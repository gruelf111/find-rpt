# Implementation decisions

## 2026-07-16 - First retrieval slice

### Bounded inspection

The retriever reads page 1 for all files shortlisted by filename date and broker. It stops on a unique strong match. Page 2 is read only when page 1 cannot decide safely. This keeps inspection bounded while accommodating reports whose security identifiers move to a second-page header.

Alternative considered: index every page in advance. Rejected for this slice because it performs unnecessary report access and adds cache/index lifecycle concerns.

### Deterministic evidence ranking

Ticker evidence uses fixed weights: explicit Bloomberg field, explicit ticker field, first-page header/title, first-page body, later-page header, then later-page body. A match needs both a strong score and a safe lead over the runner-up. Weak or close results are ambiguous.

Field labels may be on the line immediately above their values in extracted tables. The scorer therefore considers the preceding two extracted lines when classifying a matching value as an explicit Bloomberg/ticker field; it does not broaden the ticker match itself.

Alternative considered: model-based report selection. Rejected because selection must be repeatable, auditable, and incapable of inventing a match.

### Normalization

Date accepts compact or ISO form. Broker matching ignores case, spaces, and punctuation. Ticker matching ignores punctuation and spacing, making `BP/ LN` and `BP LN` equivalent. `GY` and `GR` are canonicalized as the same German Bloomberg suffix because both appear in the project materials.

### Output contract

The same result object renders to JSON or concise text. It carries the status, normalized query, reason, optional single match, all ranked candidates, inspected pages, evidence, and parse errors. No result path exists for a silent low-confidence choice.

### Evaluation data

The manually verified evaluation file stores only ticker/date/broker inputs and expected local filenames. It intentionally excludes PDF content, snippets, screenshots, or derived research data.

## 2026-07-16 - Skeptical self-review hardening

### Unreadable candidates

An earlier implementation ignored a shortlisted candidate after a parse failure and could select another readable file. That did not prove uniqueness: the unreadable file could have been the requested report. Any inspection error now blocks selection and returns `ambiguous` with a sanitized error category.

### Evidence privacy

Evidence previously included up to 240 characters of the extracted matching line. A body match could therefore expose report prose in terminal output, JSON, test failures, or logs. Evidence now includes only page, extracted line number, classification, normalized matched ticker, and score. Raw report text and report-derived text fingerprints are not serialized.

### Input and filename strictness

Date parsing now accepts only `YYYYMMDD` and `YYYY-MM-DD`; arbitrary punctuation is rejected. Tickers must contain exactly one code and a two-letter exchange suffix. Filename hash and PDF extension matching are case-insensitive for cross-platform consistency. Empty broker inputs are rejected.

### False-positive controls

Field labels must look like compact field/table headers, not merely contain words such as Bloomberg or ticker in prose. Unlabelled header evidence is strong only in the first 25 extracted lines or on a compact code-like paired-identifier line. Other early matches are weak and cannot select a report.

### Portability and residual assumptions

Serialized candidate paths use `/` and omit absolute workstation paths. Symlink candidates are rejected. Ranking scores and the 20-point margin are conservative hand-set policy values, not calibrated probabilities. The remaining material limitation is multi-security report identity: a strongly labelled non-primary ticker could still look authoritative without company-entity resolution.

## 2026-07-16 - PDF evidence layer

### PyMuPDF block model

The evidence layer runs only after deterministic retrieval selects one report. It uses PyMuPDF text blocks because corpus discovery found usable positioned text across representative layouts and no concrete reason to add OCR or another layout engine. Retrieval remains on `pypdf`; evidence extraction is a separate adapter so selection behavior does not change.

The public schema is nested as document, pages, reading-order blocks, and words. Each non-empty text block retains a stable ID, exact extracted text, bounded PDF-point box, reliable `text` type, PyMuPDF source block number, and word boxes with zero-based PyMuPDF line/word metadata. Page boundaries and dimensions remain explicit. Images are not evidence blocks. PyMuPDF's internal zero-based page index is converted at the adapter boundary; API and JSON page numbers are one-based.

Alternative considered: words or individual spans. Rejected for this slice because they create much noisier references; page-scoped blocks are the smallest useful unit for later passage selection while preserving exact geometry.

### Stable identity and resolution

A document ID is SHA-256 over the PDF bytes, so it is reproducible without depending on an absolute path. A block ID combines that document ID, one-based page, reading-order position, source block number, rounded coordinates, and text. Repeated extraction of unchanged bytes therefore produces the same identifier and ordering, while changed content or geometry invalidates it.

