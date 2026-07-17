from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import fitz

from find_rpt.cli import main
from find_rpt.evidence import PdfEvidenceExtractor
from find_rpt.rationale import RationaleExtractor
from find_rpt.rationale import ModelConfigurationError, resolve_model_mode
from find_rpt.revisions import RevisionExtractor


def semantic_template(**changes):
    value = {
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
    value.update(changes)
    return value


class AgentHostedIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.corpus = self.root / "corpus"
        self.cache = self.root / "cache"
        self.corpus.mkdir()
        path = self.corpus / f"20260622_Example Broker_{'a' * 32}.pdf"
        self.report_path = path
        document = fitz.open()
        page = document.new_page(width=700, height=800)
        page.insert_text((40, 40), "Synthetic Company: Results review", fontsize=18)
        page.insert_text((40, 75), "Bloomberg: ABC LN")
        page.insert_text((40, 110), "Results review published after results.")
        page.insert_text(
            (40, 145),
            "We raise FY2026E revenue from EUR 100m to EUR 110m due to higher prices.",
        )
        page.insert_text(
            (40, 180),
            "We met with management, including Jane Smith, Chief Financial Officer.",
        )
        page.insert_text((40, 215), "Our Buy rating is unchanged.")
        document.save(path)
        document.close()
        self.prepare = [
            "agent", "prepare", "ABC LN", "2026-06-22", "Example Broker",
            "--corpus", str(self.corpus), "--format", "json",
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare_bundle(self) -> dict:
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(self.prepare)
        self.assertEqual(code, 0, errors.getvalue())
        return json.loads(output.getvalue())

    def block_id(self, bundle: dict, phrase: str) -> str:
        passages = bundle["candidate_rationale_passages"] + bundle["candidate_context_passages"]
        return next(item["block_id"] for item in passages if phrase in item["text"])

    def finalize(self, semantic, *, output_format="agent-json") -> tuple[int, str, str]:
        semantic_path = self.root / "semantic-output.json"
        if isinstance(semantic, str):
            semantic_path.write_text(semantic, encoding="utf-8")
        else:
            semantic_path.write_text(json.dumps(semantic), encoding="utf-8")
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main([
                "agent", "finalize", "ABC LN", "2026-06-22", "Example Broker",
                "--corpus", str(self.corpus), "--cache-dir", str(self.cache),
                "--base-url", "http://127.0.0.1:65534",
                "--input", str(semantic_path), "--format", output_format,
            ])
        return code, output.getvalue(), errors.getvalue()

    def valid_semantic(self, bundle: dict, *, clarity="clear") -> dict:
        revision_id = self.block_id(bundle, "higher prices")
        context_id = self.block_id(bundle, "after results")
        return semantic_template(
            rationale_clarity=clarity,
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
                "evidence_block_ids": [context_id],
                "confidence": "high",
            },
            report_context="results_review",
            context_evidence_block_ids=[context_id],
            one_line_takeaway={
                "text": "Higher prices support revenue",
                "evidence_block_ids": [revision_id],
                "confidence": "high",
            },
        )

    def test_prepare_is_compact_and_contains_only_bounded_agent_fields(self) -> None:
        bundle = self.prepare_bundle()
        self.assertEqual(set(bundle), {
            "schema_version", "normalized_request", "selected_report_identifier",
            "validated_revisions", "candidate_rationale_passages",
            "candidate_context_passages", "allowed_metric_ids", "allowed_fiscal_period_ids",
            "analyst_candidates", "warnings",
        })
        self.assertEqual(bundle["allowed_metric_ids"], ["revenue"])
        self.assertEqual(bundle["allowed_fiscal_period_ids"], ["FY2026E"])
        passage_ids = {
            item["block_id"]
            for item in bundle["candidate_rationale_passages"] + bundle["candidate_context_passages"]
        }
        revision_ids = {
            block_id
            for revision in bundle["validated_revisions"]
            for block_id in revision["evidence_block_ids"]
        }
        self.assertTrue(revision_ids.issubset(passage_ids))
        self.assertNotIn("page_number", json.dumps(bundle))
        self.assertNotIn(str(self.root), json.dumps(bundle))

    def test_agent_prepare_accepts_alternative_date_format(self) -> None:
        command = list(self.prepare)
        command[3] = "22 Jun 2026"
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(command)
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(json.loads(output.getvalue())["normalized_request"]["date"], "20260622")

    def test_valid_agent_semantic_json_and_final_brief_rendering(self) -> None:
        bundle = self.prepare_bundle()
        code, output, errors = self.finalize(self.valid_semantic(bundle))
        self.assertEqual(code, 0, errors)
        payload = json.loads(output)
        self.assertIn(payload["status"], {"found", "partial"})
        self.assertIn("Higher prices increased revenue", payload["rendered_markdown"])
        self.assertIn("## What changed", payload["rendered_markdown"])
        self.assertTrue(payload["citations"])
        self.assertFalse(payload["sent"])

    def test_invented_block_ids_are_removed(self) -> None:
        semantic = semantic_template(one_line_takeaway={
            "text": "Higher prices support revenue",
            "evidence_block_ids": ["invented-block"],
            "confidence": "high",
        })
        code, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertEqual(code, 0)
        self.assertIn("invented_or_unselected_block_id_removed", payload["warnings"])
        self.assertNotIn("Higher prices support revenue", payload["rendered_markdown"])

    def test_block_id_from_another_report_is_removed(self) -> None:
        other_path = self.root / "other-report.pdf"
        source = fitz.open()
        page = source.new_page(width=700, height=800)
        page.insert_text((40, 80), "We lower FY2027E EPS due to higher costs.")
        source.save(other_path)
        source.close()
        document = PdfEvidenceExtractor().extract(other_path)
        revisions = RevisionExtractor().extract(document, broker="Other Broker")
        _, passages, _ = RationaleExtractor().prepare_agent(document, revisions=revisions)
        foreign_id = passages[0].block_id
        semantic = semantic_template(one_line_takeaway={
            "text": "Higher costs lower EPS",
            "evidence_block_ids": [foreign_id],
            "confidence": "high",
        })
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("invented_or_unselected_block_id_removed", payload["warnings"])
        self.assertNotIn("Higher costs lower EPS", payload["rendered_markdown"])

    def test_unsupported_numbers_are_removed(self) -> None:
        bundle = self.prepare_bundle()
        for claim in ("Revenue increases by 99%", "Revenue increases by EUR 999m"):
            with self.subTest(claim=claim):
                semantic = self.valid_semantic(bundle)
                semantic["one_line_takeaway"]["text"] = claim
                _, output, _ = self.finalize(semantic)
                payload = json.loads(output)
                self.assertIn("unsupported_claim_removed", payload["warnings"])
                self.assertNotIn(claim, payload["rendered_markdown"])

    def test_unsupported_analyst_or_management_name_is_removed(self) -> None:
        bundle = self.prepare_bundle()
        meeting_id = self.block_id(bundle, "Jane Smith")
        semantic = self.valid_semantic(bundle)
        semantic.update({
            "management_contact": "true",
            "management_evidence_block_ids": [meeting_id],
            "people_met": [{
                "name": "Mallory Invented",
                "role": "Chief Financial Officer",
                "evidence_block_ids": [meeting_id],
            }],
        })
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("unsupported_person_removed", payload["warnings"])
        self.assertNotIn("Mallory Invented", payload["rendered_markdown"])

        semantic = self.valid_semantic(bundle)
        semantic["people_met"] = [{
            "name": "Jane Smith",
            "role": "Chief Financial Officer",
            "email": "invented@example.test",
            "evidence_block_ids": [meeting_id],
        }]
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("malformed_person_removed", payload["warnings"])
        self.assertNotIn("invented@example.test", payload["rendered_markdown"])

        semantic = self.valid_semantic(bundle)
        semantic["analyst_names"] = ["Mallory Invented"]
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("agent_semantic_validation_failed:model response does not match the required top-level schema", payload["warnings"])
        self.assertNotIn("Mallory Invented", payload["rendered_markdown"])

    def test_malformed_json_returns_partial_brief_with_warning(self) -> None:
        code, output, errors = self.finalize("{not-json")
        self.assertEqual(code, 0, errors)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "partial")
        self.assertIn("agent_semantic_json_malformed", payload["warnings"])
        self.assertIn("## What changed", payload["rendered_markdown"])

    def test_missing_fields_and_invented_page_number_fail_closed(self) -> None:
        _, output, _ = self.finalize({"rationale_clarity": "clear"})
        payload = json.loads(output)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(any(item.startswith("agent_semantic_validation_failed:") for item in payload["warnings"]))

        bundle = self.prepare_bundle()
        revision_id = self.block_id(bundle, "higher prices")
        semantic = self.valid_semantic(bundle)
        semantic["one_line_takeaway"] = {
            "text": "Higher prices support revenue",
            "evidence_block_ids": [revision_id],
            "confidence": "high",
            "page_number": 999,
        }
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("malformed_grounded_claim_removed", payload["warnings"])
        self.assertNotIn("999", payload["rendered_markdown"])

    def test_unsupported_metric_period_context_management_and_causal_driver_are_removed(self) -> None:
        bundle = self.prepare_bundle()
        revision_id = self.block_id(bundle, "higher prices")
        context_id = self.block_id(bundle, "after results")
        semantic = self.valid_semantic(bundle)
        semantic["drivers"].append({
            "driver": "Higher prices increased revenue",
            "impacted_metrics": ["ebitda"],
            "fiscal_periods": ["FY2099E"],
            "category": "revenue or volume",
            "evidence_block_ids": [revision_id],
            "causal_link": "explicit",
            "confidence": "high",
        })
        semantic["drivers"].append({
            "driver": "Martian demand reduced revenue",
            "impacted_metrics": ["revenue"],
            "fiscal_periods": ["FY2026E"],
            "category": "revenue or volume",
            "evidence_block_ids": [revision_id],
            "causal_link": "explicit",
            "confidence": "high",
        })
        semantic.update({
            "report_context": "roadshow",
            "context_evidence_block_ids": [context_id],
            "management_contact": "true",
            "management_evidence_block_ids": [revision_id],
        })
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("unsupported_driver_removed", payload["warnings"])
        self.assertIn("unsupported_impacted_metric_removed", payload["warnings"])
        self.assertIn("unsupported_fiscal_period_removed", payload["warnings"])
        self.assertIn("unsupported_report_context_removed", payload["warnings"])
        self.assertIn("unsupported_management_contact_removed", payload["warnings"])
        self.assertNotIn("Martian", payload["rendered_markdown"])
        self.assertNotIn("FY2099E", payload["rendered_markdown"])
        self.assertNotIn("roadshow", payload["rendered_markdown"].casefold())

    def test_duplicate_and_contradictory_claims_do_not_survive(self) -> None:
        bundle = self.prepare_bundle()
        semantic = self.valid_semantic(bundle)
        semantic["drivers"].append(dict(semantic["drivers"][0]))
        semantic["drivers"].append({
            **semantic["drivers"][0],
            "driver": "Higher prices reduced revenue",
        })
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertIn("duplicate_driver_removed", payload["warnings"])
        self.assertIn("unsupported_driver_removed", payload["warnings"])
        self.assertEqual(payload["rendered_markdown"].count("Higher prices increased revenue"), 1)
        self.assertNotIn("Higher prices reduced revenue", payload["rendered_markdown"])

    def test_partial_rationale_is_preserved(self) -> None:
        bundle = self.prepare_bundle()
        _, output, _ = self.finalize(self.valid_semantic(bundle, clarity="partial"))
        payload = json.loads(output)
        self.assertEqual(payload["rationale_clarity"], "partial")
        self.assertIn("partially explains", payload["rendered_markdown"])

    def test_unclear_rationale_is_explicit(self) -> None:
        semantic = semantic_template(rationale_clarity="unclear")
        _, output, _ = self.finalize(semantic)
        payload = json.loads(output)
        self.assertEqual(payload["rationale_clarity"], "unclear")
        self.assertIn("does not clearly explain", payload["rendered_markdown"])
        self.assertTrue(payload["requires_analyst_escalation"])
        self.assertFalse(payload["sent"])

    def test_agent_hosted_stages_never_call_external_model(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("model call attempted")) as call:
            bundle = self.prepare_bundle()
            code, output, errors = self.finalize(self.valid_semantic(bundle))
        self.assertEqual(code, 0, errors)
        self.assertTrue(json.loads(output)["citations"])
        call.assert_not_called()

    def test_citation_viewer_unavailable_is_explicit(self) -> None:
        bundle = self.prepare_bundle()
        _, output, _ = self.finalize(self.valid_semantic(bundle))
        payload = json.loads(output)
        self.assertFalse(payload["citation_viewer_available"])
        self.assertIn("citation_viewer_unavailable", payload["warnings"])

    def test_model_mode_configuration_distinguishes_agent_api_and_none(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"FIND_RPT_MODEL_MODE": "agent-hosted"}, clear=True), redirect_stdout(output), redirect_stderr(errors):
            code = main(["rationale", "--pdf-path", str(self.report_path), "--format", "json"])
        self.assertEqual(code, 1)
        self.assertIn("agent prepare", errors.getvalue())

        output, errors = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"FIND_RPT_MODEL_MODE": "none"}, clear=True), redirect_stdout(output), redirect_stderr(errors):
            code = main(["rationale", "--pdf-path", str(self.report_path), "--format", "json"])
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"], "retrieval_only")

        with patch.dict("os.environ", {"FIND_RPT_MODEL_API_KEY": "configured"}, clear=True):
            self.assertEqual(resolve_model_mode(), "api")
        with patch.dict("os.environ", {"FIND_RPT_MODEL_MODE": "api"}, clear=True):
            self.assertEqual(resolve_model_mode(), "api")
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ModelConfigurationError):
            resolve_model_mode()

    def test_prepare_not_found_and_ambiguous_stop_before_semantics(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        command = list(self.prepare)
        command[2] = "ZZZZ LN"
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(command)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "not_found")

        second = self.corpus / f"20260622_Example Broker_{'b' * 32}.pdf"
        source = fitz.open()
        page = source.new_page(width=700, height=800)
        page.insert_text((40, 75), "Bloomberg: ABC LN")
        source.save(second)
        source.close()
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(self.prepare)
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output.getvalue())["status"], "ambiguous")

    def test_no_revisions_returns_transparent_partial_brief(self) -> None:
        corpus = self.root / "no-revisions-corpus"
        corpus.mkdir()
        path = corpus / f"20260622_Example Broker_{'c' * 32}.pdf"
        source = fitz.open()
        page = source.new_page(width=700, height=800)
        page.insert_text((40, 40), "Synthetic Company: Results preview", fontsize=18)
        page.insert_text((40, 75), "Bloomberg: NONE LN")
        page.insert_text((40, 110), "Results preview ahead of results. Demand is stable.")
        source.save(path)
        source.close()
        semantic_path = self.root / "no-revisions.semantic-output.json"
        semantic_path.write_text(json.dumps(semantic_template()), encoding="utf-8")
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main([
                "agent", "finalize", "NONE LN", "2026-06-22", "Example Broker",
                "--corpus", str(corpus), "--cache-dir", str(self.cache),
                "--input", str(semantic_path), "--format", "agent-json",
            ])
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["revisions"]["status"], "no_revisions")
        self.assertIn("no_estimate_revisions_found", payload["warnings"])

    def test_citation_cache_failure_is_sanitized(self) -> None:
        bundle = self.prepare_bundle()
        output, errors = io.StringIO(), io.StringIO()
        semantic_path = self.root / "semantic-output.json"
        semantic_path.write_text(json.dumps(self.valid_semantic(bundle)), encoding="utf-8")
        with patch("find_rpt.cli.CitationStore.save", side_effect=OSError(str(self.root / "private"))), redirect_stdout(output), redirect_stderr(errors):
            code = main([
                "agent", "finalize", "ABC LN", "2026-06-22", "Example Broker",
                "--corpus", str(self.corpus), "--cache-dir", str(self.cache),
                "--input", str(semantic_path), "--format", "agent-json",
            ])
        self.assertEqual(code, 1)
        error = json.loads(errors.getvalue())
        self.assertEqual(error["error"], "CitationFinalizationError")
        self.assertNotIn(str(self.root), errors.getvalue())


if __name__ == "__main__":
    unittest.main()
