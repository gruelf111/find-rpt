from __future__ import annotations

import argparse
import http.client
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .evidence import EvidenceDocument, EvidenceError, PdfEvidenceExtractor
from .citations import (
    DEFAULT_CACHE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    CitationBuilder,
    CitationError,
    CitationRepository,
    CitationStore,
    make_server,
    requests_from_rationale,
    requests_from_revisions,
    requests_from_metadata,
)
from .brief import ResearchBriefBuilder, render_markdown, render_text as render_brief_text
from .escalation import (
    AmbiguityEscalationBuilder,
    EscalationPolicy,
    render_email_draft_markdown,
    render_email_draft_text,
)
from .metadata import ReportMetadataExtractor
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

    brief = subparsers.add_parser(
        "brief", help="render a concise evidence-backed research brief"
    )
    brief.add_argument("--ticker", required=True, help="Bloomberg ticker")
    brief.add_argument("--date", required=True, help="corpus date as YYYYMMDD or YYYY-MM-DD")
    brief.add_argument("--broker", required=True, help="broker label")
    brief.add_argument("--corpus", type=Path, default=Path("corpus"))
    brief.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    brief.add_argument("--base-url", default=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    brief.add_argument(
        "--format",
        choices=("markdown", "json", "text", "agent-json"),
        default="markdown",
    )
    brief.add_argument("--no-visualization", action="store_true")
    brief.add_argument("--no-model", action="store_true", help="render a transparent partial brief without semantic interpretation")
    brief.add_argument(
        "--escalate-partial",
        action="store_true",
        help="also draft when partial rationale leaves a material revision unexplained",
    )

    escalation = subparsers.add_parser(
        "escalation", help="evaluate ambiguity and render a review-only analyst draft"
    )
    escalation.add_argument("--ticker", required=True, help="Bloomberg ticker")
    escalation.add_argument("--date", required=True, help="corpus date as YYYYMMDD or YYYY-MM-DD")
    escalation.add_argument("--broker", required=True, help="broker label")
    escalation.add_argument("--corpus", type=Path, default=Path("corpus"))
    escalation.add_argument("--format", choices=("markdown", "json", "text"), default="markdown")
    escalation.add_argument("--no-model", action="store_true", help="evaluate without semantic interpretation")
    escalation.add_argument(
        "--escalate-partial",
        action="store_true",
        help="draft when partial rationale leaves a material revision unexplained",
    )

    agent = subparsers.add_parser(
        "agent", help="two-stage Codex-hosted semantic interpretation"
    )
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    agent_prepare = agent_commands.add_parser(
        "prepare", help="emit bounded evidence for the active Codex agent"
    )
    _add_locator_arguments(agent_prepare)
    agent_prepare.add_argument("--format", choices=("json",), default="json")
    agent_finalize = agent_commands.add_parser(
        "finalize", help="validate semantic JSON and render the final brief"
    )
    _add_locator_arguments(agent_finalize)
    agent_finalize.add_argument(
        "--input", type=Path, default=Path("-"), help="semantic JSON file, or - for stdin"
    )
    agent_finalize.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    agent_finalize.add_argument("--base-url", default=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    agent_finalize.add_argument(
        "--format", choices=("markdown", "json", "text", "agent-json"), default="markdown"
    )
    agent_finalize.add_argument("--no-visualization", action="store_true")
    agent_finalize.add_argument("--escalate-partial", action="store_true")

    citations = subparsers.add_parser(
        "citations", help="build, validate, and serve precise local citations"
    )
    citation_commands = citations.add_subparsers(dest="citation_command", required=True)
    citation_build = citation_commands.add_parser(
        "build", help="build citations from validated extraction evidence"
    )
    source = citation_build.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf-path", type=Path)
    source.add_argument("--ticker", help="Bloomberg ticker")
    citation_build.add_argument("--date", help="required with --ticker")
    citation_build.add_argument("--broker", help="required with --ticker")
    citation_build.add_argument("--corpus", type=Path, default=Path("corpus"))
    citation_build.add_argument("--pages", help="one-based pages, e.g. 1-3,5")
    citation_build.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    citation_build.add_argument(
        "--base-url", default=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
    )
    citation_build.add_argument(
        "--with-rationale",
        action="store_true",
        help="also build citations for locally interpreted rationale claims",
    )
    citation_build.add_argument("--format", choices=("json",), default="json")

    citation_validate = citation_commands.add_parser(
        "validate", help="validate one cached citation against its source PDF"
    )
    citation_validate.add_argument("--citation-id", required=True)
    citation_validate.add_argument("--corpus", type=Path, default=Path("corpus"))
    citation_validate.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    citation_validate.add_argument("--format", choices=("json",), default="json")

    citation_serve = citation_commands.add_parser(
        "serve", help="start the loopback-only highlighted citation viewer"
    )
    citation_serve.add_argument("--corpus", type=Path, default=Path("corpus"))
    citation_serve.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    citation_serve.add_argument("--host", default=DEFAULT_HOST)
    citation_serve.add_argument("--port", type=int, default=DEFAULT_PORT)
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
    if getattr(args, "pdf_path", None) is not None:
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
        document = PdfEvidenceExtractor().extract(
            path,
            pages=getattr(args, "pages", None),
            source_root=source_root,
        )
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
    if getattr(args, "pdf_path", None) is not None:
        path = args.pdf_path
        source_root = None
    else:
        if not args.date or not args.broker:
            print("Input error: --date and --broker are required with --ticker", file=sys.stderr)
            return None, None, 1
        try:
            query_date = args.date
            for format_string in ("%d %b %Y", "%d %B %Y"):
                try:
                    query_date = datetime.strptime(args.date, format_string).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            retrieval = RetrievalEngine(args.corpus).retrieve(args.ticker, query_date, args.broker)
        except ValueError as error:
            print(f"Input error: {error}", file=sys.stderr)
            return None, None, 1
        if retrieval.status != "found":
            print(retrieval.to_json())
            return retrieval, None, {"not_found": 2, "ambiguous": 3}[retrieval.status]
        path = args.corpus / retrieval.match.filename
        source_root = args.corpus
    try:
        document = PdfEvidenceExtractor().extract(
            path,
            pages=getattr(args, "pages", None),
            source_root=source_root,
        )
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


def _run_brief(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    source_path = args.corpus / retrieval.match.filename
    metadata = ReportMetadataExtractor().extract(document)
    revisions = RevisionExtractor().extract(document, broker=args.broker)
    try:
        rationale = RationaleExtractor().extract(
            document,
            revisions=revisions,
            no_model=args.no_model,
            broker=args.broker,
        )
    except ModelConfigurationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    if rationale.status == "model_error":
        print(rationale.to_json(), file=sys.stderr)
        return 1
    escalation = AmbiguityEscalationBuilder(
        EscalationPolicy(escalate_partial=args.escalate_partial)
    ).build(
        ticker=retrieval.query.ticker,
        report_date=retrieval.query.date,
        metadata=metadata,
        revisions=revisions,
        rationale=rationale,
    )
    requests = list(requests_from_metadata(document.document_id, metadata))
    requests.extend(requests_from_revisions(revisions))
    requests.extend(requests_from_rationale(rationale))
    try:
        citation_result = CitationBuilder(args.corpus, base_url=args.base_url).build(
            document, source_path, requests
        )
        CitationStore(args.cache_dir).save(citation_result)
    except CitationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    brief = ResearchBriefBuilder().build(
        ticker=retrieval.query.ticker,
        broker=retrieval.query.broker,
        report_date=retrieval.query.date,
        metadata=metadata,
        revisions=revisions,
        rationale=rationale,
        citations=citation_result,
        escalation=escalation,
        include_visualization=not args.no_visualization,
    )
    if args.format == "agent-json":
        payload = _agent_brief_payload(retrieval, brief, rationale, citation_result)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.format == "json":
        print(brief.to_json())
    elif args.format == "text":
        print(render_brief_text(brief), end="")
    else:
        print(render_markdown(brief), end="")
    return 0


def _agent_brief_payload(retrieval, brief, rationale, citation_result) -> dict[str, Any]:
    brief_dict = brief.to_dict()
    rendered_citations = [
        {
            "citation_id": item.citation_id,
            "label": item.evidence_label,
            "local_url": item.local_url,
            "page_number": item.page_number,
            "validation_status": item.validation_status,
        }
        for item in citation_result.citations
        if item.validation_status == "valid"
    ]
    is_partial = bool(brief.warnings) or brief.rationale_clarity != "clear"
    return {
        "schema_version": "1.0",
        "status": "partial" if is_partial else "found",
        "normalized_request": {
            "ticker": retrieval.query.ticker,
            "date": retrieval.query.date,
            "broker": retrieval.query.broker,
        },
        "selected_report": {
            "source_identifier": brief.source_identifier,
            "title": brief.report_title,
            "internal_publication_date": brief.internal_publication_date,
        },
        "brief": brief_dict,
        "revisions": {
            "status": brief.revisions_status,
            "rows": brief_dict["revision_rows"],
            "omitted_rows": brief.omitted_revision_rows,
        },
        "rationale_clarity": brief.rationale_clarity,
        "context": {
            "report_context": rationale.extraction.report_context if rationale.extraction else None,
            "management_contact": rationale.extraction.management_contact if rationale.extraction else None,
            "people_met": (
                [{"name": person.name, "role": person.role} for person in rationale.extraction.people_met]
                if rationale.extraction else []
            ),
        },
        "citations": rendered_citations,
        "warnings": list(brief.warnings),
        "requires_analyst_escalation": brief.requires_analyst_escalation,
        "analyst": brief_dict["analyst"],
        "email_draft": brief_dict["email_draft"],
        "sent": False,
        "rendered_markdown": render_markdown(brief),
    }


def _run_agent_prepare(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    revisions = RevisionExtractor().extract(document, broker=args.broker)
    metadata = ReportMetadataExtractor().extract(document)
    bundle, _, _ = RationaleExtractor().prepare_agent(
        document, revisions=revisions, broker=args.broker
    )
    bundle = {
        "schema_version": bundle["schema_version"],
        "normalized_request": {
            "ticker": retrieval.query.ticker,
            "date": retrieval.query.date,
            "broker": retrieval.query.broker,
        },
        "selected_report_identifier": Path(revisions.source_filename).name,
        "validated_revisions": bundle["validated_revisions"],
        "candidate_rationale_passages": bundle["candidate_rationale_passages"],
        "candidate_context_passages": bundle["candidate_context_passages"],
        "allowed_metric_ids": bundle["allowed_metric_ids"],
        "allowed_fiscal_period_ids": bundle["allowed_fiscal_period_ids"],
        "analyst_candidates": [
            {
                "name": analyst.name,
                "role": analyst.role,
                "evidence_block_ids": list(analyst.evidence_block_ids),
            }
            for analyst in metadata.analysts
        ],
        "warnings": list(dict.fromkeys((*revisions.warnings, *metadata.warnings))),
    }
    print(json.dumps(bundle, indent=2, ensure_ascii=False))
    return 0


def _read_semantic_input(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    except OSError:
        return None, "agent_semantic_input_unreadable"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "agent_semantic_json_malformed"
    if not isinstance(parsed, dict):
        return None, "agent_semantic_json_not_an_object"
    return parsed, None


def _citation_viewer_available(base_url: str, *, timeout: float = 0.2) -> bool:
    parsed = urlsplit(base_url)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
    try:
        connection.request("GET", "/__find_rpt_health__")
        response = connection.getresponse()
        response.read()
        return response.getheader("Server", "").startswith("find-rpt-citations/1")
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def _run_agent_finalize(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    source_path = args.corpus / retrieval.match.filename
    metadata = ReportMetadataExtractor().extract(document)
    revisions = RevisionExtractor().extract(document, broker=args.broker)
    semantic, input_warning = _read_semantic_input(args.input)
    rationale = RationaleExtractor().validate_agent_output(
        document, semantic or {}, revisions=revisions, broker=args.broker
    )
    if input_warning:
        rationale = replace(rationale, warnings=(input_warning,))
    escalation = AmbiguityEscalationBuilder(
        EscalationPolicy(escalate_partial=args.escalate_partial)
    ).build(
        ticker=retrieval.query.ticker,
        report_date=retrieval.query.date,
        metadata=metadata,
        revisions=revisions,
        rationale=rationale,
    )
    requests = list(requests_from_metadata(document.document_id, metadata))
    requests.extend(requests_from_revisions(revisions))
    requests.extend(requests_from_rationale(rationale))
    try:
        citation_result = CitationBuilder(args.corpus, base_url=args.base_url).build(
            document, source_path, requests
        )
        CitationStore(args.cache_dir).save(citation_result)
    except (CitationError, OSError):
        print(
            json.dumps(
                {
                    "error": "CitationFinalizationError",
                    "message": "citation construction or local cache write failed",
                }
            ),
            file=sys.stderr,
        )
        return 1
    brief = ResearchBriefBuilder().build(
        ticker=retrieval.query.ticker,
        broker=retrieval.query.broker,
        report_date=retrieval.query.date,
        metadata=metadata,
        revisions=revisions,
        rationale=rationale,
        citations=citation_result,
        escalation=escalation,
        include_visualization=not args.no_visualization,
    )
    viewer_available = _citation_viewer_available(args.base_url)
    if not viewer_available and citation_result.citations:
        brief = replace(
            brief,
            warnings=tuple(dict.fromkeys((*brief.warnings, "citation_viewer_unavailable"))),
        )
    if args.format == "agent-json":
        payload = _agent_brief_payload(retrieval, brief, rationale, citation_result)
        payload["citation_viewer_available"] = viewer_available
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.format == "json":
        print(brief.to_json())
    elif args.format == "text":
        print(render_brief_text(brief), end="")
    else:
        print(render_markdown(brief), end="")
    return 0


def _run_escalation(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    metadata = ReportMetadataExtractor().extract(document)
    revisions = RevisionExtractor().extract(document, broker=args.broker)
    try:
        rationale = RationaleExtractor().extract(
            document,
            revisions=revisions,
            no_model=args.no_model,
            broker=args.broker,
        )
    except ModelConfigurationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    if rationale.status == "model_error":
        print(rationale.to_json(), file=sys.stderr)
        return 1
    result = AmbiguityEscalationBuilder(
        EscalationPolicy(escalate_partial=args.escalate_partial)
    ).build(
        ticker=retrieval.query.ticker,
        report_date=retrieval.query.date,
        metadata=metadata,
        revisions=revisions,
        rationale=rationale,
    )
    if args.format == "json":
        print(result.to_json())
    elif result.requires_analyst_escalation and result.email_draft is not None:
        reason = result.escalation_reason.replace("_", " ")
        if args.format == "text":
            print(f"Analyst escalation required: {reason}\n\n{render_email_draft_text(result.email_draft)}")
        else:
            print(
                "## Analyst escalation required\n\n"
                f"{reason}.\n\n{render_email_draft_markdown(result.email_draft)}"
            )
    else:
        print("No analyst escalation is required from the validated structured data.")
        if result.warnings:
            print("Warnings:")
            for warning in result.warnings:
                print(f"- {warning.replace('_', ' ')}")
    return 0


def _run_citation_build(args: argparse.Namespace) -> int:
    retrieval, document, code = _resolve_document(args)
    if code:
        return code
    if args.pdf_path is not None:
        source_path = args.pdf_path
    else:
        source_path = args.corpus / retrieval.match.filename
    revisions = RevisionExtractor().extract(document, broker=args.broker)
    requests = list(requests_from_revisions(revisions))
    rationale = None
    if args.with_rationale:
        try:
            rationale = RationaleExtractor().extract(
                document, revisions=revisions, broker=args.broker
            )
        except ModelConfigurationError as error:
            print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
            return 1
        if rationale.status == "model_error":
            print(rationale.to_json(), file=sys.stderr)
            return 1
        requests.extend(requests_from_rationale(rationale))
    try:
        result = CitationBuilder(args.corpus, base_url=args.base_url).build(
            document, source_path, requests
        )
        CitationStore(args.cache_dir).save(result)
    except CitationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    payload = result.to_dict()
    payload["revision_status"] = revisions.status
    if rationale is not None:
        payload["rationale_status"] = rationale.status
    if retrieval is not None:
        payload = {"retrieval": retrieval.to_dict(), "citation_build": payload}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _run_citation_validate(args: argparse.Namespace) -> int:
    try:
        citation = CitationRepository(
            args.corpus, CitationStore(args.cache_dir)
        ).validate(args.citation_id)
    except CitationError as error:
        print(json.dumps({"status": "invalid", "error": type(error).__name__, "message": str(error)}))
        return 1
    print(
        json.dumps(
            {
                "status": "valid",
                "citation_id": citation.citation_id,
                "document_id": citation.document_id,
                "page_number": citation.page_number,
                "highlight_box_count": len(citation.bounding_boxes),
                "local_url": citation.local_url,
            },
            indent=2,
        )
    )
    return 0


def _run_citation_serve(args: argparse.Namespace) -> int:
    try:
        server = make_server(
            args.corpus,
            args.cache_dir,
            host=args.host,
            port=args.port,
        )
    except CitationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    host, port = server.server_address[:2]
    print(f"Citation viewer listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    # Preserve the original positional retrieval interface while documenting `find`.
    if argv and argv[0] not in {"find", "evidence", "revisions", "rationale", "brief", "escalation", "agent", "citations", "-h", "--help"}:
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
    if args.command == "brief":
        return _run_brief(args)
    if args.command == "escalation":
        return _run_escalation(args)
    if args.command == "agent":
        if args.agent_command == "prepare":
            return _run_agent_prepare(args)
        if args.agent_command == "finalize":
            return _run_agent_finalize(args)
    if args.command == "citations":
        if args.citation_command == "build":
            return _run_citation_build(args)
        if args.citation_command == "validate":
            return _run_citation_validate(args)
        if args.citation_command == "serve":
            return _run_citation_serve(args)
    build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