Alternative considered: using the corpus filename hash as document identity. Rejected because explicit-path debugging PDFs may not follow the corpus naming convention and filenames are not authoritative content hashes.

Some real PDFs contain text boxes extending just beyond their media box. Coordinates are clipped to the page boundary and degenerate boxes are omitted so downstream consumers always receive valid rectangles. No OCR fallback is attempted: an unreadable, encrypted, textless, or invalid-page request raises a distinct evidence error.

The JSON source path remains relative and portable. Extraction writes no files and never annotates or rewrites a PDF. A future citation viewer may consume these coordinates, but viewer generation, estimate extraction, and model summarization remain out of scope.

### Verification

Tests cover a two-page synthetic PDF, stable JSON and IDs, word coordinates, page filtering, CLI direct-path extraction, malformed/unreadable/encrypted/textless input, and every block/page reference across ABG, BofA, J.P. Morgan, Nordea, and Kepler layouts. The corpus-derived text and coordinates exist only in memory during tests and are not stored in fixtures or logs.

### Pre-commit review

The release-gate review ran the actual locator-based CLI twice for five different broker/layout families. Page sequences, page-bound rectangles, block counts, and repeated IDs passed for all pages. Block order was compared with PyMuPDF's `sort=True` sequence and manually spot-checked for sensible header/body progression. This is deterministic geometric reading order, not semantic table reconstruction, and no broker-specific coordinates or parsing branches were introduced.

The candidate diff contains only the existing `pypdf` dependency plus PyMuPDF. It contains no service, OCR engine, database, cache implementation, report excerpt, absolute path, or generated evidence file. The PDF corpus is ignored and no PDF is tracked.

## 2026-07-16 - Deterministic estimate-revision candidates

### Three-state result and schema

Revision extraction runs only on the one `EvidenceDocument` produced from a uniquely selected report, or on the one PDF explicitly supplied with `--pdf-path`. Its result is `revisions_found`, `no_revisions`, or `candidates_unresolved`; the third state prevents revision-like language or a poorly reconstructed table from being silently treated as either a valid row or a clean no-revision report.

The row schema extends the suggested fields with `period_basis`, `stated_change_pp`, `calculated_change_pp`, and `extraction_method`. `period_basis` preserves fiscal, calendar, and unspecified year labels. Percentage-point changes are separate from relative percentage revisions, so a margin move is not misrepresented. `extraction_method` distinguishes prose, aligned old/new tables, grouped multi-year old/new/change tables, percentage-only matrices, compact headers, and inline stated changes. Evidence contains only one-based page numbers and stable block IDs; source passages are not copied into revision JSON.

Units remain compact canonical strings such as `EUR`, `EURm`, `EURbn`, `EUR/share`, `%`, `percentage_points`, and `basis_points`. Currency, scale, per-share basis, and rate basis are therefore not collapsed. The `Eu`/`Eu mn` abbreviation is normalized as an explicit euro/euro-millions label; no broker-dependent parsing branch is currently enabled. Broker-specific behavior, if later required, must enter through the isolated `RevisionExtractor.extract(..., broker=...)` boundary rather than being scattered through generic parsers.

### Conservative deterministic parsers

Candidate blocks require an explicit combination of metric, revision, period/value, old/new, consensus, or estimate-change signals. Parsing then supports:

- prose `from old to new`, `to new from old`, and explicit `new versus old before` statements;
- aligned old/new/current/previous tables with optional consensus and change columns;
- grouped multi-year new/old/change tables reconstructed from word geometry;
- percentage-only estimate-change matrices; and
- compact `Change in <metric>` headers.

All table joins stay on one page and require explicit aligned headers, periods, metric labels, and value columns. A separate consensus table may enrich an extracted revision only when page, normalized metric, qualifier set, period, and normalized unit match exactly and identify one observation; its block is retained as additional evidence. Cross-page, fuzzy, ambiguous, qualifier-mismatched, and unit-mismatched joins are prohibited. The extractor does not carry a parent metric into an unlabeled subrow or infer an old value from a stated percentage. Directional consensus language without a number leaves `consensus_value` null. Duplicate source statements with conflicting values are retained and warned rather than arbitrarily resolved.

