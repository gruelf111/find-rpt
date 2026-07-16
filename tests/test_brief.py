from __future__ import annotations

import io
import http.client
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

import fitz

from find_rpt.brief import (
    BriefRevisionRow,
    ResearchBriefBuilder,
    make_estimate_visualization,
    render_markdown,
    render_text,
)
from find_rpt.citations import CitationBuildResult, CitationRecord
from find_rpt.citations import CitationBuilder, make_server, requests_from_metadata, requests_from_revisions
from find_rpt.cli import main
from find_rpt.metadata import AnalystMetadata, ReportMetadata
from find_rpt.metadata import ReportMetadataExtractor
from find_rpt.rationale import (
    Driver,
    GroundedClaim,
    PersonMet,
    RationaleExtraction,
    RationaleResult,
)
from find_rpt.revisions import EstimateRevision, RevisionEvidence, RevisionExtractor, RevisionResult
from find_rpt.evidence import PdfEvidenceExtractor
from find_rpt.rationale import RationaleExtractor


DOCUMENT_ID = "sha256:" + "1" * 64


def revision(
    metric: str = "eps",
    period: str | None = "FY2026E",
    *,
    old: float | None = 1.0,
    new: float | None = 1.1,
    consensus: float | None = 1.05,
    unit: str | None = "EUR/share",
    stated_pct: float | None = None,
    stated_pp: float | None = None,
    warnings: tuple[str, ...] = (),
) -> EstimateRevision:
    calculated = None if old in (None, 0) or new is None else round((new - old) / abs(old) * 100, 4)
    return EstimateRevision(
        metric=metric,
        metric_qualifiers=("adjusted",) if metric == "eps" else (),
        fiscal_period=period,
        period_basis="fiscal" if period else None,
        old_value=old,
        new_value=new,
        unit=unit,
        stated_revision_pct=stated_pct,
        calculated_revision_pct=calculated,
        stated_change_pp=stated_pp,
        calculated_change_pp=(new - old) if unit == "%" and old is not None and new is not None else None,
        consensus_value=consensus,
        old_vs_consensus_pct=None if old is None or consensus in (None, 0) else round((old - consensus) / abs(consensus) * 100, 4),
        new_vs_consensus_pct=None if new is None or consensus in (None, 0) else round((new - consensus) / abs(consensus) * 100, 4),
        direction="unknown" if old is None or new is None else "increase" if new > old else "decrease" if new < old else "unchanged",
        evidence=(RevisionEvidence(1, ("block-1",)),),
        extraction_method="synthetic",
        confidence="high",
        warnings=warnings,
    )


def revisions(*rows: EstimateRevision, status: str = "revisions_found") -> RevisionResult:
    return RevisionResult(status, DOCUMENT_ID, "corpus/synthetic.pdf", (1,), ("block-1",), tuple(rows), ())


def rationale(
    clarity: str = "clear",
    *,
    context: str = "results_review",
    management: bool = False,
    first_read: bool = True,
) -> RationaleResult:
    extraction = RationaleExtraction(
        rationale_clarity=clarity,
        drivers=(
            Driver("Higher prices increased revenue", ("revenue",), ("FY2026E",), "pricing", ("block-1",), "explicit", "high"),
        ) if clarity != "unclear" else (),
        why_now=GroundedClaim("Published after results", ("block-2",), "high") if context != "not_given" else None,
        report_context=context,
        context_evidence_block_ids=("block-2",) if context != "not_given" else (),
        management_contact="true" if management else "unknown",
        management_evidence_block_ids=("block-3",) if management else (),
        people_met=(PersonMet("Jane Smith", "Chief Financial Officer", ("block-3",)),) if management else (),
        one_line_takeaway=GroundedClaim("Pricing supports the earnings outlook", ("block-1",), "high"),
        jargon_definitions=(),
        important_first_read_items=(GroundedClaim("Rating changed to Buy", ("block-4",), "high"),) if first_read else (),
        warnings=(),
    )
    return RationaleResult("interpreted", DOCUMENT_ID, "synthetic.pdf", "revisions_found", (), (), extraction, 4, 200, ())


def citation(key: str, index: int) -> CitationRecord:
    return CitationRecord(
        f"cit-{index:024x}", DOCUMENT_ID, "synthetic.pdf", 100, "1" * 64,
        1, 600, 800, ("block-1",), ((1, 1, 2, 2),), key, key,
        f"http://127.0.0.1:8765/citation/cit-{index:024x}#evidence-target",
        "valid", (),
    )


