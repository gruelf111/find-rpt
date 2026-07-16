from __future__ import annotations

import http.client
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

import fitz

from find_rpt.citations import (
    CitationBuilder,
    CitationInputError,
    CitationNotFoundError,
    CitationRepository,
    CitationRequest,
    CitationStore,
    StaleCitationError,
    make_server,
    requests_from_revisions,
)
from find_rpt.cli import main
from find_rpt.evidence import PdfEvidenceExtractor
from find_rpt.revisions import RevisionExtractor


class CitationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        self.cache = self.root / "cache"
        self.path = self.corpus / "sample.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=500)
        page.insert_textbox(
            fitz.Rect(40, 40, 350, 110),
            "We raise FY2026E revenue from EUR 100m to EUR 110m\ndue to higher prices.",
        )
        page = document.new_page(width=400, height=500)
        page.insert_text((40, 60), "Second-page supporting passage")
        document.save(self.path)
        document.close()
        self.document = PdfEvidenceExtractor().extract(self.path, source_root=self.corpus)
        self.first_block = self.document.pages[0].blocks[0]
        self.second_block = self.document.pages[1].blocks[0]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def request(self, *block_ids: str, document_id: str | None = None) -> CitationRequest:
        return CitationRequest(
            document_id or self.document.document_id,
            tuple(block_ids),
            "Revenue revision rationale",
            "claim:revenue",
        )

    def build(self, *requests: CitationRequest):
        return CitationBuilder(self.corpus).build(self.document, self.path, requests)

    def test_stable_citation_id_repeatability_and_cache_privacy(self) -> None:
        first = self.build(self.request(self.first_block.block_id))
        second = self.build(self.request(self.first_block.block_id))
        self.assertEqual(first, second)
        self.assertEqual(first.citations[0].citation_id, second.citations[0].citation_id)
        self.assertEqual(first.citations[0].page_number, 1)
        self.assertNotIn(str(self.root), first.to_json())
        self.assertNotIn("higher prices", first.to_json())

        store = CitationStore(self.cache)
        store.save(first)
        cached = self.cache.joinpath("index.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), cached)
        self.assertNotIn("higher prices", cached)

    def test_multiline_and_multiple_blocks_produce_precise_valid_boxes(self) -> None:
        result = self.build(self.request(self.first_block.block_id))
        citation = result.citations[0]
        self.assertGreaterEqual(len(citation.bounding_boxes), 2)
        for x0, y0, x1, y1 in citation.bounding_boxes:
            self.assertTrue(0 <= x0 < x1 <= citation.page_width)
            self.assertTrue(0 <= y0 < y1 <= citation.page_height)

        page = self.document.pages[0]
        extra = page.blocks[1] if len(page.blocks) > 1 else self.first_block
        combined = self.build(self.request(self.first_block.block_id, extra.block_id))
        self.assertEqual(combined.citations[0].evidence_block_ids[0], self.first_block.block_id)

    def test_invalid_and_wrong_document_blocks_emit_no_citation(self) -> None:
        invalid = self.build(self.request("p0001-b9999-invented"))
        self.assertEqual(invalid.citations, ())
        self.assertEqual(invalid.failed_requests, 1)
        self.assertIn("unknown_evidence_block", invalid.warnings[0])

        wrong = self.build(
            self.request(self.first_block.block_id, document_id="sha256:" + "0" * 64)
        )
        self.assertEqual(wrong.citations, ())
        self.assertIn("wrong_document", wrong.warnings[0])

    def test_multi_page_evidence_is_split_into_separate_citations(self) -> None:
        result = self.build(
            self.request(self.first_block.block_id, self.second_block.block_id)
        )
        self.assertEqual([item.page_number for item in result.citations], [1, 2])
        self.assertTrue(
            all("split_from_multi_page_evidence" in item.warnings for item in result.citations)
        )

    def test_non_finite_and_out_of_bounds_geometry_is_rejected(self) -> None:
        word = replace(self.first_block.words[0], bbox=(float("nan"), 1.0, 2.0, 3.0))
        block = replace(self.first_block, words=(word,))
        page = replace(self.document.pages[0], blocks=(block,))
        broken = replace(self.document, pages=(page,))
        result = CitationBuilder(self.corpus).build(
            broken, self.path, (self.request(block.block_id),)
        )
        self.assertEqual(result.citations, ())
        self.assertIn("invalid_bounding_box", result.warnings[0])

    def test_stale_source_is_detected_at_build_and_validation(self) -> None:
        result = self.build(self.request(self.first_block.block_id))
        store = CitationStore(self.cache)
        store.save(result)
        citation_id = result.citations[0].citation_id
        original = self.path.read_bytes()
        self.path.write_bytes(original + b"changed")
        with self.assertRaises(StaleCitationError):
            CitationRepository(self.corpus, store).validate(citation_id)
        with self.assertRaises(StaleCitationError):
            CitationBuilder(self.corpus).build(
                self.document, self.path, (self.request(self.first_block.block_id),)
            )

    def test_unindexed_and_outside_corpus_sources_are_rejected(self) -> None:
        outside = self.root / "outside.pdf"
        outside.write_bytes(self.path.read_bytes())
        with self.assertRaises(CitationInputError):
            CitationBuilder(self.corpus).build(
                self.document, outside, (self.request(self.first_block.block_id),)
            )
        with self.assertRaises(CitationNotFoundError):
            CitationRepository(self.corpus, CitationStore(self.cache)).source_path("../outside.pdf")

    def test_citation_base_url_must_be_a_loopback_http_origin(self) -> None:
        for value in (
            "https://127.0.0.1:8765",
            "http://0.0.0.0:8765",
            "http://example.com:8765",
            "http://127.0.0.1:8765/unexpected",
        ):
            with self.subTest(value=value), self.assertRaises(CitationInputError):
                CitationBuilder(self.corpus, base_url=value)

    def test_revision_output_is_accepted_as_structured_input(self) -> None:
        revisions = RevisionExtractor().extract(self.document)
        requests = requests_from_revisions(revisions)
        result = self.build(*requests)
        self.assertEqual(revisions.status, "revisions_found")
        self.assertGreaterEqual(len(result.citations), 1)
        self.assertTrue(all(item.claim_key.startswith("revision:") for item in result.citations))

    def test_period_selector_excludes_neighbouring_table_periods(self) -> None:
        path = self.corpus / "period-table.pdf"
        source = fitz.open()
        page = source.new_page(width=400, height=300)
        page.insert_text((190, 60), "2026E")
        page.insert_text((290, 60), "2027E")
        page.insert_text((40, 90), "EPS")
        page.insert_text((190, 90), "2.00")
        page.insert_text((290, 90), "3.00")
        source.save(path)
        source.close()
        document = PdfEvidenceExtractor().extract(path, source_root=self.corpus)
        block_ids = tuple(block.block_id for block in document.pages[0].blocks)
        result = CitationBuilder(self.corpus).build(
            document,
            path,
            (
                CitationRequest(
                    document.document_id,
                    block_ids,
                    "EPS 2026E evidence",
                    "claim:eps:2026",
                    highlight_metric="eps",
                    highlight_period="2026E",
                ),
            ),
        )
        boxes = result.citations[0].bounding_boxes
        self.assertTrue(any(x0 < 100 for x0, _, _, _ in boxes))
        self.assertTrue(any(170 < x0 < 230 for x0, _, _, _ in boxes))
        self.assertFalse(any(x0 > 260 for x0, _, _, _ in boxes))

    def test_cli_build_and_validate(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(
                [
                    "citations", "build", "--pdf-path", str(self.path),
                    "--corpus", str(self.corpus), "--cache-dir", str(self.cache),
                ]
            )
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(output.getvalue())
        citation_id = payload["citations"][0]["citation_id"]
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "citations", "validate", "--citation-id", citation_id,
                    "--corpus", str(self.corpus), "--cache-dir", str(self.cache),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["page_number"], 1)


class CitationServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        self.cache = self.root / "cache"
        self.path = self.corpus / "sample.pdf"
        source = fitz.open()
        page = source.new_page(width=400, height=500)
        page.insert_text((40, 60), "First-page supporting passage")
        page = source.new_page(width=400, height=500)
        page.insert_text((40, 60), "Second-page supporting passage")
        source.save(self.path)
        source.close()
        self.document = PdfEvidenceExtractor().extract(self.path, source_root=self.corpus)
        self.first_block = self.document.pages[0].blocks[0]
        self.second_block = self.document.pages[1].blocks[0]
        result = self.build(
            CitationRequest(
                self.document.document_id,
                (self.first_block.block_id,),
                "First page evidence",
                "claim:first",
            ),
            CitationRequest(
                self.document.document_id,
                (self.second_block.block_id,),
                "Second page evidence",
                "claim:second",
            ),
        )
        CitationStore(self.cache).save(result)
        self.citations = result.citations
        self.server = make_server(self.corpus, self.cache, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def build(self, *requests: CitationRequest):
        return CitationBuilder(self.corpus).build(self.document, self.path, requests)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = response.read()
        headers = {key.casefold(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, headers, payload

    def test_default_binding_is_loopback_and_non_loopback_is_rejected(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        with self.assertRaises(CitationInputError):
            make_server(self.corpus, self.cache, host="0.0.0.0", port=0)

    def test_correct_page_viewer_target_highlights_and_headers(self) -> None:
        citation = self.citations[1]
        status, headers, payload = self.get(f"/citation/{citation.citation_id}")
        text = payload.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("page 2", text)
        self.assertIn(f"/citation/{citation.citation_id}/page.png", text)
        self.assertIn('class="highlight"', text)
        self.assertIn("no-store", headers["cache-control"])
        self.assertIn("default-src 'self'", headers["content-security-policy"])

        status, headers, payload = self.get(f"/citation/{citation.citation_id}/page.png")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "image/png")
        self.assertTrue(payload.startswith(b"\x89PNG"))

    def test_invalid_ids_traversal_and_unindexed_files_are_not_served(self) -> None:
        for path in (
            "/citation/not-valid",
            "/citation/../../outside.pdf",
            "/document/../../outside.pdf",
            "/document/sha256:" + "0" * 64 + ".pdf",
            "/outside.pdf",
        ):
            with self.subTest(path=path):
                status, _, _ = self.get(path)
                self.assertEqual(status, 404)

    def test_only_indexed_original_pdf_is_served(self) -> None:
        citation = self.citations[0]
        status, headers, payload = self.get(
            f"/document/{citation.document_id}.pdf#page={citation.page_number}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/pdf")
        self.assertEqual(payload, self.path.read_bytes())

    def test_original_pdf_route_uses_the_validated_citation_source(self) -> None:
        other = self.corpus / "other.pdf"
        other.write_bytes(b"%PDF-1.4\nnot the cited report")
        data = CitationStore(self.cache).load()
        data["documents"][self.document.document_id]["source_filename"] = "other.pdf"
        self.cache.joinpath("index.json").write_text(json.dumps(data), encoding="utf-8")

        citation = self.citations[0]
        status, _, payload = self.get(f"/document/{citation.document_id}.pdf")
        self.assertEqual(status, 200)
        self.assertEqual(payload, self.path.read_bytes())

    def test_stale_citation_returns_conflict(self) -> None:
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        status, _, payload = self.get(f"/citation/{self.citations[0].citation_id}")
        self.assertEqual(status, 409)
        self.assertIn(b"stale", payload)


if __name__ == "__main__":
    unittest.main()
