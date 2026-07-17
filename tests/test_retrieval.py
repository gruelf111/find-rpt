from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from find_rpt.cli import render_text
from find_rpt.retrieval import RetrievalEngine, normalize_broker, normalize_date, normalize_ticker


class FakeInspector:
    def __init__(self, pages: dict[str, list[str]], errors: dict[str, Exception] | None = None):
        self.pages = pages
        self.errors = errors or {}
        self.calls: list[tuple[str, int]] = []

    def extract_page(self, path: Path, page_index: int) -> str | None:
        self.calls.append((path.name, page_index))
        if path.name in self.errors:
            raise self.errors[path.name]
        pages = self.pages.get(path.name, [])
        return pages[page_index] if page_index < len(pages) else None


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_file(self, broker: str, digest: str) -> str:
        name = f"20260102_{broker}_{digest}.pdf"
        (self.corpus / name).touch()
        return name

    def test_normalization(self) -> None:
        self.assertEqual(normalize_date("2026-01-02"), "20260102")
        self.assertEqual(normalize_broker("J.P. Morgan"), normalize_broker("JP Morgan"))
        self.assertEqual(normalize_ticker("BP/ LN"), normalize_ticker("BP LN"))
        self.assertEqual(normalize_ticker("SHA0 GY"), normalize_ticker("SHA0 GR"))
        self.assertEqual(normalize_ticker("700 HK"), "700 HK")

    def test_malformed_inputs_are_rejected(self) -> None:
        for value in ("2026/01/02", "x2026-01-02", "20260102x"):
            with self.subTest(date=value), self.assertRaises(ValueError):
                normalize_date(value)
        for value in ("ABC", "ABC LN Equity", "ABC 12"):
            with self.subTest(ticker=value), self.assertRaises(ValueError):
                normalize_ticker(value)
        with self.assertRaisesRegex(ValueError, "broker"):
            RetrievalEngine(self.corpus, FakeInspector({})).retrieve("ABC LN", "20260102", "--")

    def test_filename_shortlist_precedes_content_inspection(self) -> None:
        right = self.add_file("J.P. Morgan", "a" * 32)
        wrong_broker = self.add_file("Another Broker", "b" * 32)
        inspector = FakeInspector({right: ["Bloomberg: ABC LN"], wrong_broker: ["Bloomberg: ABC LN"]})
        result = RetrievalEngine(self.corpus, inspector).retrieve("ABC LN", "20260102", "JP Morgan")
        self.assertEqual(result.status, "found")
        self.assertEqual(result.match.filename, right)
        self.assertNotIn((wrong_broker, 0), inspector.calls)

    def test_explicit_field_beats_incidental_body_mention(self) -> None:
        explicit = self.add_file("Broker", "a" * 32)
        incidental = self.add_file("Broker", "b" * 32)
        pages = {
            explicit: ["Company\nBloomberg: ABC LN\nCommentary"],
            incidental: ["Other Company\n" + "background\n" * 50 + "Peer ABC LN performed well"],
        }
        result = RetrievalEngine(self.corpus, FakeInspector(pages)).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "found")
        self.assertEqual(result.match.filename, explicit)

    def test_ticker_value_below_table_header_is_explicit(self) -> None:
        match = self.add_file("Broker", "a" * 32)
        text = "Company\n" + "detail\n" * 50 + "Reuters Bloomberg Exchange Ticker\nABC.L ABC LN LSE ABC"
        result = RetrievalEngine(self.corpus, FakeInspector({match: [text]})).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "found")
        self.assertEqual(result.match.evidence[0].kind, "explicit_bloomberg_field")

    def test_compact_ticker_in_delimited_identifier_row_is_supported(self) -> None:
        match = self.add_file("Broker", "a" * 32)
        result = RetrievalEngine(
            self.corpus, FakeInspector({match: ["Company\nSOIFP|SOIT.PA"]})
        ).retrieve("SOI FP", "20260102", "Broker")
        self.assertEqual(result.status, "found")
        self.assertEqual(result.match.filename, match)
        self.assertEqual(result.match.evidence[0].kind, "header_or_title")

    def test_compact_ticker_is_not_matched_in_ordinary_prose(self) -> None:
        only = self.add_file("Broker", "a" * 32)
        result = RetrievalEngine(
            self.corpus, FakeInspector({only: ["MARGIN improved in the quarter"]})
        ).retrieve("MAR IN", "20260102", "Broker")
        self.assertEqual(result.status, "not_found")

    def test_narrative_bloomberg_mention_is_not_an_explicit_field(self) -> None:
        only = self.add_file("Broker", "a" * 32)
        text = "heading\n" + "detail\n" * 28 + "According to Bloomberg data, peer ABC LN moved"
        result = RetrievalEngine(self.corpus, FakeInspector({only: [text]})).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.candidates[0].evidence[0].kind, "possible_header")

    def test_short_narrative_with_bloomberg_and_ticker_words_is_not_a_field(self) -> None:
        only = self.add_file("Broker", "a" * 32)
        text = "heading\n" + "detail\n" * 28 + "Peer Bloomberg ticker is ABC LN"
        result = RetrievalEngine(self.corpus, FakeInspector({only: [text]})).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "ambiguous")
        self.assertNotEqual(result.candidates[0].evidence[0].kind, "explicit_bloomberg_field")

    def test_unique_header_match_stops_after_page_one(self) -> None:
        match = self.add_file("Broker", "a" * 32)
        other = self.add_file("Broker", "b" * 32)
        inspector = FakeInspector({match: ["Company (ABC LN)"], other: ["Other Company"]})
        result = RetrievalEngine(self.corpus, inspector).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "found")
        self.assertTrue(all(page == 0 for _, page in inspector.calls))

    def test_tied_strong_matches_are_ambiguous(self) -> None:
        first = self.add_file("Broker", "a" * 32)
        second = self.add_file("Broker", "b" * 32)
        pages = {first: ["Bloomberg: ABC LN"], second: ["Ticker: ABC LN"]}
        result = RetrievalEngine(self.corpus, FakeInspector(pages)).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.match)
        self.assertEqual([candidate.filename for candidate in result.candidates[:2]], [first, second])

    def test_weak_match_is_ambiguous(self) -> None:
        only = self.add_file("Broker", "a" * 32)
        text = "heading\n" + "body\n" * 50 + "ABC LN appeared in a peer list"
        result = RetrievalEngine(self.corpus, FakeInspector({only: [text]})).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "ambiguous")

    def test_page_two_is_bounded_fallback(self) -> None:
        match = self.add_file("Broker", "a" * 32)
        inspector = FakeInspector({match: ["No identifier", "Bloomberg: ABC LN", "unused"]})
        result = RetrievalEngine(self.corpus, inspector).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "found")
        self.assertEqual(inspector.calls, [(match, 0), (match, 1)])

    def test_no_filename_candidates_is_not_found(self) -> None:
        result = RetrievalEngine(self.corpus, FakeInspector({})).retrieve(
            "ABC LN", "20260102", "Missing Broker"
        )
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.candidates, [])

    def test_invalid_pdf_is_transparent(self) -> None:
        invalid = self.add_file("Broker", "a" * 32)
        inspector = FakeInspector({}, {invalid: ValueError("not a PDF")})
        result = RetrievalEngine(self.corpus, inspector).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "ambiguous")
        self.assertIn("could not be inspected", result.reason)
        self.assertEqual(result.candidates[0].error, "ValueError: page inspection failed")

    def test_real_inspector_rejects_non_pdf_payload_without_echoing_it(self) -> None:
        invalid = self.add_file("Broker", "a" * 32)
        (self.corpus / invalid).write_bytes(b"private upstream error payload")
        result = RetrievalEngine(self.corpus).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "ambiguous")
        self.assertNotIn("private upstream", result.to_json())

    def test_encrypted_pdf_is_ambiguous_and_error_is_sanitized(self) -> None:
        encrypted = self.add_file("Broker", "a" * 32)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("test-password")
        with (self.corpus / encrypted).open("wb") as output:
            writer.write(output)
        result = RetrievalEngine(self.corpus).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "ambiguous")
        self.assertIn("page inspection failed", result.candidates[0].error)
        self.assertNotIn("test-password", result.to_json())

    def test_symlink_candidate_is_not_opened(self) -> None:
        link_name = self.add_file("Broker", "a" * 32)
        inspector = FakeInspector({link_name: ["Bloomberg: ABC LN"]})
        with patch.object(Path, "is_symlink", return_value=True):
            result = RetrievalEngine(self.corpus, inspector).retrieve(
                "ABC LN", "20260102", "Broker"
            )
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.candidates[0].error, "UnsafePath: symbolic links are not allowed")
        self.assertEqual(inspector.calls, [])

    def test_unreadable_candidate_blocks_otherwise_strong_selection(self) -> None:
        strong = self.add_file("Broker", "a" * 32)
        unreadable = self.add_file("Broker", "b" * 32)
        inspector = FakeInspector(
            {strong: ["Bloomberg: ABC LN"]}, {unreadable: RuntimeError("private details")}
        )
        result = RetrievalEngine(self.corpus, inspector).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.match)
        self.assertNotIn("private details", result.to_json())

    def test_missing_corpus_is_transparent(self) -> None:
        missing = self.corpus / "missing"
        result = RetrievalEngine(missing, FakeInspector({})).retrieve(
            "ABC LN", "20260102", "Broker"
        )
        self.assertEqual(result.status, "not_found")
        self.assertIn("does not exist", result.reason)

    def test_uppercase_extension_and_digest_are_supported(self) -> None:
        name = f"20260102_Broker_{'A' * 32}.PDF"
        (self.corpus / name).touch()
        result = RetrievalEngine(
            self.corpus, FakeInspector({name: ["Bloomberg: ABC LN"]})
        ).retrieve("ABC LN", "20260102", "Broker")
        self.assertEqual(result.status, "found")
        self.assertEqual(result.match.filename, name)

    def test_result_supports_text_and_structured_json(self) -> None:
        match = self.add_file("Broker", "a" * 32)
        result = RetrievalEngine(
            self.corpus, FakeInspector({match: ["Bloomberg: ABC LN SECRET REPORT WORDS"]})
        ).retrieve("ABC LN", "20260102", "Broker")
        rendered = render_text(result)
        structured = json.loads(result.to_json())
        self.assertIn("Status: found", rendered)
        self.assertIn(match, rendered)
        self.assertEqual(structured["status"], "found")
        self.assertEqual(structured["match"]["filename"], match)
        self.assertEqual(structured["match"]["path"], f"{self.corpus.name}/{match}")
        self.assertNotIn("SECRET REPORT WORDS", rendered)
        self.assertNotIn("SECRET REPORT WORDS", result.to_json())
        self.assertEqual(structured["match"]["evidence"][0]["matched_ticker"], "ABC LN")


if __name__ == "__main__":
    unittest.main()
