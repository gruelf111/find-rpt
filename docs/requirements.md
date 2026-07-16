# Requirements checklist

This checklist distinguishes mandatory requirements from preferences and optional submission guidance in `candidate_brief.pdf`. It also records the constraints of the current discovery task.

## Command and retrieval

- [x] RQ-001 (Required): Provide an agent skill or slash command named `/find-rpt`.
- [x] RQ-002 (Required): Accept exactly the user inputs `{ticker} {date} {broker}`.
- [x] RQ-003 (Required): Accept Bloomberg-style tickers such as `SAP GY` and `BP/ LN`.
- [ ] RQ-004 (Required): Search for the matching report in `corpus/` and handle the case where no matching report exists.
- [ ] RQ-005 (Required): Use the date and broker encoded in `{YYYYMMDD}_{Broker}_{hash}.pdf` to narrow retrieval.
- [ ] RQ-006 (Required): Resolve the ticker from report content because it is not present in filenames.
- [ ] RQ-007 (Required): Work from the single matched report; do not aggregate estimates or views across reports.

## Research brief content

- [ ] RQ-008 (Required): Return the report title.
- [ ] RQ-009 (Required): Return a one-sentence summary of the report's key message.
- [ ] RQ-010 (Required): Identify EPS revisions when present.
- [ ] RQ-011 (Required): Identify other estimate revisions when present.
- [ ] RQ-012 (Required): Present revisions as a list or table.
- [ ] RQ-013 (Required): For each revision, identify the line item, fiscal year, and percentage change.
- [ ] RQ-014 (Required): For each revision, show the difference versus consensus both before and after when the report supplies the required values.
- [ ] RQ-015 (Required): Explain the actual operational or financial drivers behind estimate changes rather than merely repeating that an estimate moved.
- [ ] RQ-016 (Required): Explain why the broker believes those drivers will affect earnings.
- [ ] RQ-017 (Required): Write the rationale in plain English for a generalist finance reader.
- [ ] RQ-018 (Required): Preserve generally accepted financial and accounting terms, but expand broker shorthand and house-specific KPIs into everyday English on first use.
- [ ] RQ-019 (Required): Keep the "why it changed, and why now" discussion to no more than two short paragraphs.
- [ ] RQ-020 (Required): Identify the report context, including whether it is a results preview/review, roadshow or management meeting, initiation, reiteration, or reaction to an event.
- [ ] RQ-021 (Required): State whether the broker spoke with management and identify the management participant(s) when the report gives them.
- [ ] RQ-022 (Required): Explicitly say when the report does not provide the context.
- [ ] RQ-023 (Required): Surface the estimate picture available in the report: consensus or street range, broker-versus-consensus comparison, scenario table, or broker old-versus-new estimates.
- [ ] RQ-024 (Required): Consider a visualization when it communicates the estimate spread more clearly than raw numbers.
- [ ] RQ-025 (Required): Include anything else material to a first read of a sell-side report.

## Evidence and citations

- [ ] RQ-026 (Required): Back material claims with evidence from the matched PDF.
- [ ] RQ-027 (Required): Attach citations inline where each fact or broker view is stated, rather than only listing a filename at the end.
- [ ] RQ-028 (Required): Link to the precise source location that supports the claim.
- [ ] RQ-029 (Required): Highlight the supporting passage so the reader lands on it directly.
- [ ] RQ-030 (Required): Sprinkle evidence links through the rationale wherever claims need support.
- [ ] RQ-031 (Required): Keep citations traceable to the source document without modifying the source PDF.

## Output shape and usability

- [ ] RQ-032 (Required): Produce a concise, easily readable, structured, scannable brief rather than a wall of text.
- [ ] RQ-033 (Required): Make the brief digestible in well under one minute.
- [ ] RQ-034 (Required): Lead with a one-glance header containing ticker, broker, date, and one-line takeaway.
- [ ] RQ-035 (Required): Order the brief as an analyst would read it: what moved, why, context, then the estimate picture.
- [ ] RQ-036 (Required): Clearly distinguish broker estimates, consensus values, reported results, and derived calculations.
- [ ] RQ-037 (Required): Avoid presenting unavailable or inapplicable values as numeric revisions; preserve states such as not meaningful or not supplied.

## Ambiguity escalation and email safety

- [x] RQ-038 (Required): Detect when revisions are present but the report's rationale is unclear.
- [x] RQ-039 (Required): In that case, offer to draft an email to the covering analyst.
- [x] RQ-040 (Required): Automatically compose a draft with questions specific to the unclear revision rationale.
- [x] RQ-041 (Required): Identify the covering analyst by name from the report.
- [x] RQ-042 (Required): Use `[TODO: address]` in the `To:` field when the analyst's email cannot be determined.
- [x] RQ-043 (Required): Surface the draft to the user and stop.
- [x] RQ-044 (Required): Never send the email without user review and a separate explicit action.
- [x] RQ-045 (Required): Do not include any automatic-send path in the skill.

## Platform, packaging, and submission

- [x] RQ-046 (Required): Implement the skill for an agent harness capable of exposing the command contract.
- [x] RQ-047 (Preference): Work seamlessly in Claude Code and/or Codex, the stated primary environments.
- [x] RQ-048 (Required submission): Include the skill/plugin implementing `/find-rpt`.
- [x] RQ-049 (Required submission): Include a short README explaining enablement and required configuration.
- [x] RQ-050 (Required submission): Include safe synthetic example runs; real-corpus transcripts remain local pending final submission review.
- [x] RQ-051 (Required submission): Demonstrate the full output shape and at least one source citation in the examples.
- [ ] RQ-052 (Required submission): Include the AI/agent development transcripts or logs.
- [ ] RQ-053 (Optional): If possible, publish the package as a GitHub repository and share its link.
- [ ] RQ-054 (Required): Do not upload or commit the research report files to the repository.
- [ ] RQ-055 (Required): Do not redistribute the reports outside the project.
- [ ] RQ-056 (Allowed): AI use is permitted and encouraged, but the implementation must be rigorously verified.
- [ ] RQ-057 (Allowed): The architecture, tools, libraries, and AI assistants are not prescribed.

## Discovery-phase constraints

- [x] DQ-001: Inspect `candidate_brief.pdf` carefully.
- [x] DQ-002: Inspect the corpus without modifying any PDF.
- [x] DQ-003: Perform discovery only; do not implement the full solution yet.
- [x] DQ-004: Do not redistribute report content or include long quotations.
- [x] DQ-005: Record discovery findings in `docs/discovery.md`.
- [x] DQ-006: Record this requirements checklist in `docs/requirements.md`.