Alternative considered: use a model to classify tables or complete missing rows. Rejected for this milestone because the deterministic implementation produces useful partial output, exposes its unresolved layouts, and satisfies the no-fabrication constraint. No LLM or external service was added.

### Arithmetic policy

Relative revision is `(new - old) / abs(old) * 100`. The absolute denominator makes movement from a loss to a smaller or larger loss directionally interpretable. A zero old value has no relative percentage and emits `zero_old_value_no_relative_revision`. Consensus spreads use the same absolute-denominator convention and remain null for zero consensus.

For percentage-valued metrics the extractor also calculates `new - old` in percentage points; basis-point values are converted to percentage points for that field. Source-stated and calculated changes reconcile within an absolute tolerance of 0.25 percentage points. Display rounding can exceed that tolerance, in which case the row is retained with a mismatch warning. Arithmetic is suppressed on currency, scale, or basis mismatches.

### Evaluation data and privacy

The real-report regression file stores only broker, filename, expected status, and expected row count. It contains no report passage, financial value, coordinate, screenshot, analyst data, or content hash. All source text and coordinates stay in memory during tests. Visual inspection images were written only to the operating-system temporary directory and are not repository artifacts.

### Pre-commit review findings

The 11-report CLI review found three material issues and fixed them without adding a dependency or broker-specific branch: abbreviated accounting qualifiers were not consistently preserved, a safe same-page consensus table was left unlinked, and disclosure-only pages could be classified as unresolved candidates. Qualifier normalization now covers common abbreviated forms, consensus joining follows the exact policy above, and generic legal/research-disclosure phrases are excluded before candidate scoring.

The review distinguishes automated validation from manual field verification. All 178 emitted rows are repeatable and all 493 referenced block IDs resolve to their source pages; a representative 32-row sample across all six revision-bearing reports was manually checked for metric/qualifier, period, unit, row linkage, arithmetic representation, null handling, and source passage. Dense nested and wrapped table rows remain conservative omissions rather than inferred output.

## 2026-07-16 - Bounded rationale and report-context extraction

### Deterministic passage boundary

Rationale extraction consumes the one `EvidenceDocument` already selected by deterministic retrieval and the corresponding deterministic `RevisionResult`. Revision evidence blocks are mandatory anchors. The selector adds at most two same-page neighbors on either side, signal-bearing passages, nearby-page passages containing revised metrics, opening-page context, and the first blocks of an explicitly cross-referenced page. Disclosure noise is excluded before signal scoring.

The final model input is capped at 24 blocks and 12,000 extracted characters. Revision rows are grouped into metric/direction/period summaries instead of sending all numeric rows. The result records exact input block and character counts. `--no-model` exercises this complete selection path and returns the candidate passages while marking interpretation as skipped.

Alternative considered: give the model the whole PDF or all extracted text. Rejected because it would enlarge the confidentiality surface, weaken single-report claim auditing, and make failures harder to reproduce.

### Provider boundary and confidentiality

`RationaleModel` is the provider protocol. `DeterministicFakeRationaleModel` supports repeatable unit tests. The configured implementation uses an OpenAI-compatible chat-completions envelope but accepts only loopback HTTP(S) endpoints. Its key, URL, and model name come from environment variables; there is no hard-coded key or `.env` loader. A missing key is an explicit configuration error, and a non-loopback URL is rejected before any request is made.

Alternative considered: enable a general external API provider. Rejected because repository policy prohibits sending report contents to an external service. This means real-report semantic evaluation requires a user-configured local model; absence of one is recorded as an evaluation limitation rather than bypassed.

### Structured prompt and validation

The system prompt allows interpretation and plain-English compression only. It forbids external knowledge, proximity-only causation, invented events/people/roles/periods/metrics/numbers/block IDs, and citation URL generation. Output is a single schema-shaped object containing clarity, drivers, why-now, context, management interaction, people met, takeaway, jargon, first-read items, and warnings.

Python validates every cited ID against both the selected document and the bounded passage set. It removes unsupported claims and numbers, unknown periods and metrics, people whose names do not appear in evidence, and ungrounded context. It downgrades `explicit` causal links when the passage lacks direct causal language and changes a revision-bearing result to `unclear` when no validated driver remains. Malformed model output returns `model_error` with an explicit warning and no fallback prose.

Alternative considered: add a second model verification pass immediately. Rejected for this milestone because deterministic validation already enforces evidence identity, lexical/numeric support, enum/schema correctness, and causal-language gates. A second bounded verifier can be added later if local-model evaluation shows materially unsupported claims surviving these checks.

