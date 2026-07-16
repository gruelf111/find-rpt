from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

import fitz

from find_rpt.brief import ResearchBriefBuilder, render_markdown, render_text
from find_rpt.citations import CitationBuildResult, CitationRecord
from find_rpt.cli import main
from find_rpt.escalation import (
    AmbiguityEscalationBuilder,
    EscalationPolicy,
    assess_materiality,
    render_email_draft_markdown,
    render_email_draft_text,
)
from find_rpt.evidence import PdfEvidenceExtractor
from find_rpt.metadata import AnalystMetadata, ReportMetadata, ReportMetadataExtractor
from find_rpt.rationale import Driver, RationaleExtraction, RationaleResult
from find_rpt.revisions import EstimateRevision, RevisionEvidence, RevisionResult


DOCUMENT_ID = "sha256:" + "a" * 64


def revision(
    metric: str = "eps",
    period: str | None = "FY2026E",
    *,
    old: float | None = 1.0,
    new: float | None = 1.1,
    unit: str | None = "EUR/share",
    stated_pct: float | None = None,
    stated_pp: float | None = None,
    consensus: float | None = None,
    direction: str | None = None,
    indicators: tuple[str, ...] = (),
) -> EstimateRevision:
    calculated_pct = (
        None
        if old in (None, 0) or new is None
        else round((new - old) / abs(old) * 100, 4)
    )
    calculated_pp = new - old if unit == "%" and old is not None and new is not None else None
    return EstimateRevision(
        metric=metric,
        metric_qualifiers=("adjusted",) if metric == "eps" else (),
        fiscal_period=period,
        period_basis="fiscal" if period else None,
        old_value=old,
        new_value=new,
        unit=unit,
        stated_revision_pct=stated_pct,
        calculated_revision_pct=calculated_pct,
        stated_change_pp=stated_pp,
        calculated_change_pp=calculated_pp,
        consensus_value=consensus,
        old_vs_consensus_pct=None,
        new_vs_consensus_pct=(
            None if new is None or consensus in (None, 0) else round((new - consensus) / abs(consensus) * 100, 4)
        ),
        direction=direction or ("unknown" if old is None or new is None else "increase" if new > old else "decrease" if new < old else "unchanged"),
        evidence=(RevisionEvidence(1, ("block-revision",)),),
        extraction_method="synthetic",
        confidence="high",
        warnings=(),
        materiality_indicators=indicators,
    )


def revisions(*rows: EstimateRevision, status: str = "revisions_found") -> RevisionResult:
    return RevisionResult(status, DOCUMENT_ID, "synthetic.pdf", (1,), ("block-revision",), tuple(rows), ())


def rationale(
    clarity: str,
    *,
    drivers: tuple[Driver, ...] = (),
    context: str = "not_given",
    management: str = "unknown",
) -> RationaleResult:
    extraction = RationaleExtraction(
        rationale_clarity=clarity,
        drivers=drivers,
        why_now=None,
        report_context=context,
        context_evidence_block_ids=(),
        management_contact=management,
        management_evidence_block_ids=(),
        people_met=(),
        one_line_takeaway=None,
        jargon_definitions=(),
        important_first_read_items=(),
        warnings=(),
    )
    return RationaleResult("interpreted", DOCUMENT_ID, "synthetic.pdf", "revisions_found", (), (), extraction, 0, 0, ())


def metadata(*analysts: AnalystMetadata) -> ReportMetadata:
    return ReportMetadata(
        "Synthetic Company: Estimate update",
        ("block-title",),
        "2026-06-22",
        tuple(analysts),
        (),
        document_id=DOCUMENT_ID,
    )


def analyst(name="Alex Example", email="alex@example.test", **kwargs) -> AnalystMetadata:
    return AnalystMetadata(name, "Lead Research Analyst", email, ("block-analyst",), **kwargs)


def build(
    rows: RevisionResult,
    rationale_result: RationaleResult | None,
    *,
    report_metadata: ReportMetadata | None = None,
    policy: EscalationPolicy | None = None,
):
    return AmbiguityEscalationBuilder(policy).build(
        ticker="ABC LN",
        report_date="2026-06-22",
        metadata=report_metadata or metadata(analyst()),
        revisions=rows,
        rationale=rationale_result,
    )


