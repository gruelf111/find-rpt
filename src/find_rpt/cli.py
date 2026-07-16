from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import EvidenceDocument, EvidenceError, PdfEvidenceExtractor
from .retrieval import Candidate, RetrievalEngine, RetrievalResult
from .revisions import RevisionExtractor
from .rationale import ModelConfigurationError, RationaleExtractor


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
    parser = argparse.ArgumentParser(prog="find-rpt")
    subparsers = parser.add_subparsers(dest="command")

    find = subparsers.add_parser("find", help="select one report")
    _add_locator_arguments(find)
    find.add_argument("--format", choices=("text", "json"), default="text")

    evidence = subparsers.add_parser("evidence", help="extract structured PDF evidence")
    source = evidence.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf-path", type=Path)
    source.add_argument("--ticker", help="Bloomberg ticker")
    evidence.add_argument("--date", help="required with --ticker")
    evidence.add_argument("--broker", help="required with --ticker")
    evidence.add_argument("--corpus", type=Path, default=Path("corpus"))
    evidence.add_argument("--pages", help="one-based pages, e.g. 1-3,5")
    evidence.add_argument("--format", choices=("json",), default="json")

    revisions = subparsers.add_parser(
        "revisions", help="extract deterministic estimate-revision candidates"
    )
    source = revisions.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf-path", type=Path)
    source.add_argument("--ticker", help="Bloomberg ticker")
    revisions.add_argument("--date", help="required with --ticker")
    revisions.add_argument("--broker", help="required with --ticker")
    revisions.add_argument("--corpus", type=Path, default=Path("corpus"))
    revisions.add_argument("--pages", help="one-based pages, e.g. 1-3,5")
    revisions.add_argument("--format", choices=("json",), default="json")

    rationale = subparsers.add_parser(
        "rationale", help="retrieve bounded passages and extract grounded rationale"
    )
    source = rationale.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf-path", type=Path)
    source.add_argument("--ticker", help="Bloomberg ticker")
    rationale.add_argument("--date", help="required with --ticker")
    rationale.add_argument("--broker", help="required with --ticker")
    rationale.add_argument("--corpus", type=Path, default=Path("corpus"))
    rationale.add_argument("--pages", help="one-based pages, e.g. 1-3,5")
    rationale.add_argument("--no-model", action="store_true", help="return candidate passages only")
    rationale.add_argument("--format", choices=("json",), default="json")
    return parser


def _add_locator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ticker", help="Bloomberg ticker, for example 'BP/ LN'")
    parser.add_argument("date", help="corpus date as YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("broker", help="broker label")
    parser.add_argument("--corpus", type=Path, default=Path("corpus"))


def _run_find(args: argparse.Namespace) -> int:
    try:
        result = RetrievalEngine(args.corpus).retrieve(args.ticker, args.date, args.broker)
    except ValueError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 1
    print(result.to_json() if args.format == "json" else render_text(result))
    return {"found": 0, "not_found": 2, "ambiguous": 3}[result.status]


def _run_evidence(args: argparse.Namespace) -> int:
    retrieval: RetrievalResult | None = None
    if args.pdf_path is not None:
        path = args.pdf_path
        source_root = None
    else:
        if not args.date or not args.broker:
            print("Input error: --date and --broker are required with --ticker", file=sys.stderr)
            return 1
        try:
            retrieval = RetrievalEngine(args.corpus).retrieve(args.ticker, args.date, args.broker)
        except ValueError as error:
            print(f"Input error: {error}", file=sys.stderr)
            return 1
        if retrieval.status != "found":
            print(retrieval.to_json())
            return {"not_found": 2, "ambiguous": 3}[retrieval.status]
        path = args.corpus / retrieval.match.filename
        source_root = args.corpus
    try:
        document = PdfEvidenceExtractor().extract(path, pages=args.pages, source_root=source_root)
    except EvidenceError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    payload = document.to_dict()
    if retrieval is not None:
        payload = {"retrieval": retrieval.to_dict(), "evidence": payload}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _resolve_document(
    args: argparse.Namespace,
) -> tuple[RetrievalResult | None, EvidenceDocument | None, int]:
    retrieval: RetrievalResult | None = None
    if args.pdf_path is not None:
        path = args.pdf_path
        source_root = None
    else:
        if not args.date or not args.broker:
            print("Input error: --date and --broker are required with --ticker", file=sys.stderr)
            return None, None, 1
        try:
            retrieval = RetrievalEngine(args.corpus).retrieve(args.ticker, args.date, args.broker)
        except ValueError as error:
            print(f"Input error: {error}", file=sys.stderr)
            return None, None, 1
        if retrieval.status != "found":
            print(retrieval.to_json())
            return retrieval, None, {"not_found": 2, "ambiguous": 3}[retrieval.status]
        path = args.corpus / retrieval.match.filename
        source_root = args.corpus
    try:
        document = PdfEvidenceExtractor().extract(path, pages=args.pages, source_root=source_root)
    except EvidenceError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return retrieval, None, 1
    return retrieval, document, 0


def _run_revisions(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    result = RevisionExtractor().extract(document, broker=args.broker)
    payload = result.to_dict()
    if retrieval is not None:
        payload = {"retrieval": retrieval.to_dict(), "revisions": payload}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _run_rationale(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    revisions = RevisionExtractor().extract(document, broker=args.broker)
    try:
        result = RationaleExtractor().extract(
            document,
            revisions=revisions,
            no_model=args.no_model,
            broker=args.broker,
        )
    except ModelConfigurationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    payload = result.to_dict()
    if retrieval is not None:
        payload = {"retrieval": retrieval.to_dict(), "rationale": payload}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.status != "model_error" else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    # Preserve the original positional retrieval interface while documenting `find`.
    if argv and argv[0] not in {"find", "evidence", "revisions", "rationale", "-h", "--help"}:
        argv.insert(0, "find")
    args = build_parser().parse_args(argv)
    if args.command == "find":
        return _run_find(args)
    if args.command == "evidence":
        return _run_evidence(args)
    if args.command == "revisions":
        return _run_revisions(args)
    if args.command == "rationale":
        return _run_rationale(args)
    build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