### Context and management signals

Context patterns identify results previews/reviews, roadshows, management meetings, initiations, reiterations, rating changes, and event reactions. They are hints supplied to the model, not authoritative classifications. Management interaction requires explicit meeting/roadshow/hosted language near management, CEO, CFO, chief-officer, or investor-relations wording. Names and roles remain model-interpreted but must resolve literally to cited selected passages.

The initial Windows CLI corpus sweep exposed non-CP1252 symbols in candidate passages. Standard streams are now reconfigured to UTF-8 when supported, preserving valid JSON without changing source text or writing artifacts.

### Adversarial review hardening

The release-gate review found that the initial boundary checks were necessary but not sufficient. A caller could supply a `RevisionResult` from another document, an unexpected provider exception could escape the safe result path, extra schema fields were ignored, model confidence had no deterministic meaning, and a nearby fact could survive when its block also contained unrelated causal wording. Dense revision evidence could also crowd a results-preview block out of the 24-block budget.

The extractor now rejects cross-document revision data before building a payload. Top-level and nested claim schemas are exact and length/count bounded; invalid provider warnings are filtered to short machine-readable codes. All provider and validation failures return a sanitized `model_error`. The first occurrence of each direct context category receives deterministic selection priority, which preserved results-preview evidence in the dense real-corpus case without increasing the block or character caps.

Driver validation is sentence-scoped. `explicit` requires direct causal wording plus sufficient driver-term support in the same cited sentence. `inferred` requires explicit hedged causal wording, not simple adjacency. Proximity-only output is removed. A `valuation only` driver is accepted only for target-price linkage and cannot explain an earnings metric. Management participants require both literal name evidence and an explicit interaction in the cited block; role-specific words must resolve. Jargon definitions are limited to a small deterministic standard glossary or an explicit source definition.

Confidence is recalculated by Python. A high-confidence driver has direct causal support and supported metric/period linkage; medium means explicit support is incomplete or the source itself hedges the causal link; low is reserved for minimal surviving linkage. Grounded non-driver claims use deterministic lexical/evidence concentration rather than the model's self-assessment.

## 2026-07-16 - Precise local citation viewer

### Viewer instead of annotated derivative PDFs

The citation target is a small standard-library HTTP server bound to loopback. It
uses PyMuPDF to render only the cited page in memory and overlays validated boxes in
an inline SVG. This avoids a remote PDF.js/CDN dependency, does not copy or rewrite
the source, and keeps the implementation within the existing dependency set. The
viewer also exposes the indexed original PDF behind an opaque document-ID route and
the correct page fragment, but the highlighted page is the authoritative citation
surface.

Alternative considered: temporary annotated derivative PDFs. Rejected because a
browser overlay is easier to delete, does not create another report file, supports
multiple translucent boxes without changing source bytes, and has a smaller risk of
accidental redistribution. There is deliberately no annotated-PDF fallback. A safe
render failure is explicit.

### Document and citation identity

Document identity remains `sha256:<content digest>`, calculated from PDF bytes and
independent of absolute path. Citation records additionally retain source byte size,
the full digest, and a safe corpus-relative filename. The server recomputes size and
digest before every citation, page-image, or original-PDF response. A mismatch is a
stale citation and returns conflict instead of rendering.

Citation IDs are a SHA-256-derived `cit-` token over schema version, document ID,
one-based page, ordered validated block IDs, and deterministic metric/period line
selectors. Labels, absolute paths, host, and port are excluded. The ID therefore
remains repeatable for an unchanged source and claim evidence while distinct fiscal
periods sharing a table block can receive distinct claim-specific highlights.

### Bounding-box validation and merge policy

Every request names the selected document ID and one or more existing evidence block
IDs. Unknown or cross-document references fail and emit no citation. Coordinates
must be finite, ordered, and within page dimensions with a documented 0.5-point
tolerance; accepted coordinates are clipped to the exact page edge. Word boxes are
preferred. Adjacent words on the same extracted line merge only when the horizontal
gap is at most four points and their vertical ranges overlap. Lines and distant
cells remain separate.