def citations(*keys: str, failed: int = 0) -> CitationBuildResult:
    return CitationBuildResult(DOCUMENT_ID, "synthetic.pdf", tuple(citation(key, index) for index, key in enumerate(keys, 1)), failed, ())


def row_citations(count: int, *extra_keys: str) -> CitationBuildResult:
    keys = tuple(f"revision:{index}:evidence:1" for index in range(1, count + 1))
    return citations(*keys, *extra_keys)


def metadata(*, analyst: bool = True, title: str | None = "Synthetic Company: Better pricing") -> ReportMetadata:
    analysts = (AnalystMetadata("Alex Example", "Research analyst", "alex@example.test", ("block-5",)),) if analyst else ()
    warnings = () if analyst and title else tuple(item for item, missing in (("report_title_not_identified", title is None), ("analyst_not_identified", not analyst)) if missing)
    return ReportMetadata(title, ("block-title",) if title else (), None, analysts, warnings)


class BriefRenderingTests(unittest.TestCase):
    def complete(self, *, include_visualization: bool = True):
        result = revisions(
            revision("eps", "FY2027E", old=1.2, new=1.3, consensus=1.1),
            revision("revenue", "FY2026E", old=100, new=110, consensus=105, unit="EURm"),
        )
        built_citations = citations(
            "metadata:title", "metadata:analyst:1", "revision:1:evidence:1",
            "revision:2:evidence:1", "rationale:driver:1", "rationale:why_now",
            "rationale:context", "rationale:takeaway", "rationale:first_read:1",
        )
        return ResearchBriefBuilder().build(
            ticker="ABC LN", broker="Example Broker", report_date="2026-06-22",
            metadata=metadata(), revisions=result, rationale=rationale(),
            citations=built_citations, include_visualization=include_visualization,
        )

    def test_complete_brief_order_formats_citations_and_no_empty_sections(self) -> None:
        brief = self.complete()
        markdown = render_markdown(brief)
        headings = ["# Synthetic", "## What changed", "## Why it changed", "## Estimate picture", "## Important", "## Source"]
        positions = [markdown.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("[source](http://127.0.0.1", markdown)
        self.assertIn("Alex Example", markdown)
        self.assertNotIn("## Warnings", markdown)
        self.assertEqual(json.loads(brief.to_json())["ticker"], "ABC LN")
        text = render_text(brief)
        self.assertNotIn("# ", text)
        self.assertIn("<http://127.0.0.1", text)

    def test_no_revisions_has_warning_and_does_not_print_empty_change_section(self) -> None:
        brief = ResearchBriefBuilder().build(
            ticker="ABC LN", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(status="no_revisions"), rationale=rationale(first_read=False),
            citations=citations("metadata:title", "rationale:takeaway"),
        )
        markdown = render_markdown(brief)
        self.assertNotIn("## What changed", markdown)
        self.assertIn("no estimate revisions found", markdown)
        self.assertNotIn("## Important first-read items", markdown)

    def test_revision_without_consensus_uses_missing_symbol(self) -> None:
        brief = ResearchBriefBuilder().build(
            ticker="ABC LN", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(revision(consensus=None)), rationale=rationale(), citations=citations("revision:1:evidence:1"),
        )
        self.assertIn("| — | — | — |", render_markdown(brief))

    def test_deterministic_analyst_friendly_order_and_multiple_periods(self) -> None:
        brief = ResearchBriefBuilder().build(
            ticker="ABC LN", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(
                revision("eps", "FY2027E"), revision("ebitda", "FY2026E", unit="EURm"),
                revision("revenue", "FY2028E", unit="EURm"), revision("eps", "FY2026E"),
            ), rationale=rationale(), citations=row_citations(4),
        )
        self.assertEqual([(row.metric, row.fiscal_period) for row in brief.revision_rows], [
            ("revenue", "FY2028E"), ("ebitda", "FY2026E"), ("eps", "FY2026E"), ("eps", "FY2027E")
        ])

    def test_percentage_point_margin_is_not_rendered_as_percentage_revision(self) -> None:
        row = revision("ebit_margin", "FY2026E", old=10, new=12, consensus=None, unit="%", stated_pp=2)
        brief = ResearchBriefBuilder().build(
            ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(row), rationale=rationale(), citations=row_citations(1),
        )
        self.assertIn("+2pp", render_markdown(brief))
        self.assertNotIn("+20%", render_markdown(brief))

    def test_only_material_arithmetic_warnings_are_rendered(self) -> None:
        row = revision(
            warnings=("stated_calculated_revision_mismatch", "old_value_unresolved")
        )
        brief = ResearchBriefBuilder().build(
            ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(row), rationale=rationale(), citations=row_citations(1),
        )
        markdown = render_markdown(brief)
        self.assertIn("Material arithmetic warnings", markdown)
        self.assertIn("stated calculated revision mismatch", markdown)
        self.assertNotIn("old value unresolved", markdown)

    def test_long_metric_name_and_row_cap_are_safe(self) -> None:
        rows = tuple(revision(f"very_long_metric_name_{index}", f"FY20{26 + index}E") for index in range(15))
        brief = ResearchBriefBuilder(max_revision_rows=8).build(
            ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(*rows), rationale=rationale(), citations=row_citations(15),
        )
        self.assertEqual(len(brief.revision_rows), 8)
        self.assertEqual(brief.omitted_revision_rows, 7)
        self.assertIn("additional revision rows omitted:7", render_markdown(brief))

    def test_clear_partial_unclear_and_context_not_given(self) -> None:
        for clarity in ("clear", "partial", "unclear"):
            with self.subTest(clarity=clarity):
                brief = ResearchBriefBuilder().build(
                    ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(),
                    revisions=revisions(revision()), rationale=rationale(clarity, context="not_given"),
                    citations=row_citations(1, "rationale:driver:1"),
                )
                joined = " ".join(brief.rationale_paragraphs)
                self.assertIn("Publication context is not given", joined)
                if clarity == "unclear":
                    self.assertIn("does not clearly explain", joined)
                if clarity == "partial":
                    self.assertIn("partially explains", joined)
                self.assertLessEqual(len(brief.rationale_paragraphs), 2)

    def test_management_meeting_names_explicit_participant(self) -> None:
        brief = ResearchBriefBuilder().build(
            ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(revision()), rationale=rationale(context="management_meeting", management=True),
            citations=citations("rationale:context", "rationale:management"),
        )
        self.assertIn("Jane Smith (Chief Financial Officer)", " ".join(brief.rationale_paragraphs))

    def test_rating_change_is_first_read_item(self) -> None:
        self.assertIn("Rating changed to Buy", render_markdown(self.complete()))

    def test_missing_citations_and_partial_pipeline_failure_are_material_warnings(self) -> None:
        brief = ResearchBriefBuilder().build(
            ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(analyst=False),
            revisions=revisions(revision()), rationale=None, citations=citations(failed=2),
        )
        self.assertIn("rationale_not_available", brief.warnings)
        self.assertIn("citation_requests_failed:2", brief.warnings)
        self.assertIn("analyst_not_identified", brief.warnings)
        self.assertEqual(brief.revision_rows, ())
        self.assertIsNone(brief.report_title)
        self.assertIn("uncited_revision_rows_omitted:1", brief.warnings)

    def test_invalid_citations_and_cross_report_metadata_are_rejected(self) -> None:
        invalid = replace(citation("revision:1:evidence:1", 1), validation_status="invalid")
        brief = ResearchBriefBuilder().build(
            ticker="ABC", broker="Broker", report_date="20260622", metadata=metadata(),
            revisions=revisions(revision()), rationale=None,
            citations=CitationBuildResult(DOCUMENT_ID, "synthetic.pdf", (invalid,), 0, ()),
        )
        self.assertEqual(brief.revision_rows, ())
        self.assertIn("uncited_structured_facts_omitted:2", brief.warnings)
        mismatched = replace(metadata(), document_id="sha256:" + "2" * 64)
        with self.assertRaisesRegex(ValueError, "metadata and revisions"):
            ResearchBriefBuilder().build(
                ticker="ABC", broker="Broker", report_date="20260622", metadata=mismatched,
                revisions=revisions(revision()), rationale=None, citations=row_citations(1),
            )

    def test_no_visualization_flag_at_builder_level(self) -> None:
        self.assertEqual(self.complete(include_visualization=False).estimate_visualizations, ())


class VisualizationTests(unittest.TestCase):
    def row(self, old, new, consensus, unit="EUR/share"):
        return BriefRevisionRow("eps", (), "FY2026E", old, new, None, None, consensus, None, None, unit, "unknown", (), ())

    def test_old_new_consensus_scale_is_consistent(self) -> None:
        visual = make_estimate_visualization(self.row(1, 2, 1.5))
        self.assertIsNotNone(visual)
        self.assertEqual(len(visual.lines), 4)
        self.assertIn("EUR/share", visual.plain_text)

    def test_negative_and_zero_values_are_safe(self) -> None:
        visual = make_estimate_visualization(self.row(-2, 0, 1))
        self.assertIsNotNone(visual)
        self.assertTrue(all("│" in line for line in visual.lines[1:]))
        self.assertIn("-2", visual.plain_text)
        self.assertIn("  0", visual.plain_text)

    def test_visualization_omits_single_equal_nonfinite_or_unitless_values(self) -> None:
        self.assertIsNone(make_estimate_visualization(self.row(1, None, None)))
        self.assertIsNone(make_estimate_visualization(self.row(1, 1, None)))
        self.assertIsNone(make_estimate_visualization(self.row(1, float("nan"), None)))
        self.assertIsNone(make_estimate_visualization(self.row(1, 2, None, unit=None)))


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_document(self, lines: list[tuple[float, float, str, int]]):
        path = self.root / "metadata.pdf"
        source = fitz.open()
        page = source.new_page(width=600, height=800)
        for x, y, text, size in lines:
            page.insert_text((x, y), text, fontsize=size)
        source.save(path)
        source.close()
        return PdfEvidenceExtractor().extract(path)

    def test_title_is_cited_and_email_name_is_not_inferred(self) -> None:
        document = self.make_document([
            (40, 45, "Synthetic Company: Pricing improves", 18),
            (40, 65, "19 June 2026", 10),
            (40, 80, "anonymous.analyst@example.test", 10),
        ])
        result = ReportMetadataExtractor().extract(document)
        self.assertEqual(result.title, "Synthetic Company: Pricing improves")
        self.assertTrue(result.title_evidence_block_ids)
        self.assertEqual(result.internal_publication_date, "2026-06-19")
        self.assertTrue(result.internal_publication_date_evidence_block_ids)
        self.assertEqual(result.analysts, ())
        self.assertIn("analyst_not_identified", result.warnings)

    def test_explicit_name_role_and_email_are_retained(self) -> None:
        path = self.root / "analyst.pdf"
        source = fitz.open()
        page = source.new_page(width=600, height=800)
        page.insert_text((40, 45), "Synthetic Company: Pricing improves", fontsize=18)
        page.insert_textbox(
            fitz.Rect(40, 80, 350, 150),
            "Alex Example\nSenior Research Analyst\nalex@example.test",
            fontsize=10,
        )
        source.save(path)
        source.close()
        result = ReportMetadataExtractor().extract(PdfEvidenceExtractor().extract(path))
        self.assertEqual(result.analysts[0].name, "Alex Example")
        self.assertEqual(result.analysts[0].email, "alex@example.test")
        self.assertIn("Analyst", result.analysts[0].role)


class BriefCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        self.cache = self.root / "cache"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_report(self, digest: str, title: str = "Synthetic Company: Price-led growth") -> Path:
        path = self.corpus / f"20260622_Example Broker_{digest}.pdf"
        document = fitz.open()
        page = document.new_page(width=700, height=800)
        page.insert_text((40, 40), title, fontsize=18)
        page.insert_text((40, 75), "Bloomberg: ABC LN")
        page.insert_text((40, 115), "We raise FY2026E revenue from EUR 100m to EUR 110m due to higher prices.")
        document.save(path)
        document.close()
        return path

    def test_markdown_json_text_and_no_visualization_cli(self) -> None:
        self.write_report("a" * 32)
        for output_format in ("markdown", "json", "text"):
            with self.subTest(output_format=output_format):
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    code = main([
                        "brief", "--ticker", "ABC LN", "--date", "2026-06-22", "--broker", "Example Broker",
                        "--corpus", str(self.corpus), "--cache-dir", str(self.cache), "--no-model",
                        "--no-visualization", "--format", output_format,
                    ])
                self.assertEqual(code, 0, errors.getvalue())
                self.assertIn("ABC LN", output.getvalue())
                self.assertNotIn(str(self.root), output.getvalue())
                if output_format == "json":
                    self.assertEqual(json.loads(output.getvalue())["estimate_visualizations"], [])

    def test_ambiguous_retrieval_stops_before_brief_rendering(self) -> None:
        self.write_report("a" * 32, "Synthetic Company: First report")
        self.write_report("b" * 32, "Synthetic Company: Second report")
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main([
                "brief", "--ticker", "ABC LN", "--date", "20260622", "--broker", "Example Broker",
                "--corpus", str(self.corpus), "--cache-dir", str(self.cache), "--no-model",
            ])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output.getvalue())["status"], "ambiguous")
        self.assertNotIn("What changed", output.getvalue())

    def test_brief_does_not_accept_page_limited_extraction(self) -> None:
        parser_output = io.StringIO()
        with redirect_stdout(parser_output):
            with self.assertRaises(SystemExit):
                main([
                    "brief", "--ticker", "ABC LN", "--date", "20260622",
                    "--broker", "Example Broker", "--pages", "1",
                ])