class TriggerAndMaterialityTests(unittest.TestCase):
    def test_clear_rationale_no_escalation(self) -> None:
        self.assertFalse(build(revisions(revision()), rationale("clear")).requires_analyst_escalation)

    def test_unclear_rationale_with_one_material_revision(self) -> None:
        result = build(revisions(revision(old=1, new=1.1)), rationale("unclear"))
        self.assertTrue(result.requires_analyst_escalation)
        self.assertEqual(result.escalation_reason, "rationale_unclear_for_material_revision")
        self.assertIn("adjusted EPS", result.email_draft.questions[0])
        self.assertIn("FY2026E", result.email_draft.questions[0])

    def test_unclear_rationale_with_several_revisions_is_specific(self) -> None:
        result = build(
            revisions(
                revision("revenue", "FY2027E", old=100, new=105, unit="EURm"),
                revision("eps", "FY2026E", old=1, new=1.1),
            ),
            rationale("unclear"),
        )
        self.assertEqual(len(result.email_draft.questions), 2)
        self.assertIn("EPS", result.email_draft.questions[0])
        self.assertIn("revenue", result.email_draft.questions[1])

    def test_partial_policy_only_escalates_material_unexplained_revision(self) -> None:
        immaterial = build(
            revisions(revision(old=100, new=102, unit="EURm")),
            rationale("partial"),
            policy=EscalationPolicy(escalate_partial=True),
        )
        self.assertFalse(immaterial.requires_analyst_escalation)
        material = build(
            revisions(revision(old=100, new=104, unit="EURm")),
            rationale("partial"),
            policy=EscalationPolicy(escalate_partial=True),
        )
        self.assertTrue(material.requires_analyst_escalation)
        disabled = build(revisions(revision()), rationale("partial"))
        self.assertFalse(disabled.requires_analyst_escalation)
        self.assertIn("partial_rationale_escalation_disabled", disabled.warnings)

    def test_no_revisions(self) -> None:
        result = build(revisions(status="no_revisions"), rationale("unclear"))
        self.assertFalse(result.requires_analyst_escalation)

    def test_rating_and_target_price_changes_are_material(self) -> None:
        rating = revision("rating", None, old=None, new=None, unit=None, direction="increase")
        target = revision("target_price", None, old=50, new=51, unit="EUR")
        self.assertTrue(assess_materiality(rating).is_material)
        self.assertTrue(assess_materiality(target).is_material)
        result = build(revisions(rating, target), rationale("unclear"))
        self.assertEqual(len(result.email_draft.questions), 2)
        unresolved = revision("rating", None, old=None, new=None, unit=None, direction="unknown")
        self.assertFalse(assess_materiality(unresolved).is_material)

    def test_percentage_point_margin_has_separate_threshold(self) -> None:
        small = revision("ebit_margin", old=10, new=10.5, unit="%", stated_pp=0.5)
        material = revision("ebit_margin", old=10, new=11.2, unit="%", stated_pp=1.2)
        self.assertFalse(assess_materiality(small).is_material)
        assessment = assess_materiality(material)
        self.assertTrue(assessment.is_material)
        self.assertEqual(assessment.change_kind, "percentage_points")

    def test_negative_values_use_absolute_base_and_zero_denominator_is_explicit(self) -> None:
        negative = revision(old=-100, new=-96, unit="EURm")
        assessment = assess_materiality(negative)
        self.assertTrue(assessment.is_material)
        self.assertEqual(assessment.reason, "relative_threshold_negative_base")
        zero = assess_materiality(revision(old=0, new=100, unit="EURm"))
        self.assertFalse(zero.is_material)
        self.assertEqual(zero.reason, "zero_denominator_materiality_unresolved")

    def test_non_numeric_requires_validated_material_indicator(self) -> None:
        non_numeric = revision(old=None, new=None, unit=None, direction="unknown")
        self.assertFalse(assess_materiality(non_numeric).is_material)
        warning_only = replace(
            non_numeric,
            warnings=("explicitly_marked_material",),
        )
        self.assertFalse(assess_materiality(warning_only).is_material)
        marked = replace(non_numeric, materiality_indicators=("explicitly_marked_material",))
        self.assertTrue(assess_materiality(marked).is_material)


