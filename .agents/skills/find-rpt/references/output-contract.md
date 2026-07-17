# Agent-hosted output contract

The skill uses two JSON boundaries. Python owns both boundaries and the final renderer.

## Prepare bundle

`find-rpt agent prepare ... --format json` emits only:

- `schema_version`;
- `normalized_request` and a safe `selected_report_identifier`;
- `validated_revisions`, grouped by metric and direction with fiscal-period and stable evidence-block identifiers; authoritative values remain in Python;
- `candidate_rationale_passages` and `candidate_context_passages`, each containing only `block_id` and bounded `text`;
- `allowed_metric_ids` and `allowed_fiscal_period_ids`;
- deterministic `analyst_candidates` containing names, roles, and source block IDs but no email addresses; and
- deterministic warning codes.

The bundle deliberately contains no authoritative revision values, page numbers, bounding boxes, citation IDs or URLs, analyst addresses, full-report text, or unrelated passages. Each passage appears in only one candidate list. The host must not add keys or identifiers and must not return analyst data.

## Semantic JSON

The host returns the exact rationale schema shown in `SKILL.md`. Every factual semantic field must cite one or more supplied block IDs. Metrics and periods must use the prepare bundle's closed allowlists. Confidence is advisory; Python recalculates or downgrades it. The host never constructs citations or repeats deterministic revision arithmetic.

## Final result

`find-rpt agent finalize ... --input - --format agent-json` reselects the same report from the original query, repeats deterministic extraction, validates the semantic object, removes unsupported items, constructs citations, and renders the brief.

Successful final objects contain:

- `status`: `found` or `partial`;
- `normalized_request` and a safe `selected_report` identifier;
- structured `brief`, `revisions`, `context`, and `citations`;
- `rationale_clarity`;
- `warnings`;
- `requires_analyst_escalation`, `analyst`, and a review-only `email_draft`;
- immutable `sent: false`;
- `citation_viewer_available`; and
- authoritative `rendered_markdown`.

Return `rendered_markdown` unchanged. `partial` means some semantic output was unavailable, unclear, malformed, or removed. Do not fill the gap. Invented or unselected block IDs, unsupported claims, metrics, periods, names, roles, numbers, contexts, and causal links are removed and surfaced through warnings.

Retrieval failures remain `not_found` or `ambiguous`; never select a candidate manually. Citation page numbers, geometry, and loopback URLs appear only in final Python output. An unavailable citation viewer does not authorize replacing links.

The Codex host model participates only while the skill runs inside Codex. Standalone `brief` and `rationale` commands use API mode only when explicitly configured with `FIND_RPT_MODEL_MODE=api` and `FIND_RPT_MODEL_API_KEY`; otherwise the caller must use `--no-model` or `FIND_RPT_MODEL_MODE=none`.
