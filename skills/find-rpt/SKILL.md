---
name: find-rpt
description: Locate exactly one sell-side research report in the configured local corpus by Bloomberg ticker, date, and broker, then return the existing Python pipeline's evidence-backed brief. Use when the user invokes /find-rpt, asks to locate a local report using those three identifiers, or asks for a brief from one deterministically identified report. Do not use for general market research, external web research, or multi-report synthesis.
---

# Find one local research report

Use the installed Python pipeline as the only authority. Do not inspect PDFs, calculate revisions, construct citations, infer rationale, or rewrite the validated brief in the skill layer.

## Run

1. Parse exactly ticker, date, and broker. Preserve Bloomberg ticker punctuation and quoted broker text. Accept `YYYYMMDD`, `YYYY-MM-DD`, or `D Mon YYYY`; do not guess a missing field.
2. Resolve the directory containing this `SKILL.md`, then run its bundled launcher with explicit arguments when already parsed:

   ```text
   python <skill-directory>/scripts/find_rpt.py --ticker "<ticker>" --date "<date>" --broker "<broker>"
   ```

   For a raw slash-command string, pass it as one `--command` value. The launcher normalizes command syntax and then invokes `python -m find_rpt brief ... --format agent-json`.
3. Read [references/output-contract.md](references/output-contract.md) before interpreting the JSON.
4. Handle the returned `status` exactly:
   - `found`: return `rendered_markdown` unchanged.
   - `partial`: return `rendered_markdown` unchanged, then surface only material `warnings` not already visible.
   - `not_found`, `ambiguous`, `invalid_invocation`, `configuration_error`, `model_unavailable`, `malformed_cli_json`, `cli_error`, or `safety_error`: show the status and message; do not choose a report or fill missing fields.
   - If `citation_viewer_available` is false, state that links are preserved but require the local viewer. Suggest the documented viewer start command; do not replace citations.
5. Preserve every citation URL. Never recalculate estimates, add external financial knowledge, search the web for report facts, or merge another report.
6. If `requires_analyst_escalation` is true, display the generated draft contained in `rendered_markdown` and stop. Never send, launch a mail client, copy to a mail service, or act on an address.

## Output guardrails

Return the Python renderer's concise order: identity; title and takeaway; what changed; why changed and why now; estimate picture; first-read items; source/analyst; warnings; escalation draft. Omit nothing from the validated renderer and add no empty sections or filler.

Preserve adjusted versus reported metrics, units, currencies, fiscal periods, percentages versus percentage points, consensus distinctions, and explicit statements that context or rationale is unavailable. Never expose absolute local paths.

## Local-only safety

Use only the configured local corpus. Never copy, upload, attach, redistribute, annotate, or commit a report PDF or report-derived image. Never persist proprietary passages in logs or examples. The only supported model endpoint is loopback; `--no-model` produces a transparent partial brief.

Configuration precedence is launcher flags, environment variables, `find-rpt.toml`, then safe defaults. See the repository README for field names, citation-viewer startup, no-model mode, and troubleshooting.