class AnalystAndQuestionTests(unittest.TestCase):
    def test_analyst_name_and_email_found(self) -> None:
        result = build(revisions(revision()), rationale("unclear"), report_metadata=metadata(analyst()))
        self.assertEqual(result.email_draft.to, "alex@example.test")
        self.assertEqual(result.email_draft.analyst_names, ("Alex Example",))

    def test_name_found_but_email_missing_uses_exact_placeholder(self) -> None:
        result = build(revisions(revision()), rationale("unclear"), report_metadata=metadata(analyst(email=None)))
        self.assertEqual(result.email_draft.to, "[TODO: address]")
        self.assertIn("recipient_address", result.email_draft.unresolved_fields)

    def test_multiple_analysts_are_all_addressed_without_unsupported_lead_choice(self) -> None:
        first = analyst("Alex Example", "alex@example.test", selection_status="relevant")
        second = analyst("Blair Example", "blair@example.test", selection_status="relevant")
        result = build(revisions(revision()), rationale("unclear"), report_metadata=metadata(first, second))
        self.assertEqual(result.email_draft.analyst_names, ("Alex Example", "Blair Example"))
        self.assertEqual(result.email_draft.to, "alex@example.test; blair@example.test")

    def test_no_identity_uses_neutral_greeting_and_warning(self) -> None:
        result = build(revisions(revision()), rationale("unclear"), report_metadata=metadata())
        self.assertEqual(result.email_draft.greeting, "Hello,")
        self.assertEqual(result.email_draft.to, "[TODO: address]")
        self.assertIn("analyst_identity_not_found_neutral_greeting_used", result.email_draft.warnings)

    def test_duplicate_questions_are_removed_and_order_is_deterministic(self) -> None:
        row = revision("eps", "FY2026E", old=1, new=1.1)
        first = build(revisions(row, row), rationale("unclear"))
        second = build(revisions(row, row), rationale("unclear"))
        self.assertEqual(first, second)
        self.assertEqual(len(first.email_draft.questions), 1)

    def test_consensus_comparison_is_in_question(self) -> None:
        row = replace(
            revision(old=1, new=1.1, consensus=1.0),
            new_vs_consensus_pct=10.0,
        )
        question = build(revisions(row), rationale("unclear")).email_draft.questions[0]
        self.assertIn("above consensus", question)
        self.assertIn("1 EUR/share", question)

    def test_question_already_answered_elsewhere_is_not_included(self) -> None:
        answered = revision("eps", "FY2026E", old=1, new=1.1)
        unresolved = revision("revenue", "FY2027E", old=100, new=105, unit="EURm")
        driver = Driver(
            "Pricing increased EPS",
            ("eps",),
            ("FY2026E",),
            "pricing",
            ("block-driver",),
            "explicit",
            "high",
        )
        result = build(
            revisions(answered, unresolved),
            rationale("partial", drivers=(driver,)),
            policy=EscalationPolicy(escalate_partial=True),
        )
        self.assertEqual(len(result.email_draft.questions), 1)
        self.assertIn("revenue", result.email_draft.questions[0])
        self.assertNotIn("EPS", result.email_draft.questions[0])

    def test_inferred_driver_is_context_not_a_clear_answer(self) -> None:
        incomplete = Driver(
            "Pricing may contribute to EPS",
            ("eps",),
            ("FY2026E",),
            "pricing",
            ("block-driver",),
            "inferred",
            "medium",
        )
        result = build(
            revisions(revision()),
            rationale("unclear", drivers=(incomplete,)),
        )
        self.assertTrue(result.requires_analyst_escalation)
        self.assertIn("mentions Pricing may contribute to EPS", result.email_draft.questions[0])

    def test_report_context_and_management_make_question_specific(self) -> None:
        result = build(
            revisions(revision()),
            rationale("unclear", context="results_review", management="true"),
        )
        self.assertIn("result or management comment", result.email_draft.questions[0])


class RenderingAndSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = build(revisions(revision()), rationale("unclear"))

    def test_markdown_json_and_text_rendering(self) -> None:
        markdown = render_email_draft_markdown(self.result.email_draft)
        text = render_email_draft_text(self.result.email_draft)
        payload = json.loads(self.result.to_json())
        self.assertIn("**To:**", markdown)
        self.assertIn("To:", text)
        self.assertTrue(payload["requires_analyst_escalation"])
        self.assertIn("analyst", payload)
        self.assertIn("email_draft", payload)
        self.assertFalse(payload["sent"])
        self.assertFalse(payload["email_draft"]["sent"])
        self.assertIn("has not been sent", markdown)
        self.assertIn("has not been sent", text)

    def test_brief_surfaces_draft_last_and_stops(self) -> None:
        citation = CitationRecord(
            "cit-" + "1" * 24,
            DOCUMENT_ID,
            "synthetic.pdf",
            1,
            "a" * 64,
            1,
            600,
            800,
            ("block-revision",),
            ((1, 1, 2, 2),),
            "Revision",
            "revision:1:evidence:1",
            "http://127.0.0.1:8765/citation/cit-" + "1" * 24,
            "valid",
            (),
        )
        citations = CitationBuildResult(DOCUMENT_ID, "synthetic.pdf", (citation,), 0, ())
        brief = ResearchBriefBuilder().build(
            ticker="ABC LN",
            broker="Example Broker",
            report_date="2026-06-22",
            metadata=metadata(analyst()),
            revisions=revisions(revision()),
            rationale=rationale("unclear"),
            citations=citations,
            escalation=self.result,
        )
        markdown = render_markdown(brief)
        self.assertIn("Analyst clarification draft", markdown)
        self.assertTrue(markdown.rstrip().endswith("outside find-rpt._"))
        self.assertIn("has not been sent", render_text(brief))
        structured = json.loads(brief.to_json())
        self.assertTrue(structured["requires_analyst_escalation"])
        self.assertFalse(structured["email_draft"]["sent"])

    def test_user_signoff_placeholder(self) -> None:
        self.assertEqual(self.result.email_draft.signoff_placeholder, "Best,\n[Your name]")
        self.assertIn("[Your name]", self.result.email_draft.body)

    def test_no_prohibited_delivery_capability_or_dependency(self) -> None:
        roots = [Path("src"), Path("pyproject.toml")]
        source = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for root in roots
            for path in ([root] if root.is_file() else sorted(root.rglob("*.py")))
        )
        prohibited = (
            r"\bsmtplib\b",
            r"\bSMTP\b",
            r"\bGmail\b",
            r"\bOutlook\b",
            r"\bSendGrid\b",
            r"\bmailgun\b",
            r"\bmailto\b",
            r"\bsend_email\b",
            r"\bsend[-_]draft\b",
            r"\b(?:SMTP|EMAIL)_(?:USER|PASS|PASSWORD|TOKEN|CREDENTIALS)\b",
            r"subprocess\s*\..*\bmail\b",
            r"\b(?:pyperclip|clipboard|Set-Clipboard)\b",
            r"\b(?:gmail\.googleapis|graph\.microsoft|api\.sendgrid|api\.mailgun)\b",
        )
        for pattern in prohibited:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, source, re.I))