For a deterministic revision request, Python carries the already validated metric
and period into the geometry selector. It keeps the metric label, the requested
period header/cells, old/new/change cells aligned to the metric row, and necessary
consensus evidence. A compact label with separate numeric cells adds only cells to
its right; a compact prose/header line that already contains values does not absorb
unrelated same-height columns. If the selector cannot find a safe line, it falls
back to all validated words in the evidence block and records a warning rather than
inventing coordinates.

### Multi-page evidence

A citation record is single-page. Evidence IDs spanning pages are grouped by their
actual source page and emitted as separate citations, each with
`split_from_multi_page_evidence`. This avoids a link that lands on one page while
claiming to highlight evidence elsewhere.

### Cache and server security

The ignored `.cache/find-rpt/citations/index.json` stores fingerprints, portable
filenames, block IDs, geometry, short labels, validation state, and URLs; it stores
no report text or absolute path. The server accepts loopback addresses only,
suppresses request logs, applies no-store and restrictive browser headers, rejects
unrecognized ID-shaped routes and traversal, and resolves only regular non-symlink
PDFs beneath the configured corpus. Direct paths are never URL parameters.

### Final review hardening

The release-gate review made the loopback origin part of the citation-builder
boundary as well as the server boundary: a base URL must be a plain loopback HTTP
origin with an explicit port. This prevents generated user-facing citation metadata
from pointing at a remote or path-prefixed origin. The original-PDF route also uses
the source filename from the citation record that just passed fingerprint
validation, rather than trusting duplicated document-index filename metadata. Cache
records whose embedded citation ID differs from their index key, or whose page
geometry is empty/non-finite, now fail closed.

## 2026-07-16 - Structured research-brief rendering

### Validated-model boundary and section order

`ResearchBriefBuilder` consumes `ReportMetadata`, `RevisionResult`, `RationaleResult`, and `CitationBuildResult`. It does not receive report text, parse a PDF, call a model, calculate an authoritative revision, or generate evidence geometry. A separate deterministic metadata adapter supplies a conservatively selected page-one title and evidence-backed analyst records. The later escalation milestone extended that adapter to retain an explicitly named research analyst without an address while preserving missing fields. Missing metadata remains a warning.

The Markdown/text order is one-glance identity, title/takeaway, what changed, why it changed and why now, estimate picture, first-read items, source/analyst information, and material warnings. Empty optional sections are omitted. This follows analyst reading order while keeping source identity and completeness caveats visible.

### Materiality, revision ordering, and length target

The concise view targets roughly 100-250 words before model-generated rationale, no more than two short rationale paragraphs, eight revision rows, two comparison panels, and four first-read items. The caps are deterministic rather than character truncation. Rows with consensus and complete old/new observations receive selection priority; selected rows are then ordered revenue, EBITDA, EBIT, margins, EPS, tax/interest/share count, target price, then other metrics and fiscal period. The brief reports the number omitted, and JSON preserves the structured concise-view result. Missing values use `—` and are never back-filled.

Only arithmetic warnings that can change interpretation are shown beside the table: unit/consensus incompatibility, zero denominators, stated/calculated mismatches, and conflicting candidates. Extraction diagnostics remain structured but do not become a wall of user-facing warnings.

### Terminal visualization

The estimate picture is a dependency-free, zero-axis bar chart over discrete old, new, and consensus observations. Every line uses the same absolute scale within its panel; negative values extend left and positive values right. The label includes the validated unit, and number formatting avoids adding source precision. It does not draw a continuous range. A panel is omitted unless at least two distinct finite observations and one unit exist. The same plain text is embedded in Markdown code fences and returned as the terminal fallback.

### Citation bindings and partial failure

Citation identity remains evidence-based and excludes claim prose. Because several claims can legitimately share the same citation ID, `CitationBuildResult` now carries claim-to-citation bindings in addition to de-duplicated records. This preserves stable URLs while allowing every rendered claim to resolve inline.

Retrieval ambiguity, unusable evidence, model failure, or a total citation-builder error stops rendering. A failed or invalid individual citation causes the affected fact to be omitted, with a material partial-brief warning. Metadata, revisions, rationale, and citations must share one document identity; metadata may omit its identity only for backwards-compatible synthetic callers. No revisions, unresolved revision candidates, `--no-model`, missing title/analyst, and omitted rows produce a transparent partial brief with material warnings. The brief CLI always extracts the full selected PDF and exposes no page-limited option. Skill packaging remains outside this milestone.

## 2026-07-16 - Ambiguity escalation and review-only analyst drafting

### Deterministic trigger and partial-rationale policy

