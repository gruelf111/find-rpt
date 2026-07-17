---
name: find-rpt
description: Locate exactly one sell-side research report in the configured local corpus by Bloomberg ticker, date, and broker, then use the active Codex agent only to interpret a bounded evidence bundle before Python validates and renders the evidence-backed brief. Use when the user invokes /find-rpt, asks to locate a local report using those three identifiers, or asks for a brief from one deterministically identified report. Do not use for general market research, external web research, or multi-report synthesis.
---

# Find one local research report

Use Python as the authority for retrieval, evidence, revisions, arithmetic, analyst extraction, citations, validation, and rendering. Use the active Codex model only for the bounded semantic fields below. Never inspect the PDF directly or add outside knowledge.

## Agent-hosted workflow

1. Parse exactly ticker, date, and broker. Preserve Bloomberg ticker punctuation and quoted broker text. Accept `YYYYMMDD`, `YYYY-MM-DD`, or `D Mon YYYY`; do not guess a missing field.
2. From the configured project environment, run:

   ```text
   python -m find_rpt agent prepare "<ticker>" "<date>" "<broker>" --corpus "<configured-corpus>" --format json
   ```

3. Stop on `not_found`, `ambiguous`, or an error. Otherwise, reason only over `validated_revisions`, `candidate_rationale_passages`, and `candidate_context_passages`. Treat `allowed_metric_ids`, `allowed_fiscal_period_ids`, and supplied `block_id` values as closed allowlists. Use `normalized_request` and `selected_report_identifier` only to confirm identity. Treat `analyst_candidates` and `warnings` as read-only deterministic metadata; never copy analyst data into semantic JSON.
4. Produce exactly one JSON object matching this schema, with no Markdown wrapper and no extra keys:

   ```json
   {
     "rationale_clarity": "clear|partial|unclear",
     "drivers": [{"driver":"", "impacted_metrics":[], "fiscal_periods":[], "category":null, "evidence_block_ids":[], "causal_link":"explicit|inferred", "confidence":"high|medium|low"}],
     "why_now": null,
     "report_context": "results_preview|results_review|roadshow|management_meeting|initiation|reiteration|rating_change|event_reaction|other|not_given",
     "context_evidence_block_ids": [],
     "management_contact": "true|false|unknown",
     "management_evidence_block_ids": [],
     "people_met": [],
     "one_line_takeaway": null,
     "jargon_definitions": [],
     "important_first_read_items": [],
     "warnings": []
   }
   ```

   Grounded claims use `{"text":"", "evidence_block_ids":[], "confidence":"high|medium|low"}`. People use `{"name":"", "role":null, "evidence_block_ids":[]}`. Jargon definitions use `{"term":"", "definition":"", "evidence_block_ids":[]}`. Use only source-stated names and numbers. Use only allowlisted metric and fiscal-period identifiers. Do not create page numbers, URLs, bounding boxes, revisions, consensus values, analyst identities, or email addresses. Use `null`, empty arrays, `not_given`, `unknown`, or `unclear` when support is absent.
5. Pass that JSON to stdin of the deterministic finalizer:

   ```text
   python -m find_rpt agent finalize "<ticker>" "<date>" "<broker>" --corpus "<configured-corpus>" --input - --format agent-json
   ```

6. Read [references/output-contract.md](references/output-contract.md). Display only `rendered_markdown` from the finalizer. Never display the evidence bundle, draft semantic JSON, validator diagnostics not present in the final output, or self-authored report prose.

If semantic validation fails, the finalizer returns a partial brief with warnings. Display that validated partial output; never retry with looser claims and never silently fall back to unsupported prose.

## Guardrails

Keep rationale and why-now to at most two short paragraphs in the rendered result. Expand broker shorthand and house-specific key performance indicators on first use while retaining standard financial terminology. Do not infer causal links from proximity.

Preserve every finalizer-generated citation URL. If `citation_viewer_available` is false, preserve the links and surface the finalizer's warning. If analyst escalation is present, display the review-only draft and stop. Never send, open a mail client, copy to a mail service, or act on an address.

Use only the local corpus. Never copy, upload, attach, redistribute, annotate, or commit a report PDF or report-derived image. The Codex host model is used only in this skill workflow. Standalone CLI use must select `FIND_RPT_MODEL_MODE=api` with a configured loopback API key or use `FIND_RPT_MODEL_MODE=none`/`--no-model`.