class AnalystExtractionTests(unittest.TestCase):
    def test_designation_phone_missing_email_and_multiple_analysts_are_evidence_backed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "analysts.pdf"
            document = fitz.open()
            page = document.new_page(width=600, height=800)
            page.insert_text((40, 40), "Synthetic Company: Estimate update", fontsize=18)
            page.insert_textbox(
                fitz.Rect(40, 80, 330, 180),
                "Alex Example, CFA\nLead Research Analyst\n+44 20 1234 5678\nalex@example.test",
                fontsize=10,
            )
            page.insert_textbox(
                fitz.Rect(350, 80, 580, 160),
                "Blair Example\nResearch Analyst",
                fontsize=10,
            )
            document.save(path)
            document.close()
            evidence_document = PdfEvidenceExtractor().extract(path)
            result = ReportMetadataExtractor().extract(evidence_document)
        by_name = {item.name: item for item in result.analysts}
        self.assertEqual(by_name["Alex Example"].designation, "CFA")
        self.assertEqual(by_name["Alex Example"].email, "alex@example.test")
        self.assertIsNotNone(by_name["Alex Example"].phone)
        self.assertEqual(by_name["Alex Example"].selection_status, "lead")
        self.assertIsNone(by_name["Blair Example"].email)
        self.assertTrue(all(item.evidence_block_ids for item in result.analysts))
        evidence_by_id = {
            block.block_id: block.text
            for page in evidence_document.pages
            for block in page.blocks
        }
        alex_evidence = "\n".join(
            evidence_by_id[block_id]
            for block_id in by_name["Alex Example"].evidence_block_ids
        )
        for explicit_field in (
            by_name["Alex Example"].name,
            by_name["Alex Example"].designation,
            by_name["Alex Example"].role,
            by_name["Alex Example"].email,
            by_name["Alex Example"].phone,
        ):
            self.assertIn(explicit_field, alex_evidence)


class EscalationCliTests(unittest.TestCase):
    def test_markdown_json_and_text_commands_complete_without_delivery_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            corpus.mkdir()
            path = corpus / f"20260622_Example Broker_{'a' * 32}.pdf"
            document = fitz.open()
            page = document.new_page(width=600, height=800)
            page.insert_text((40, 40), "Synthetic Company: Estimate update", fontsize=18)
            page.insert_text((40, 75), "Bloomberg: ABC LN")
            page.insert_text((40, 110), "We raise FY2026E revenue from EUR 100m to EUR 110m.")
            document.save(path)
            document.close()

            for output_format in ("markdown", "json", "text"):
                with self.subTest(output_format=output_format):
                    output, errors = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = main([
                            "escalation", "--ticker", "ABC LN", "--date", "2026-06-22",
                            "--broker", "Example Broker", "--corpus", str(corpus),
                            "--no-model", "--format", output_format,
                        ])
                    self.assertEqual(code, 0, errors.getvalue())
                    self.assertNotIn(str(corpus), output.getvalue())
                    if output_format == "json":
                        payload = json.loads(output.getvalue())
                        self.assertFalse(payload["requires_analyst_escalation"])
                        self.assertIn("email_draft", payload)
                        self.assertIn("warnings", payload)
                    else:
                        self.assertIn("No analyst escalation is required", output.getvalue())
                        self.assertIn("rationale clarity unavailable", output.getvalue())


if __name__ == "__main__":
    unittest.main()
