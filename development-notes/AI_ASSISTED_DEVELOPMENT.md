# AI-assisted development record

This is a submission-safe summary. It contains no report passages, real analyst contacts, screenshots, model prompts containing source text, secrets, or hidden system instructions.

## Tools and roles

- Codex was used to inspect the repository, propose bounded changes, edit code and documentation, run tests, and coordinate local verification.
- Local Python code using `pypdf` and PyMuPDF performed authoritative selection, extraction, arithmetic, geometry, and validation.
- A deterministic fake rationale model exercised schema and grounding behavior in synthetic tests.
- Real report contents were never sent to an external model or service. Real semantic evaluation requires a separately configured loopback model.

## Major task summaries

1. Converted the assignment brief into deterministic retrieval, evidence, revision, rationale, citation, rendering, escalation, and packaging slices.
2. Built conservative validators that remove unsupported model claims and reject ambiguous report selection.
3. Added a local highlighted citation viewer with source-fingerprint validation.
4. Added a review-only analyst clarification draft with immutable `sent: false` state and no delivery architecture.
5. Packaged the pipeline as a thin Codex skill and optional Claude Code command.
6. Performed final submission evaluation, including a twelve-report sample, clean installation, packaged invocation, and repository safety scans.

## AI-assisted decisions

- Report selection, arithmetic, unit/period alignment, evidence coordinates, citation identity, and escalation materiality remain deterministic Python responsibilities.
- Model reasoning is bounded to one selected report and a capped evidence payload.
- Any unsupported driver, context, participant, metric, period, number, or evidence ID is removed before rendering.
- No-model mode is transparent partial output, never a semantic fallback.
- Missing analyst identity or address remains missing; no identity or address is inferred.

## Rejected or corrected output

- Early retrieval logic could select a readable candidate while another shortlisted PDF was unreadable; it was changed to return ambiguity.
- Serialized retrieval evidence initially risked exposing report lines; it was reduced to safe location/classification metadata.
- Proximity-only and valuation-only causal claims were rejected by deterministic validation.
- Broad table highlights were narrowed to metric/period-aligned words and cells.
- A May 28 report was initially missed because its text layer collapsed a ticker into a compact delimited token; exact delimited compact-token support was added with a prose false-positive guard.
- A parenthesized research-analyst role was initially missed; the name parser was narrowed to accept that explicit form while still excluding ESG contacts.

## Manual verification

- Source PDFs were rendered locally and inspected without modifying them.
- The evaluation distinguishes automated checks, human field checks, and unmeasured real-model semantics.
- Citation targets were opened through the loopback viewer and checked for report, page, and highlight precision.
- Generated real-report output and renderings remained ignored local artifacts and were not committed.

## Limitations discovered

- Real semantic rationale accuracy is not measured without a configured local model.
- Dense or wrapped tables can produce conservative misses or unresolved candidates.
- Retrieval examines only the first two pages for identity.
- Analyst extraction deliberately misses some irregular layouts rather than infer identity.
- The citation viewer requires a running loopback server and an unchanged source PDF.

The chronological development record and command results are in `DEVELOPMENT_LOG.md`; architecture decisions are in `docs/decisions.md`; evaluation metrics are in `docs/evaluation.md`.
