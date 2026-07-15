from __future__ import annotations

import json
import unittest
from pathlib import Path

from find_rpt.retrieval import RetrievalEngine


class CorpusEvaluationTests(unittest.TestCase):
    def test_manually_verified_cases(self) -> None:
        corpus = Path("corpus")
        if not corpus.is_dir():
            self.skipTest("local corpus is not available")
        cases = json.loads(Path("tests/evaluation_cases.json").read_text(encoding="utf-8"))
        engine = RetrievalEngine(corpus)
        for case in cases:
            with self.subTest(ticker=case["ticker"], broker=case["broker"]):
                result = engine.retrieve(case["ticker"], case["date"], case["broker"])
                self.assertEqual(result.status, "found", result.to_json())
                self.assertEqual(result.match.filename, case["expected_filename"])
                self.assertLessEqual(max(result.match.pages_inspected), 2)
                self.assertNotIn("text", result.match.evidence[0].__dict__)
                self.assertNotIn("line_sha256", result.match.evidence[0].__dict__)


if __name__ == "__main__":
    unittest.main()
