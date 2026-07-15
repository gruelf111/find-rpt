from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import fitz

from find_rpt.cli import main
from find_rpt.evidence import PdfEvidenceExtractor
from find_rpt.revisions import (
    ROUNDING_TOLERANCE_PCT,
    RevisionExtractor,
    calculate_revision_pct,
    normalize_fiscal_period,
    normalize_metric,
    normalize_unit,
    parse_value,
)


class RevisionCalculationTests(unittest.TestCase):
    def test_positive_negative_and_zero_old_values(self) -> None:
        self.assertEqual(calculate_revision_pct(100, 110), (10.0, None))
        self.assertEqual(calculate_revision_pct(-100, -80), (20.0, None))
        self.assertEqual(calculate_revision_pct(-100, -120), (-20.0, None))
        self.assertEqual(
            calculate_revision_pct(0, 10),
            (None, "zero_old_value_no_relative_revision"),
        )

    def test_unit_normalization_preserves_scale_basis_and_currency(self) -> None:
        self.assertEqual(normalize_unit("EUR 12.5m"), "EURm")
        self.assertEqual(normalize_unit("$3.20/share"), "USD/share")
        self.assertEqual(normalize_unit("1.5bn"), "bn")
        self.assertEqual(normalize_unit("25bps"), "basis_points")
        self.assertEqual(normalize_unit("1.2pp"), "percentage_points")
        self.assertEqual(normalize_unit("12.0%"), "%")
        self.assertEqual(parse_value("(€1.25bn)").value, -1.25)
        for state in ("NA", "n.m.", "ns"):
            with self.subTest(state=state):
                self.assertIsNone(parse_value(state).value)

    def test_metric_qualifiers_and_period_normalization(self) -> None:
        self.assertEqual(normalize_metric("adjusted diluted EPS"), ("eps", ("adjusted", "diluted")))
        self.assertEqual(normalize_metric("reported EBIT margin"), ("ebit_margin", ("reported",)))
        self.assertEqual(normalize_metric("restated EPS"), ("eps", ("restated",)))
        self.assertEqual(normalize_metric("EPS (rep.)"), ("eps", ("reported",)))
        self.assertEqual(normalize_metric("DPS ord."), ("dps", ("ordinary",)))
        self.assertEqual(normalize_metric("Basic EPS"), ("eps", ("basic",)))
        self.assertEqual(normalize_fiscal_period("FY26E"), ("FY2026E", "fiscal"))
        self.assertEqual(normalize_fiscal_period("CY2027"), ("CY2027", "calendar"))
        self.assertEqual(normalize_fiscal_period("03/27e"), ("FY03/2027E", "fiscal"))
        self.assertEqual(normalize_fiscal_period("Q1 2028E"), ("Q1 2028E", "fiscal"))
        self.assertEqual(normalize_fiscal_period("1H27E"), ("H1 2027E", "fiscal"))
        self.assertEqual(normalize_fiscal_period("2029E"), ("2029E", "unspecified"))


class RevisionExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_pdf(self, name: str, lines: list[tuple[float, float, str]]) -> Path:
        path = self.root / name
        document = fitz.open()
        page = document.new_page(width=700, height=800)
        for x, y, text in lines:
            page.insert_text((x, y), text)
        document.save(path)
        document.close()
        return path

    def extract(self, path: Path):
        evidence = PdfEvidenceExtractor().extract(path)
        return evidence, RevisionExtractor().extract(evidence)

    def test_prose_old_new_consensus_arithmetic_and_evidence(self) -> None:
        path = self.make_pdf(
            "prose.pdf",
            [(40, 60, "We raised adjusted diluted EPS FY2026E from EUR 2.00 to EUR 2.20 by 10%, consensus of EUR 2.10.")],
        )
        evidence, result = self.extract(path)
        self.assertEqual(result.status, "revisions_found")
        revision = result.revisions[0]
        self.assertEqual(revision.metric, "eps")
        self.assertEqual(revision.metric_qualifiers, ("adjusted", "diluted"))
        self.assertEqual(revision.fiscal_period, "FY2026E")
        self.assertEqual((revision.old_value, revision.new_value), (2.0, 2.2))
        self.assertEqual(revision.calculated_revision_pct, 10.0)
        self.assertEqual(revision.stated_revision_pct, 10.0)
        self.assertEqual(revision.consensus_value, 2.1)
        self.assertAlmostEqual(revision.old_vs_consensus_pct, -4.7619)
        self.assertAlmostEqual(revision.new_vs_consensus_pct, 4.7619)
        valid_ids = {block.block_id for page in evidence.pages for block in page.blocks}
        self.assertTrue(set(revision.evidence[0].block_ids).issubset(valid_ids))

    def test_percentage_points_are_separate_from_relative_percentage(self) -> None:
        path = self.make_pdf(
            "margin.pdf",
            [(40, 60, "We revised FY2026E adjusted EBIT margin from 10% to 12% by 2pp.")],
        )
        _, result = self.extract(path)
        revision = result.revisions[0]
        self.assertEqual(revision.unit, "%")
        self.assertEqual(revision.calculated_change_pp, 2.0)
        self.assertEqual(revision.stated_change_pp, 2.0)
        self.assertEqual(revision.calculated_revision_pct, 20.0)

        basis_points = self.make_pdf(
            "basis-points.pdf",
            [(40, 60, "We revised FY2027E cost of risk from 25bps to 30bps by 5bps.")],
        )
        _, result = self.extract(basis_points)
        revision = result.revisions[0]
        self.assertEqual(revision.unit, "basis_points")
        self.assertEqual(revision.stated_change_pp, 0.05)
        self.assertEqual(revision.calculated_change_pp, 0.05)

    def test_rounding_mismatch_and_zero_denominator_warnings(self) -> None:
        path = self.make_pdf(
            "warnings.pdf",
            [
                (40, 60, "We raised revenue FY2026E from EUR 100m to EUR 110m by 8%."),
                (40, 90, "We revised EBIT FY2027E from EUR 0m to EUR 5m."),
            ],
        )
        _, result = self.extract(path)
        by_period = {revision.fiscal_period: revision for revision in result.revisions}
        self.assertIn("stated_calculated_revision_mismatch", by_period["FY2026E"].warnings)
        self.assertGreater(abs(10 - 8), ROUNDING_TOLERANCE_PCT)
        self.assertIn("zero_old_value_no_relative_revision", by_period["FY2027E"].warnings)

    def test_mismatched_units_and_directional_consensus_are_not_invented(self) -> None:
        path = self.make_pdf(
            "unit-mismatch.pdf",
            [
                (40, 60, "We revised revenue FY2030E from EUR 100m to USD 0.2bn."),
                (40, 90, "We raised EPS FY2031E from EUR 2.00 to EUR 2.10, above consensus."),
            ],
        )
        _, result = self.extract(path)
        by_period = {revision.fiscal_period: revision for revision in result.revisions}
        mismatch = by_period["FY2030E"]
        self.assertIsNone(mismatch.unit)
        self.assertIsNone(mismatch.calculated_revision_pct)
        self.assertIn("old_new_unit_mismatch", mismatch.warnings)
        self.assertIsNone(by_period["FY2031E"].consensus_value)

    def test_old_new_table_and_revision_matrix(self) -> None:
        path = self.make_pdf(
            "tables.pdf",
            [
                (40, 40, "Estimate revisions"),
                (40, 70, "Metric"), (250, 70, "Previous"), (350, 70, "Current"),
                (450, 70, "Consensus"), (550, 70, "Change"),
                (40, 100, "Adjusted EPS FY2026E"), (250, 100, "EUR 2.00"),
                (350, 100, "EUR 2.20"), (450, 100, "EUR 2.10"), (550, 100, "+10%"),
                (40, 180, "Forecast changes"),
                (250, 210, "FY2027E"), (350, 210, "FY2028E"),
                (40, 240, "Revenue"), (250, 240, "+3%"), (350, 240, "-2%"),
            ],
        )
        _, result = self.extract(path)
        methods = {revision.extraction_method for revision in result.revisions}
        self.assertIn("table_old_new", methods)
        self.assertIn("table_revision_matrix", methods)
        table = next(revision for revision in result.revisions if revision.extraction_method == "table_old_new")
        self.assertEqual((table.old_value, table.new_value, table.consensus_value), (2.0, 2.2, 2.1))
        matrix = [revision for revision in result.revisions if revision.extraction_method == "table_revision_matrix"]
        self.assertEqual(
            {item.fiscal_period for item in matrix},
            {"FY2027E", "FY2028E"},
            result.to_json(),
        )
        self.assertTrue(all(item.old_value is None and item.new_value is None for item in matrix))

    def test_separate_consensus_table_joins_only_exact_page_metric_period_and_unit(self) -> None:
        path = self.make_pdf(
            "consensus-table.pdf",
            [
                (40, 40, "Key changes"),
                (160, 70, "(EUR)"), (250, 70, "Previous"), (350, 70, "Current"),
                (40, 100, "EPS 2026E"), (250, 100, "2.00"), (350, 100, "2.20"),
                (40, 125, "Reported EPS 2027E"), (250, 125, "2.10"), (350, 125, "2.30"),
                (40, 180, "Forecasts"),
                (160, 210, "(EUR)"), (250, 210, "2026E"), (350, 210, "2027E"),
                (40, 240, "Consensus EPS"), (250, 240, "2.10"), (350, 240, "2.25"),
            ],
        )
        _, result = self.extract(path)
        by_period = {revision.fiscal_period: revision for revision in result.revisions}
        joined = by_period["2026E"]
        self.assertEqual(joined.consensus_value, 2.1)
        self.assertAlmostEqual(joined.old_vs_consensus_pct, -4.7619)
        self.assertAlmostEqual(joined.new_vs_consensus_pct, 4.7619)
        self.assertEqual(len(joined.evidence), 2)
        self.assertIsNone(by_period["2027E"].consensus_value)

    def test_no_revisions_and_unresolved_candidates_are_distinct(self) -> None:
        no_revision = self.make_pdf("none.pdf", [(40, 60, "Company overview and historical performance")])
        _, result = self.extract(no_revision)
        self.assertEqual(result.status, "no_revisions")

        unresolved = self.make_pdf(
            "unresolved.pdf",
            [(40, 60, "Estimate revisions"), (40, 90, "Old New FY2026E adjusted EPS n.m.")],
        )
        _, result = self.extract(unresolved)
        self.assertEqual(result.status, "candidates_unresolved")
        self.assertEqual(result.revisions, ())

        disclosure = self.make_pdf(
            "disclosure.pdf",
            [(40, 60, "Valuation methodology describes EPS and changes to ratings over FY2026E.")],
        )
        _, result = self.extract(disclosure)
        self.assertEqual(result.status, "no_revisions")

        legal_disclosure = self.make_pdf(
            "legal-disclosure.pdf",
            [(40, 60, "Under no circumstances is to be construed as an offer. Past performance is not a guide. Revenue estimates may change.")],
        )
        _, result = self.extract(legal_disclosure)
        self.assertEqual(result.status, "no_revisions")

    def test_repeatability_and_direct_cli_json(self) -> None:
        path = self.make_pdf(
            "repeatable.pdf",
            [(40, 60, "We cut target price from USD 50 to USD 45 by 10%.")],
        )
        evidence = PdfEvidenceExtractor().extract(path)
        first = RevisionExtractor().extract(evidence)
        second = RevisionExtractor().extract(evidence)
        self.assertEqual(first, second)

        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["revisions", "--pdf-path", str(path), "--format", "json"])
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "revisions_found")
        self.assertNotIn(str(self.root), output.getvalue())


