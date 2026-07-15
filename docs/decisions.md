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