`AmbiguityEscalationBuilder` consumes only the selected report's `ReportMetadata`, `RevisionResult`, and validated `RationaleResult`. The default trigger requires parsed revisions, `unclear` rationale, and at least one material revision without a validated driver for the same metric and fiscal period. Clear rationale never triggers. Missing semantic interpretation is reported as unavailable rather than treated as unclear.

Partial rationale is opt-in through `EscalationPolicy(escalate_partial=True)` and the CLI's `--escalate-partial` option. Even then, it triggers only when a material revision remains unexplained. This avoids drafting merely because a report uses cautious language while preserving an explicit route for incomplete rationale.

Alternative considered: trigger on every `partial` result. Rejected because it would create false escalations when every material change is already covered and only an immaterial row remains incomplete.

### Materiality rules

Relative revisions are material at an absolute 3% threshold. Negative bases retain the revision extractor's `(new-old)/abs(old)` convention and are labelled separately in the assessment. Zero denominators are never compared with the relative threshold. Percentage and margin observations use the validated percentage-point fields and a separate absolute 1 percentage-point threshold; the relative percentage is not substituted. Rating and target-price changes are material when they actually change. A non-numeric row is material only when validated structured data carries `explicitly_marked_material` or its equivalent report-derived indicator.

Alternative considered: apply 3% to every numeric-looking field. Rejected because percentage-point margins, zero bases, and unitless/non-numeric changes do not support that comparison.

### Lead-analyst selection and unresolved recipients

The metadata adapter now retains explicit named analysts even when an address is absent. It supports multi-line, pipe-delimited, and same-line contact blocks, explicit designations, roles, phones, and geometry-bounded name/address association. Same-column and nearest-line rules prevent cross-column address attachment. Generic research headings, organization abbreviations, sales, ESG, disclosure, media, and publishing contacts are excluded.

An explicitly supported `covering` or `lead` status is preferred. Without that evidence, every relevant named analyst is addressed rather than choosing one by order or broker convention. Names and addresses are never derived from each other. A missing address produces exactly `[TODO: address]`; a missing name produces a neutral greeting and a warning. PDF metadata is not currently used because the evidence document does not expose a validated metadata field and visual report evidence is stronger.

### Question construction and deduplication

Questions are deterministic templates populated from the unresolved revision's metric, qualifiers, period, old/new values, relative or percentage-point change, consensus comparison, incomplete validated drivers, context, and management interaction. Metric-specific assumption menus keep questions concrete without adding facts. A driver suppresses a question only when its validated metric and fiscal period answer that revision. Rows sharing metric, qualifiers, and period are merged; if their observations conflict, the merged question omits the conflicting values rather than repeating or resolving them.

Alternative considered: require a model to write or deduplicate the questions. Rejected because the structured inputs support concise deterministic questions, which are easier to test and cannot introduce new facts. No model-assisted polishing is enabled; the deterministic implementation is the only path.

### No-send architecture and stopping behavior

`EmailDraft` is an immutable data model. Renderers can display it in Markdown, JSON, or text, but no component accepts credentials, talks to a mail provider, launches a client, creates a `mailto:` action, invokes a shell mail command, copies to the clipboard, or exposes a delivery method. The brief renderer places the escalation last and ends with the statement that the draft has not been sent. `find-rpt escalation` exposes the same review-only model without citation or delivery side effects.

A source/dependency guard test rejects named mail libraries, providers, credential variables, client links, and delivery entry points. Any use of the draft requires separate user review and action outside this repository.

### Final adversarial-review hardening

The final review found three material boundary gaps. First, JSON relied on the absence of a send method and the rendered not-sent sentence but did not carry an explicit machine-readable status. `EmailDraft` and `EscalationResult` now expose frozen, non-initializable `sent: false` fields. Second, a generic revision warning string could activate explicit materiality. Only the dedicated validated `materiality_indicators` field can now do so; confidence and warnings cannot override missing evidence. Third, standalone Markdown/text no-model output previously hid `rationale_clarity_unavailable` behind a generic no-escalation sentence. It now surfaces structured warnings.

The analyst evidence audit also made the existing evidence tuple include explicit phone and lead/covering-role evidence used by the extracted fields. A regression assertion resolves each synthetic analyst field back to those evidence blocks. The no-send guard was expanded to cover draft-delivery names, provider endpoints, email credential variables, and clipboard integrations in addition to the original libraries and client actions.
