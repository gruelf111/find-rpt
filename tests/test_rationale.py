from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import fitz

from find_rpt.cli import main
from find_rpt.evidence import PdfEvidenceExtractor
from find_rpt.rationale import (
    CandidatePassage,
    CandidatePassageSelector,
    DeterministicFakeRationaleModel,
    LocalOpenAICompatibleRationaleModel,
    ModelConfigurationError,
    RationaleInputError,
    RationaleExtractor,
    detect_context_signals,
)
from find_rpt.revisions import RevisionExtractor


def blank_response(**overrides):
    response = {
        "rationale_clarity": "clear",
        "drivers": [],
        "why_now": None,
        "report_context": "not_given",
        "context_evidence_block_ids": [],
        "management_contact": "unknown",
        "management_evidence_block_ids": [],
        "people_met": [],
        "one_line_takeaway": None,
        "jargon_definitions": [],
        "important_first_read_items": [],
        "warnings": [],
    }
    response.update(overrides)
    return response


class RationaleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_pdf(self, name: str, pages: list[list[str]]) -> Path:
        path = self.root / name
        document = fitz.open()
        for lines in pages:
            page = document.new_page(width=700, height=800)
            for index, line in enumerate(lines):
                page.insert_text((40, 50 + index * 35), line)
        document.save(path)
        document.close()
        return path

    def evidence_and_revisions(self, path: Path):
        evidence = PdfEvidenceExtractor().extract(path)
        return evidence, RevisionExtractor().extract(evidence)

    def test_candidate_passages_anchor_revisions_adjacency_and_bounded_size(self) -> None:
        path = self.make_pdf(
            "candidates.pdf",
            [[
                "Results review after results",
                "We raise FY2026E revenue from EUR 100m to EUR 110m due to higher prices.",
                "Pricing remained firm in the quarter.",
                "Unrelated historical appendix text.",
            ]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        passages = CandidatePassageSelector(max_blocks=3, max_characters=500).select(
            evidence, revisions
        )
        self.assertLessEqual(len(passages), 3)
        self.assertLessEqual(sum(len(item.text) for item in passages), 500)
        self.assertTrue(any("revision_evidence" in item.reasons for item in passages))
        self.assertTrue(any("due to higher prices" in item.text for item in passages))

    def test_direct_context_is_not_crowded_out_by_dense_revision_evidence(self) -> None:
        lines = ["Results preview ahead of results"] + [
            f"We raise FY20{26 + index}E revenue from EUR 100m to EUR 110m due to pricing."
            for index in range(10)
        ]
        path = self.make_pdf("dense-context.pdf", [lines])
        evidence, revisions = self.evidence_and_revisions(path)
        passages = CandidatePassageSelector(max_blocks=5, max_characters=2_000).select(
            evidence, revisions
        )
        self.assertTrue(any("Results preview" in passage.text for passage in passages))
        self.assertIn("results_preview", detect_context_signals(passages))

    def test_context_classification_signals(self) -> None:
        passages = (
            CandidatePassage(1, "a", "Results preview ahead of results", (), 1),
            CandidatePassage(1, "b", "We met with management on the roadshow", (), 1),
            CandidatePassage(1, "c", "We upgraded the shares after the announcement", (), 1),
        )
        signals = detect_context_signals(passages)
        self.assertIn("results_preview", signals)
        self.assertIn("roadshow", signals)
        self.assertIn("management_meeting", signals)
        self.assertIn("rating_change", signals)
        self.assertIn("event_reaction", signals)

    def test_clear_rationale_context_management_people_and_takeaway(self) -> None:
        path = self.make_pdf(
            "clear.pdf",
            [[
                "Results review published after results.",
                "We raise FY2026E revenue from EUR 100m to EUR 110m due to higher prices.",
                "We met with management, including Jane Smith, Chief Financial Officer.",
                "Our Buy rating and target price are unchanged.",
            ]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        passages = CandidatePassageSelector().select(evidence, revisions)
        by_text = {item.text: item.block_id for item in passages}
        revision_id = next(value for text, value in by_text.items() if "higher prices" in text)
        timing_id = next(value for text, value in by_text.items() if "after results" in text)
        meeting_id = next(value for text, value in by_text.items() if "Jane Smith" in text)
        rating_id = next(value for text, value in by_text.items() if "Buy rating" in text)
        response = blank_response(
            drivers=[{
                "driver": "Higher prices increased revenue",
                "impacted_metrics": ["revenue"],
                "fiscal_periods": ["FY2026E"],
                "category": "pricing",
                "evidence_block_ids": [revision_id],
                "causal_link": "explicit",
                "confidence": "high",
            }],
            why_now={
                "text": "Published after results",
                "evidence_block_ids": [timing_id],
                "confidence": "high",
            },
            report_context="results_review",
            context_evidence_block_ids=[timing_id],
            management_contact="true",
            management_evidence_block_ids=[meeting_id],
            people_met=[{
                "name": "Jane Smith",
                "role": "Chief Financial Officer",
                "evidence_block_ids": [meeting_id],
            }],
            one_line_takeaway={
                "text": "Higher prices support revenue",
                "evidence_block_ids": [revision_id],
                "confidence": "high",
            },
            important_first_read_items=[{
                "text": "Buy rating is unchanged",
                "evidence_block_ids": [rating_id],
                "confidence": "high",
            }],
        )
        model = DeterministicFakeRationaleModel(response)
        result = RationaleExtractor(model).extract(evidence, revisions=revisions)
        self.assertEqual(result.status, "interpreted")
        extraction = result.extraction
        self.assertEqual(extraction.rationale_clarity, "clear")
        self.assertEqual(extraction.drivers[0].causal_link, "explicit")
        self.assertEqual(extraction.drivers[0].impacted_metrics, ("revenue",))
        self.assertEqual(extraction.report_context, "results_review")
        self.assertEqual(extraction.management_contact, "true")
        self.assertEqual(extraction.people_met[0].name, "Jane Smith")
        self.assertEqual(extraction.people_met[0].role, "Chief Financial Officer")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(
            {item["block_id"] for item in model.calls[0]["evidence_passages"]},
            {item.block_id for item in result.candidate_passages},
        )

    def test_invalid_block_and_unsupported_claims_are_removed(self) -> None:
        path = self.make_pdf(
            "unsupported.pdf",
            [["We raise FY2026E revenue from EUR 100m to EUR 110m."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        response = blank_response(
            drivers=[{
                "driver": "Martian demand lifted revenue by 99%",
                "impacted_metrics": ["revenue"],
                "fiscal_periods": ["FY2099E"],
                "category": "revenue or volume",
                "evidence_block_ids": ["invented-block"],
                "causal_link": "explicit",
                "confidence": "high",
            }],
            one_line_takeaway={
                "text": "Revenue rises 99%",
                "evidence_block_ids": ["invented-block"],
                "confidence": "high",
            },
        )
        result = RationaleExtractor(DeterministicFakeRationaleModel(response)).extract(
            evidence, revisions=revisions
        )
        self.assertEqual(result.extraction.rationale_clarity, "unclear")
        self.assertEqual(result.extraction.drivers, ())
        self.assertIsNone(result.extraction.one_line_takeaway)
        self.assertIn("invented_or_unselected_block_id_removed", result.extraction.warnings)
        self.assertIn("unsupported_driver_removed", result.extraction.warnings)

    def test_partial_rationale_downgrades_unproven_causal_link(self) -> None:
        path = self.make_pdf(
            "partial.pdf",
            [["We raise FY2026E revenue from EUR 100m to EUR 110m. Pricing likely contributed to the revenue increase."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        block_id = CandidatePassageSelector().select(evidence, revisions)[0].block_id
        response = blank_response(drivers=[{
            "driver": "Pricing likely contributed to revenue increase",
            "impacted_metrics": ["revenue", "EBITDA"],
            "fiscal_periods": ["FY2026E", "FY2099E"],
            "category": "pricing",
            "evidence_block_ids": [block_id],
            "causal_link": "explicit",
            "confidence": "medium",
        }])
        result = RationaleExtractor(DeterministicFakeRationaleModel(response)).extract(
            evidence, revisions=revisions
        )
        self.assertEqual(result.extraction.rationale_clarity, "partial")
        self.assertEqual(result.extraction.drivers[0].causal_link, "inferred")
        self.assertEqual(result.extraction.drivers[0].impacted_metrics, ("revenue",))
        self.assertEqual(result.extraction.drivers[0].fiscal_periods, ("FY2026E",))
        self.assertIn("unsupported_impacted_metric_removed", result.extraction.warnings)
        self.assertIn("unsupported_fiscal_period_removed", result.extraction.warnings)

    def test_nearby_fact_cannot_survive_as_a_causal_driver(self) -> None:
        path = self.make_pdf(
            "nearby-fact.pdf",
            [["We raise FY2026E revenue from EUR 100m to EUR 110m due to higher pricing. Mars demand was discussed nearby."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        block_id = CandidatePassageSelector().select(evidence, revisions)[0].block_id
        response = blank_response(drivers=[{
            "driver": "Mars demand increased revenue",
            "impacted_metrics": ["revenue"],
            "fiscal_periods": ["FY2026E"],
            "category": "revenue or volume",
            "evidence_block_ids": [block_id],
            "causal_link": "explicit",
            "confidence": "high",
        }])
        result = RationaleExtractor(DeterministicFakeRationaleModel(response)).extract(
            evidence, revisions=revisions
        )
        self.assertEqual(result.extraction.drivers, ())
        self.assertEqual(result.extraction.rationale_clarity, "unclear")
        self.assertIn("unsupported_causal_driver_removed", result.extraction.warnings)

    def test_valuation_change_cannot_become_an_earnings_driver(self) -> None:
        path = self.make_pdf(
            "valuation-driver.pdf",
            [["We lower FY2026E EPS from EUR 2.00 to EUR 1.80 due to operating costs. We upgrade to Buy because valuation is attractive."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        block_id = CandidatePassageSelector().select(evidence, revisions)[0].block_id
        response = blank_response(drivers=[{
            "driver": "Attractive valuation reduced EPS",
            "impacted_metrics": ["EPS"],
            "fiscal_periods": ["FY2026E"],
            "category": "valuation only",
            "evidence_block_ids": [block_id],
            "causal_link": "explicit",
            "confidence": "high",
        }])
        result = RationaleExtractor(DeterministicFakeRationaleModel(response)).extract(
            evidence, revisions=revisions
        )
        self.assertEqual(result.extraction.drivers, ())
        self.assertIn(
            "valuation_only_driver_not_linked_to_target_price",
            result.extraction.warnings,
        )

    def test_unclear_when_revisions_have_no_explanation(self) -> None:
        path = self.make_pdf(
            "unclear.pdf",
            [["We raise FY2026E revenue from EUR 100m to EUR 110m."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        result = RationaleExtractor(
            DeterministicFakeRationaleModel(blank_response(rationale_clarity="clear"))
        ).extract(evidence, revisions=revisions)
        self.assertEqual(revisions.status, "revisions_found")
        self.assertEqual(result.extraction.rationale_clarity, "unclear")

    def test_report_with_no_revisions_remains_explicit(self) -> None:
        path = self.make_pdf(
            "no-revisions.pdf",
            [["Results preview ahead of results. Demand is stable."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        result = RationaleExtractor(
            DeterministicFakeRationaleModel(blank_response(rationale_clarity="clear"))
        ).extract(evidence, revisions=revisions)
        self.assertEqual(result.revision_status, "no_revisions")
        self.assertEqual(result.extraction.rationale_clarity, "clear")

    def test_malformed_model_json_returns_explicit_warning(self) -> None:
        path = self.make_pdf("malformed.pdf", [["Results preview ahead of results."]])
        evidence, revisions = self.evidence_and_revisions(path)
        result = RationaleExtractor(DeterministicFakeRationaleModel("not json")).extract(
            evidence, revisions=revisions
        )
        self.assertEqual(result.status, "model_error")
        self.assertIsNone(result.extraction)
        self.assertTrue(result.warnings[0].startswith("model_failure:"))

    def test_extra_schema_fields_and_unexpected_provider_errors_fail_safely(self) -> None:
        path = self.make_pdf("provider-errors.pdf", [["Results preview ahead of results."]])
        evidence, revisions = self.evidence_and_revisions(path)
        extra = blank_response(unexpected="value")
        malformed = RationaleExtractor(DeterministicFakeRationaleModel(extra)).extract(
            evidence, revisions=revisions
        )
        self.assertEqual(malformed.status, "model_error")

        class BrokenModel:
            def extract(self, payload):
                raise RuntimeError("private provider detail")

        broken = RationaleExtractor(BrokenModel()).extract(evidence, revisions=revisions)
        self.assertEqual(broken.status, "model_error")
        self.assertEqual(
            broken.warnings,
            ("model_failure:unexpected_provider_or_validation_error",),
        )
        self.assertNotIn("private provider detail", broken.to_json())

    def test_revision_data_from_another_document_is_rejected(self) -> None:
        first_path = self.make_pdf(
            "first.pdf", [["We raise FY2026E revenue from EUR 100m to EUR 110m due to pricing."]]
        )
        second_path = self.make_pdf("second.pdf", [["Results preview ahead of results."]])
        first_evidence, first_revisions = self.evidence_and_revisions(first_path)
        second_evidence = PdfEvidenceExtractor().extract(second_path)
        with self.assertRaises(RationaleInputError):
            RationaleExtractor().extract(
                second_evidence, revisions=first_revisions, no_model=True
            )

    def test_non_loopback_model_endpoint_is_rejected(self) -> None:
        with self.assertRaises(ModelConfigurationError):
            LocalOpenAICompatibleRationaleModel(
                "https://example.com/v1/chat/completions", "key", "model"
            )

    def test_people_roles_and_jargon_are_conservatively_validated(self) -> None:
        path = self.make_pdf(
            "identity.pdf",
            [["We met with management, including Jane Smith, Chief Financial Officer. EPS was discussed."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        block_id = CandidatePassageSelector().select(evidence, revisions)[0].block_id
        response = blank_response(
            management_contact="true",
            management_evidence_block_ids=[block_id],
            people_met=[{
                "name": "Jane Smith",
                "role": "Chief Technology Officer",
                "evidence_block_ids": [block_id],
            }],
            jargon_definitions=[{
                "term": "EPS",
                "definition": "revenue per share",
                "evidence_block_ids": [block_id],
            }],
        )
        result = RationaleExtractor(DeterministicFakeRationaleModel(response)).extract(
            evidence, revisions=revisions
        )
        self.assertIsNone(result.extraction.people_met[0].role)
        self.assertEqual(result.extraction.jargon_definitions, ())
        self.assertIn("unsupported_person_role_removed", result.extraction.warnings)
        self.assertIn("unsupported_jargon_definition_removed", result.extraction.warnings)

    def test_missing_api_key_fails_clearly_and_no_model_is_available(self) -> None:
        path = self.make_pdf("missing-key.pdf", [["Results preview ahead of results."]])
        evidence, revisions = self.evidence_and_revisions(path)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ModelConfigurationError):
            RationaleExtractor().extract(evidence, revisions=revisions)
        no_model = RationaleExtractor().extract(evidence, revisions=revisions, no_model=True)
        self.assertEqual(no_model.status, "retrieval_only")
        self.assertIsNone(no_model.extraction)

        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), redirect_stderr(errors):
            code = main(["rationale", "--pdf-path", str(path), "--format", "json"])
        self.assertEqual(code, 1)
        self.assertIn("FIND_RPT_MODEL_API_KEY", errors.getvalue())

    def test_fake_model_and_structured_output_are_repeatable(self) -> None:
        path = self.make_pdf(
            "repeatable.pdf",
            [["We lower FY2027E EPS from EUR 2.00 to EUR 1.80 due to operating costs."]],
        )
        evidence, revisions = self.evidence_and_revisions(path)
        block_id = CandidatePassageSelector().select(evidence, revisions)[0].block_id
        response = blank_response(drivers=[{
            "driver": "Operating costs reduced EPS",
            "impacted_metrics": ["EPS"],
            "fiscal_periods": ["FY2027E"],
            "category": "operating costs",
            "evidence_block_ids": [block_id],
            "causal_link": "explicit",
            "confidence": "high",
        }])
        model = DeterministicFakeRationaleModel(response)
        extractor = RationaleExtractor(model)
        first = extractor.extract(evidence, revisions=revisions)
        second = extractor.extract(evidence, revisions=revisions)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first.to_json()), json.loads(second.to_json()))

        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main([
                "rationale", "--pdf-path", str(path), "--no-model", "--format", "json"
            ])
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "retrieval_only")
        self.assertGreater(payload["model_input_block_count"], 0)


class RealReportRationaleRetrievalTests(unittest.TestCase):
    def test_real_reports_have_repeatable_bounded_model_inputs(self) -> None:
        corpus = Path("corpus")
        cases_path = Path("tests/revision_evaluation_cases.json")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(filename=case["filename"]):
                document = PdfEvidenceExtractor().extract(corpus / case["filename"])
                revisions = RevisionExtractor().extract(document, broker=case["broker"])
                extractor = RationaleExtractor()
                first = extractor.extract(
                    document, revisions=revisions, no_model=True, broker=case["broker"]
                )
                second = extractor.extract(
                    document, revisions=revisions, no_model=True, broker=case["broker"]
                )
                self.assertEqual(first, second)
                self.assertEqual(first.status, "retrieval_only")
                self.assertLessEqual(first.model_input_block_count, 24)
                self.assertLessEqual(first.model_input_character_count, 12_000)
                self.assertTrue(first.candidate_passages)
                valid_ids = {
                    block.block_id for page in document.pages for block in page.blocks
                }
                self.assertTrue(
                    all(item.block_id in valid_ids for item in first.candidate_passages)
                )

    def test_management_meeting_report_is_retrieved_without_model_use(self) -> None:
        path = Path("corpus/20260511_Goldman Sachs_056e83f8b6ec877143bb64acd780409e.pdf")
        if not path.is_file():
            self.skipTest("local management-meeting report is not available")
        document = PdfEvidenceExtractor().extract(path)
        result = RationaleExtractor().extract(document, no_model=True, broker="Goldman Sachs")
        self.assertIn("management_meeting", result.context_signals)
        self.assertLessEqual(result.model_input_block_count, 24)
        self.assertLessEqual(result.model_input_character_count, 12_000)


if __name__ == "__main__":
    unittest.main()
