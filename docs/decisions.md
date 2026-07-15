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
