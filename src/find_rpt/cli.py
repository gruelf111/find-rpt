from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .retrieval import Candidate, RetrievalEngine, RetrievalResult


def _candidate_lines(candidate: Candidate) -> list[str]:
    details = (
        f"score={candidate.score}; confidence={candidate.confidence}; "
        f"pages={candidate.pages_inspected or 'none'}"
    )
    if candidate.error:
        details += f"; error={candidate.error}"
    lines = [f"- {candidate.filename} ({details})"]
    for evidence in candidate.evidence[:3]:
        lines.append(
            f"  page {evidence.page}, line {evidence.line}, {evidence.kind}, "
            f"score {evidence.score}; matched {evidence.matched_ticker}"
        )
    return lines


def render_text(result: RetrievalResult) -> str:
    lines = [
        f"Status: {result.status}",
        f"Query: {result.query.ticker} | {result.query.date} | {result.query.broker}",
        f"Reason: {result.reason}",
    ]
    if result.match is not None:
        lines.append(f"Match: {result.match.path}")
        lines.append("Evidence:")
        lines.extend(_candidate_lines(result.match)[1:])
    elif result.candidates:
        lines.append("Ranked candidates:")
        for candidate in result.candidates:
            lines.extend(_candidate_lines(candidate))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="find-rpt",
        description="Find one local report using filename metadata and ticker evidence.",
    )
    parser.add_argument("ticker", help="Bloomberg ticker, for example 'BP/ LN'")
    parser.add_argument("date", help="Corpus date as YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("broker", help="Broker label; punctuation and case are normalized")
    parser.add_argument("--corpus", type=Path, default=Path("corpus"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = RetrievalEngine(args.corpus).retrieve(args.ticker, args.date, args.broker)
    except ValueError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 1

    print(result.to_json() if args.format == "json" else render_text(result))
    return {"found": 0, "not_found": 2, "ambiguous": 3}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