class RealReportRevisionEvaluationTests(unittest.TestCase):
    def test_eleven_real_reports_are_repeatable_and_evidence_resolves(self) -> None:
        corpus = Path("corpus")
        cases_path = Path("tests/revision_evaluation_cases.json")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        evidence_extractor = PdfEvidenceExtractor()
        revision_extractor = RevisionExtractor()
        for case in cases:
            path = corpus / case["filename"]
            with self.subTest(filename=path.name):
                evidence = evidence_extractor.extract(path)
                first = revision_extractor.extract(evidence, broker=case["broker"])
                second = revision_extractor.extract(evidence, broker=case["broker"])
                self.assertEqual(first, second)
                self.assertEqual(first.status, case["expected_status"])
                self.assertEqual(len(first.revisions), case["expected_revision_count"])
                blocks = {
                    (page.page_number, block.block_id)
                    for page in evidence.pages
                    for block in page.blocks
                }
                for revision in first.revisions:
                    for reference in revision.evidence:
                        self.assertTrue(reference.block_ids)
                        self.assertTrue(
                            all((reference.page_number, block_id) in blocks for block_id in reference.block_ids)
                        )
                    if (
                        revision.old_value is not None
                        and revision.new_value is not None
                        and "old_new_unit_mismatch" not in revision.warnings
                    ):
                        expected, warning = calculate_revision_pct(revision.old_value, revision.new_value)
                        self.assertEqual(revision.calculated_revision_pct, expected)
                        if warning:
                            self.assertIn(warning, revision.warnings)

    def test_locator_cli_selects_one_report_then_extracts_revisions(self) -> None:
        if not Path("corpus").is_dir():
            self.skipTest("local corpus is not available")
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(
                [
                    "revisions",
                    "--ticker", "SHA0 GY",
                    "--date", "2026-06-22",
                    "--broker", "Kepler Cheuvreux",
                    "--format", "json",
                ]
            )
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["retrieval"]["status"], "found")
        self.assertEqual(payload["revisions"]["status"], "revisions_found")


if __name__ == "__main__":
    unittest.main()
