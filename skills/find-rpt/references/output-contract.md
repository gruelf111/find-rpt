# Agent JSON output contract

The launcher emits one JSON object. The installed Python CLI and renderer are authoritative; the launcher only parses invocation syntax, applies configuration, validates safety invariants, and maps process failures.

## Status

- `found`: one report selected and a complete validated brief returned.
- `partial`: one report selected, but one or more material limitations or unavailable components are present.
- `not_found`: no filename candidate or no ticker match.
- `ambiguous`: selection cannot prove exactly one report, including tied matches or unreadable shortlisted PDFs.
- `invalid_invocation`: missing/invalid ticker, date, broker, or quoting.
- `configuration_error`: invalid configuration, inaccessible corpus, unsafe endpoint, or CLI startup/runtime configuration failure.
- `model_unavailable`: required local model configuration or response is unavailable. Re-run with explicitly configured no-model mode only when a partial brief is acceptable.
- `malformed_cli_json`: CLI output is not the expected structured object.
- `cli_error`: an unclassified CLI failure.
- `safety_error`: absolute-path leakage or violation of immutable `sent: false`.

The local viewer is checked separately through `citation_viewer_available`. When false, links remain in the brief and `citation_viewer_unavailable` appears in `warnings`.

## Success and partial fields

- `schema_version`: contract version.
- `status`: one status above.
- `normalized_request`: `ticker`, ISO `date`, and `broker` after command parsing. Final ticker/broker normalization and matching remain in the Python pipeline.
- `selected_report`: safe source identifier, report title, and internal publication date when validated. It never contains an absolute path.
- `brief`: complete structured `ResearchBrief` object.
- `rendered_markdown`: authoritative final renderer output. Return it unchanged.
- `revisions`: concise validated rows, extraction status, and omitted-row count. Missing values are JSON `null`; no value may be inferred.
- `rationale_clarity`: `clear`, `partial`, `unclear`, or `null` when unavailable.
- `context`: report-context enum, management-contact state, and explicitly supported participants.
- `citations`: validated citation ID, label, loopback URL, one-based page, and validation status. Material facts also carry citations inside `brief`.
- `warnings`: material completeness or interpretation warnings.
- `requires_analyst_escalation`: deterministic Boolean.
- `analyst`: only report-evidenced draft recipients; may be empty.
- `email_draft`: review-only draft or `null`. A missing address is exactly `[TODO: address]`.
- `sent`: always and immutably `false`, including nested draft state.
- `citation_viewer_available`: launcher health result.

## Retrieval and failure fields

Failure objects retain `schema_version`, `status`, `normalized_request` when parsing succeeded, `message`, `warnings`, `requires_analyst_escalation: false`, `email_draft: null`, and `sent: false`. Ambiguity may include safe candidate metadata. Never use candidates to select a report manually.

## Edge-case interpretation

- No date/broker candidate: `not_found` with a filename-shortlist reason.
- No ticker match: `not_found` with no selected report.
- Multiple ticker matches or unreadable/encrypted shortlisted PDF: `ambiguous`; stop.
- Encrypted, invalid, textless, or extraction-failed selected PDF: explicit configuration/CLI error; stop.
- No revisions: valid `partial` brief with `revisions.status = no_revisions`; omit the empty change section.
- Unclear rationale: `partial`; if escalation is required, display the draft and stop.
- Analyst email absent: preserve `[TODO: address]`; never infer an address.
- Model unavailable: do not invent rationale. Configure the local model or explicitly enable no-model mode.
- Citation viewer unavailable: preserve links and warn; start the matching loopback viewer.
- Stale citation: rebuild citations from the unchanged local source and do not reuse the stale ID.
- Partial output: return the validated renderer and material warnings without filling gaps.