class RealReportBriefEvaluationTests(unittest.TestCase):
    def test_all_rendered_citations_open_for_three_real_partial_briefs(self) -> None:
        corpus = Path("corpus")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        cases = [
            case
            for case in json.loads(Path("tests/evaluation_cases.json").read_text(encoding="utf-8"))
            if case["broker"] in {"BofA Global Research", "Nordea Equity Research", "Kepler Cheuvreux"}
        ]
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "citations"
            citation_ids: set[str] = set()
            for case in cases:
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    code = main([
                        "brief", "--ticker", case["ticker"], "--date", case["date"],
                        "--broker", case["broker"], "--corpus", str(corpus),
                        "--cache-dir", str(cache), "--no-model", "--format", "json",
                    ])
                self.assertEqual(code, 0, errors.getvalue())
                payload = json.loads(output.getvalue())
                if payload["primary_citation"]:
                    citation_ids.add(payload["primary_citation"]["citation_id"])
                for row in payload["revision_rows"]:
                    citation_ids.update(item["citation_id"] for item in row["citations"])
                for analyst in payload["analysts"]:
                    citation_ids.update(item["citation_id"] for item in analyst["citations"])
            server = make_server(corpus, cache, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                self.assertGreater(len(citation_ids), 3)
                for citation_id in citation_ids:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    connection.request("GET", f"/citation/{citation_id}")
                    response = connection.getresponse()
                    response.read()
                    connection.close()
                    self.assertEqual(response.status, 200)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_eleven_real_brief_commands_complete_in_no_model_mode(self) -> None:
        corpus = Path("corpus")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        cases = json.loads(Path("tests/evaluation_cases.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "citations"
            for case in cases:
                with self.subTest(filename=case["expected_filename"]):
                    output, errors = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = main([
                            "brief", "--ticker", case["ticker"], "--date", case["date"],
                            "--broker", case["broker"], "--corpus", str(corpus),
                            "--cache-dir", str(cache), "--no-model", "--format", "json",
                        ])
                    self.assertEqual(code, 0, errors.getvalue())
                    payload = json.loads(output.getvalue())
                    self.assertEqual(payload["ticker"], case["ticker"])
                    self.assertIn("semantic_interpretation_skipped", payload["warnings"])

    def test_eleven_real_reports_render_safe_partial_briefs_with_valid_row_citations(self) -> None:
        corpus = Path("corpus")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        cases = json.loads(Path("tests/evaluation_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(filename=case["expected_filename"]):
                path = corpus / case["expected_filename"]
                document = PdfEvidenceExtractor().extract(path, source_root=corpus)
                metadata_result = ReportMetadataExtractor().extract(document)
                revision_result = RevisionExtractor().extract(document, broker=case["broker"])
                rationale_result = RationaleExtractor().extract(
                    document, revisions=revision_result, no_model=True, broker=case["broker"]
                )
                requests = list(requests_from_metadata(document.document_id, metadata_result))
                requests.extend(requests_from_revisions(revision_result))
                citation_result = CitationBuilder(corpus).build(document, path, requests)
                brief = ResearchBriefBuilder().build(
                    ticker=case["ticker"], broker=case["broker"], report_date=case["date"],
                    metadata=metadata_result, revisions=revision_result,
                    rationale=rationale_result, citations=citation_result,
                )
                rendered = render_markdown(brief)
                self.assertNotIn(str(corpus.resolve()), rendered)
                self.assertNotIn("## Important first-read items\n\n\n", rendered)
                self.assertEqual(citation_result.failed_requests, 0)
                self.assertTrue(all(row.citations for row in brief.revision_rows))


if __name__ == "__main__":
    unittest.main()
