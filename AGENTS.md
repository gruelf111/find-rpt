# AGENTS.md

These instructions apply to every agent and every file in this repository.

## Source-document safety

- Treat `briefing.pdf` and everything under `corpus/` as immutable, read-only source material. If the supplied brief is named `candidate_brief.pdf`, treat it identically.
- Never rename, edit, annotate, move, delete, commit, copy, upload, attach, publish, or redistribute a report PDF.
- Never add a report PDF, a PDF excerpt, or report-derived page image to Git, examples, logs, issues, pull requests, external services, or submission artifacts.
- Keep generated indexes, evidence coordinates, citation artifacts, caches, and rendered inspection images local and ignored by Git.
- Do not send report contents to an external API or service. Prefer a small local implementation with no unnecessary infrastructure or external dependencies.

## Retrieval scope and determinism

- For each `/find-rpt {ticker} {date} {broker}` query, select one report and work only from that single report. Do not aggregate facts, estimates, consensus, or views across reports.
- Use deterministic Python logic for corpus inventory, filename parsing, PDF validation, broker/date filtering, ticker normalization and matching, arithmetic, unit and period alignment, table/value validation, evidence page and bounding-box locations, and output validation.
- Make selection failures explicit. Return no match or an ambiguity result when deterministic evidence cannot identify exactly one report.
- Never invent or silently infer a ticker match, estimate, estimate revision, rationale, analyst, email address, consensus value, report context, or source location.
- Preserve distinctions among reported and adjusted values, actuals and estimates, broker and consensus values, source-stated and derived values, and calendar and fiscal periods.
- Label deterministic calculations as derived and retain the inputs used to validate them.

## Model responsibilities

- Use model reasoning only to interpret evidence from the selected report and write a concise, plain-English brief.
- Do not let model reasoning choose files, perform authoritative arithmetic, manufacture missing fields, or create evidence coordinates.
- Attach inline evidence to every material factual claim and broker view. Each citation must resolve to the selected source PDF's precise page and highlighted passage.
- A page-only or filename-only citation is insufficient when a precise passage exists.
- Explicitly state when the report does not give the context or the rationale. Do not fill gaps with general knowledge or information from another report.
- Expand broker shorthand and house-specific KPIs on first use while retaining standard financial and accounting terminology.
- Keep the rationale section to no more than two short paragraphs.

## Required response order

Render a scannable brief in this order:

1. **One-glance header** - ticker, broker, query/corpus date, report title, and a one-sentence takeaway. Show the internal publication date too when it differs materially from the query/corpus date.
2. **What changed** - EPS and other revisions by line item and fiscal period, including percentage change and before/after consensus comparison when the selected report supplies the necessary data.
3. **Why it changed** - the actual operational or financial drivers and why the broker believes they affect the estimates, in plain English.
4. **Context / why now** - identify results preview or review, management meeting or roadshow, initiation, reiteration, or event reaction; identify management participants when stated; otherwise say the context is not given.
5. **The estimate picture** - show the report's old/new, broker/consensus, range, or scenario evidence and use a minimal visualization only when it materially improves comprehension.
6. **Other first-read items** - include only material rating, target-price, valuation, catalyst, risk, or caveat information supported by the selected report.
7. **Ambiguity escalation, only when triggered** - when revisions exist but their rationale is unclear, say so, offer and produce a draft addressed to the named covering analyst, use `[TODO: address]` if the address is unavailable, surface the draft, and stop.

Keep evidence inline throughout this order rather than collecting unsupported filenames at the end. The result must be concise enough to read in well under one minute.

## Email safety

- Never implement an automatic email-send path, mail client integration, or send-capable external service.
- An escalation may draft an email only. It must require user review and a separate explicit user action outside this skill before anything can be sent.
- Select the covering research analyst from explicit report evidence; do not substitute sales, ESG, disclosure, or inferred contacts.

## Engineering discipline

- Prefer a small, understandable local Python implementation over services, databases, frameworks, orchestration layers, or infrastructure that the core workflow does not require.
- Add or update relevant tests with every substantive behavior change, then run those tests before considering the change complete.
- Test negative and ambiguous cases as well as the happy path, including invalid PDFs, ticker aliases, broker aliases, date mismatches, missing fields, table states such as `NA`/`ns`/`n.m.`, and citation-coordinate validation.
- Verify after substantive changes that no PDFs or generated report artifacts are tracked by Git.
- Keep `README.md` current with installation, configuration, command usage, limitations, and test instructions.
- Keep `docs/decisions.md` current with material architecture and interpretation decisions, alternatives considered, and verification evidence.
- Keep `DEVELOPMENT_LOG.md` current with AI-assisted development activity and decisions required for the submission. Record enough context to audit the work without copying report content.
- Never put secrets, report passages, PDF screenshots, recipient watermarks, or proprietary report data in documentation, tests, fixtures, transcripts, or logs.
