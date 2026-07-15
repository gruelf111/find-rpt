from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import fitz
from pypdf import PdfWriter

from find_rpt.cli import main
from find_rpt.evidence import (
    EncryptedPdfError,
    InvalidPageRangeError,
    NoUsableTextError,
    PdfEvidenceExtractor,
    UnreadablePdfError,
)


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "sample.pdf"
        document = fitz.open()
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 40), "First page heading")
        page.insert_text((30, 80), "First page evidence")
        page = document.new_page(width=500, height=600)
        page.insert_text((40, 50), "Second page evidence")
        document.save(self.path)
        document.close()
        self.extractor = PdfEvidenceExtractor()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_schema_coordinates_and_source_text(self) -> None:
        evidence = self.extractor.extract(self.path)
        self.assertEqual(evidence.page_count, 2)
        self.assertEqual([page.page_number for page in evidence.pages], [1, 2])
        with fitz.open(self.path) as source:
            for page in evidence.pages:
                self.assertGreater(page.width, 0)
                self.assertGreater(page.height, 0)
                source_text = source[page.page_number - 1].get_text()
                for block in page.blocks:
                    x0, y0, x1, y1 = block.bbox
                    self.assertTrue(0 <= x0 < x1 <= page.width)
                    self.assertTrue(0 <= y0 < y1 <= page.height)
                    self.assertIn(block.text, source_text)
                    self.assertTrue(block.words)
                    self.assertTrue(all(word.text in block.text for word in block.words))

    def test_ids_ordering_and_json_are_repeatable(self) -> None:
        first = self.extractor.extract(self.path)
        second = self.extractor.extract(self.path)
        self.assertEqual(first, second)
        ids = [block.block_id for page in first.pages for block in page.blocks]
        self.assertEqual(ids, [block.block_id for page in second.pages for block in page.blocks])
        self.assertTrue(all(identifier.startswith("p") for identifier in ids))
        self.assertTrue(first.document_id.startswith("sha256:"))
        self.assertNotIn(str(self.root), first.to_json())

    def test_page_range_filtering(self) -> None:
        evidence = self.extractor.extract(self.path, pages="2")
        self.assertEqual(evidence.page_count, 2)
        self.assertEqual([page.page_number for page in evidence.pages], [2])
        with self.assertRaises(InvalidPageRangeError):
            self.extractor.extract(self.path, pages="0-2")
        with self.assertRaises(InvalidPageRangeError):
            self.extractor.extract(self.path, pages="3")
        with self.assertRaises(InvalidPageRangeError):
            self.extractor.extract(self.path, pages="2-1")

    def test_malformed_unreadable_encrypted_and_textless(self) -> None:
        malformed = self.root / "bad.pdf"
        malformed.write_bytes(b"not a private report")
        with self.assertRaises(UnreadablePdfError):
            self.extractor.extract(malformed)

        encrypted = self.root / "encrypted.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("password")
        with encrypted.open("wb") as output:
            writer.write(output)
        with self.assertRaises(EncryptedPdfError):
            self.extractor.extract(encrypted)

        blank = self.root / "blank.pdf"
        document = fitz.open()
        document.new_page()
        document.save(blank)
        document.close()
        with self.assertRaises(NoUsableTextError):
            self.extractor.extract(blank)

        with self.assertRaises(UnreadablePdfError):
            self.extractor.extract(self.root / "missing.pdf")

    def test_direct_path_cli_returns_json(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["evidence", "--pdf-path", str(self.path), "--pages", "1"])
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual([page["page_number"] for page in payload["pages"]], [1])


class BrokerLayoutEvidenceTests(unittest.TestCase):
    CASES = (
        "20260511_ABG Sundal Collier_0566b42f1d8750853347bf485216f764.pdf",
        "20260511_BofA Global Research_003c2de68007dc1805c646be0e369535.pdf",
        "20260511_JP Morgan_1666c9de5c0a393daa6484be9f484839.pdf",
        "20260511_Nordea Equity Research_09830ec754626864bb0aa1f8c9f2f71f.pdf",
        "20260622_Kepler Cheuvreux_098dda895ab76d9a8e9b4c3a3408485a.pdf",
    )

    def test_five_real_layouts_have_valid_repeatable_evidence(self) -> None:
        corpus = Path("corpus")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        extractor = PdfEvidenceExtractor()
        for filename in self.CASES:
            with self.subTest(filename=filename):
                path = corpus / filename
                first = extractor.extract(path)
                second = extractor.extract(path)
                self.assertEqual(first, second)
                self.assertGreater(sum(len(page.blocks) for page in first.pages), 0)
                with fitz.open(path) as source:
                    for page in first.pages:
                        source_text = source[page.page_number - 1].get_text()
                        for block in page.blocks:
                            self.assertIn(block.text, source_text)
                            x0, y0, x1, y1 = block.bbox
                            self.assertTrue(0 <= x0 < x1 <= page.width)
                            self.assertTrue(0 <= y0 < y1 <= page.height)

    def test_locator_cli_selects_then_extracts_without_writing(self) -> None:
        if not Path("corpus").is_dir():
            self.skipTest("local corpus is not available")
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(
                [
                    "evidence",
                    "--ticker", "SHA0 GY",
                    "--date", "2026-06-22",
                    "--broker", "Kepler Cheuvreux",
                    "--pages", "1",
                    "--format", "json",
                ]
            )
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["retrieval"]["status"], "found")
        self.assertEqual([page["page_number"] for page in payload["evidence"]["pages"]], [1])


if __name__ == "__main__":
    unittest.main()
