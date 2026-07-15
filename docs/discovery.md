# Discovery findings

## Scope and method

This is a read-only discovery pass over `candidate_brief.pdf` and `corpus/`. No PDF was renamed, moved, edited, annotated, or committed. The review combined:

- filename inventory and validation;
- text extraction with `pypdf` and word/bounding-box inspection with `pdfplumber`;
- rendered page inspection with `pypdfium2`;
- full first-page text checks across all parseable PDFs; and
- full-page text and layout checks on seven reports from distinct broker families.

The report examples below identify structures and short labels only. They intentionally avoid reproducing substantive report passages.

## Corpus inventory

### Size and dates

There are 173 files with a `.pdf` extension in `corpus/`.

| Filename date | Files |
| --- | ---: |
| 2026-05-11 | 139 |
| 2026-05-28 | 33 |
| 2026-06-22 | 1 |
| **Total** | **173** |

Of those 173 files, 172 are valid, parseable PDFs. One file is a 192-byte plain-text service error saved with a `.pdf` extension:

`20260528_Goldman Sachs_922f12ee6b63791acb7d0cae28d83f59.pdf`

The 172 valid PDFs contain 1,729 pages. Report length ranges from 1 to 81 pages, with a median of 9 pages. None is encrypted according to `pypdf`.

### Brokers

The corpus contains 29 distinct broker labels.

| Broker | Files | Broker | Files |
| --- | ---: | --- | ---: |
| ABG Sundal Collier | 7 | Alantra Equities Sociedad de Valores, S.A. | 7 |
| Berenberg | 7 | Bestinver Securities | 2 |
| BNP Paribas | 7 | BofA Global Research | 7 |
| CIC Corporate & Institutional Banking | 7 | Citi | 7 |
| Danske Bank Commissioned Research | 1 | Danske Bank Research | 7 |
| Degroof Petercam | 2 | Deutsche Bank Research | 7 |
| DNB Carnegie | 7 | Goldman Sachs | 8 |
| ING Wholesale Banking | 2 | Intermonte Securities | 2 |
| Jefferies | 7 | JP Morgan | 7 |
| KBC Securities | 4 | Kepler Cheuvreux | 8 |
| Morgan Stanley | 7 | Nordea Equity Research | 7 |
| Oddo BHF Corporates & Markets | 7 | Panmure Liberum | 4 |
| Pareto Securities | 7 | Rothschild & Co Redburn | 7 |
| Stifel Nicolaus | 7 | UBS | 7 |
| Zurcher Kantonalbank | 7 |  |  |

### Filename pattern

Every corpus filename matches:

```text
^(?<date>\d{8})_(?<broker>.+)_(?<hash>[0-9a-f]{32})\.pdf$
```

Observed properties:

- Dates are eight digits in `YYYYMMDD` form.
- Broker labels are variable-length and may contain spaces, commas, periods, and ampersands.
- The final token is always a 32-character lowercase hexadecimal hash.
- Broker parsing must be greedy up to the final underscore/hash pair; splitting blindly on every underscore is unsafe as a general design.
- Tickers and company names are absent from filenames.
- File validity cannot be inferred from the extension alone.

The filename date is best treated as the query/corpus date because the brief explicitly says date is encoded in the filename. It is not necessarily the PDF's internal publication date. The sole `20260622` file, for example, displays a 19 June 2026 release date internally while the brief's example treats it as 22 June. The output should expose both values when they differ instead of silently replacing one with the other.

## Representative layout inspection

Seven first pages were rendered and inspected, with later pages checked where needed for tables.

| Broker | Layout and retrieval observations |
| --- | --- |
| ABG Sundal Collier | A fast-comment layout: narrative and a small chart dominate the left column; rating, security codes, price/target, next event, and analyst contacts sit in a right sidebar. The code line combines a local identifier and Bloomberg ticker. There is no estimate-change table on the inspected event note. |
| BofA Global Research | Dense two-column first page with the thesis on the left and a structured right rail containing date, key changes, analyst team, stock data, Bloomberg/Reuters codes, and a glossary. A compact estimate/consensus table is embedded below the narrative. This is favorable for extraction but reading order must be reconstructed. |
| J.P. Morgan | Long `Our Take` prose and bullet sections occupy the main column; rating, ticker, price target, analysts, and sales contacts are in a narrow right rail. Actual-versus-house-versus-consensus tables begin later. Extraction order interleaves header/sidebar/main text unless coordinates are used. |
| Goldman Sachs | A management-meeting note with a wide narrative column and a separate analyst panel. The title uses a Reuters-style code in parentheses rather than a Bloomberg-labelled field. It is rationale-rich but may contain no estimate revisions. |
| Nordea Equity Research | Page 1 is highly structured: thesis and rationale at top left, identifiers and rating information at top right, then summary figures and an `Estimate Changes` table across the bottom. This is an ideal vertical-slice fixture because narrative, ticker, analyst, rating, estimates, and context coexist on one page. |
| ODDO BHF | Dashboard-like first page with recommendation/target banner, price chart, share data and forecast rail, central result-versus-estimate table, narrative sections, and analyst details. Some tables extract with lost spacing, so geometric table parsing is needed. |
| Kepler Cheuvreux | A research dashboard: current/prior rating and target, Bloomberg/Reuters codes, revision percentages, thesis headings, forecast table, consensus EPS, valuation, and analyst appear on page 1. The page is information-rich and is the exact style used by the brief's worked example. |

Additional observed layout classes include one-page brief-news notes, multi-page model books, accessible text variants, results previews, event reactions, management-meeting takeaways, and commissioned research. A broker name alone does not determine whether revisions or consensus comparisons exist.

## Text-layer assessment

The corpus is suitable for text-first retrieval with layout-aware verification.

- All 172 valid PDFs yielded at least 1,105 non-whitespace characters from page 1; no valid file had an empty or near-empty first page.
- Across the seven fully inspected samples, every page yielded words and positioned character objects. The sample contained 62 pages, and none had a zero-word page.
- `pdfplumber` recovered word bounding boxes and detected tables on BofA, J.P. Morgan, Nordea, ODDO BHF, and Kepler sample pages. This makes coordinate-based evidence highlighting feasible without changing the originals.
- Plain text extraction is not layout-faithful. Multi-column pages can emit sidebar content before the thesis, table cells can collapse together, and charts may contribute labels in non-visual order.
- Character decoding is imperfect. Examples include replacement characters for euro signs or curly punctuation, non-breaking hyphens, and a misdecoded rating arrow. Extraction and output need Unicode normalization while retaining the original page coordinates.
- Text presence does not imply semantic quality. Logos, disclosures, repeated recipient watermarks, footers, chart labels, and accessibility duplicates add noise.
- The one invalid `.pdf` must be rejected during cataloging with a clear corpus-integrity diagnostic, not passed to the extraction model.

OCR should therefore be a fallback, not the default. The first implementation can reject or flag image-only pages; later support can add OCR behind the same positioned-word interface.

## How required fields appear

### Bloomberg tickers

Ticker notation is inconsistent even when the underlying security is clear:

- Explicit labelled forms: `Bloomberg SYNSAM SS`, `Bloomberg: SHA0 GR`, `Bloomberg code: ISP IM`.
- Combined fields: `Bloomberg/Reuters codes: BNOR NO / BNOR.OL`.
- Tabular fields: separate Reuters, Bloomberg, exchange, and ticker columns.
- Mixed title lines: `CPG.L, CPG LN`, where Reuters precedes Bloomberg without labels.
- Combined local/Bloomberg code: `ERIC.B-SE/ERICB SS`.
- Alternate punctuation: `ARGX:BB` rather than `ARGX BB`.
- Country suffix variation: German instruments appear with both `GR` and `GY` conventions in the project materials.
- Reuters-only title use: Goldman Sachs may place a code such as `FBK.MI` in the title and omit a Bloomberg-labelled code on the first page.
- No visible ticker: one-page brief-news formats can identify only the company, rating, and target price.

Ticker matching should normalize whitespace, colon separators, slash-bearing roots, exchange aliases, and case, but retain the raw displayed form for evidence. Matching must not confuse Reuters/local codes with Bloomberg codes.

### Analyst names

Analyst identity appears as:

- explicit name, role, phone, and email in a sidebar (BofA, J.P. Morgan, Goldman Sachs, Nordea, ODDO BHF);
- a single named covering analyst below the thesis;
- multiple research analysts plus a separate specialist-sales contact;
- email addresses only, from which a name might be inferred but is not explicitly printed in the extracted reading order (ABG sample);
- separate equity and ESG analysts on the same page.

The escalation flow needs an explicit covering-analyst selection rule. It should prefer the lead equity/research analyst, avoid specialist sales and ESG contacts, and never invent a name from an address without marking the inference.

### Estimate tables and revisions

At least five patterns are present:

1. A `Previous` versus `Current` key-changes table by fiscal year (BofA).
2. An `Estimate Changes` matrix containing percentage revisions across multiple line items and years (Nordea).
3. Revision percentages embedded in the page header plus a separate forecast/consensus table (Kepler).
4. Actual, house estimate, prior-year, and change columns in a results table, with consensus comparisons in adjacent prose (ODDO BHF).
5. Actual versus house versus consensus tables on later pages (J.P. Morgan).

Tables may use calendar years, fiscal year-end month labels such as `03/27e`, quarter/half-year periods, reported versus adjusted metrics, mixed currencies/units, parentheses for negatives, or states such as `ns`, `n.m.`, and `NA`. Values in narrative prose may be more informative than detected tables.

### Ratings and target prices

Rating language includes uppercase labels, sentence prose, and transitions:

- standalone `HOLD`;
- `Reiterate Rating: NEUTRAL` with a price objective;
- `Overweight` with a dated target;
- `Neutral` with an arrow/icon;
- `Hold (Buy)` showing current and prior rating;
- prose such as "Buy rated" in a valuation section.

Target prices may be called target price, price target, price objective, PO, TP, or fair value. They can include prior/current values, currency, upside/downside, and establishment or horizon dates. `n.a. on Hold` is a valid non-numeric target state and must not be coerced.

### Consensus comparisons

Consensus appears in several forms:

- a dedicated `Consensus EPS` row beside broker forecasts;
- actual, house, and consensus values in one table;
- a source-qualified consensus row, for example a named data provider;
- inline comparisons such as reported/house/consensus triplets;
- narrative predictions about likely changes to consensus;
- qualitative claims that consensus is high or low without a numeric range.

The system must keep observed consensus values separate from the broker's prediction about future consensus movement. It should calculate spreads only when units, periods, and bases align, and label calculations as derived.

### Rationale and context passages

Useful rationale tends to be anchored by broker-specific headings, including variants of:

- `Why this report?` and `Deconstructing the forecasts`;
- `Our Take`, `Noteworthy Areas`, and `Outlook & Guidance`;
- `Our view` in a one-page news note;
- a thesis paragraph followed by operational-driver headings;
- results, valuation, and investment-conclusion sections.

The rationale may link revisions to margins, pricing/mix, foreign exchange, investment income, costs, regulation, demand, utilization, or company guidance. Context can be explicit in the title or opening paragraph: results review, preview, management meeting, conference call, or reaction to an external event. Management interaction may identify a CEO, investor relations, or only "initial discussions with management."

## Main retrieval and extraction edge cases

### Retrieval

- A `.pdf` extension can mask a non-PDF error payload.
- Date semantics are ambiguous: filename/query date may differ from internal release, writing, publication, price, or market-data dates.
- Broker input may vary from the exact filename label (`J.P. Morgan` versus `JP Morgan`, `ODDO BHF` versus the full corpus label).
- Ticker is not indexed in filenames and can be absent, Reuters-only, or represented with punctuation/suffix variants.
- The same date/broker pair often has several reports, so ticker resolution is essential.
- A report can mention many peer or event-company tickers; the subject security must be distinguished from incidental mentions.
- Multiple securities or share classes can appear on one report.
- Short tickers can collide with ordinary words if matching is not field- or boundary-aware.
- Corporate aliases, renamed companies, dual listings, ADRs, and local/Bloomberg/Reuters variants can produce false negatives.
- Duplicate or near-duplicate accessible versions may exist inside a PDF's extracted content even when there is only one file.

### Extraction

- Multi-column reading order can mix narrative, sidebars, footers, and disclosures.
- Tables can collapse spaces or reorder cells; narrative revisions may not appear in tables.
- Old/current, actual/estimate, reported/adjusted, and broker/consensus values are easy to mislabel.
- Fiscal periods vary by issuer and may not align with calendar years.
- Percent changes may be explicitly reported or may need calculation; the two must be distinguished.
- Consensus before-and-after is often not fully supplied. Missing values must remain missing rather than being inferred.
- Currency symbols and punctuation can decode incorrectly.
- Rating arrows/icons may not survive text extraction, while nearby parenthetical ratings do.
- Analyst panels may contain multiple authors, sales contacts, ESG analysts, and disclosure names.
- The report context or revision rationale can be absent, implicit, or split across pages.
- Existing PDF hyperlinks do not provide the required claim-level highlighted destination.
- Disclosures and recipient watermarks create repeated noise and should be excluded from evidence retrieval.
- A report can be relevant but contain no revisions; this should produce an explicit no-revision result, not trigger ambiguity escalation.
- "Revisions exist, rationale unclear" is different from "no revisions" and requires a separate confidence decision.

## Proposed minimal architecture

```text
/find-rpt arguments
        |
        v
query normalization
        |
        v
validated corpus catalog ---- filename metadata + PDF validity
        |
        v
date/broker candidate filter
        |
        v
ticker identity resolver ----- labelled fields, title/company, aliases
        |
        v
layout-aware extractor ------- words + bounding boxes + tables
        |
        v
structured brief model ------- values + evidence spans + confidence
        |                 \
        v                  v
validators              ambiguity gate
        |                  |
        v                  v
brief renderer          draft-by-name, never-send response
        |
        v
local citation viewer ------ page + highlight rectangles over original PDF
```

Minimal components:

1. **Skill wrapper**: a small Codex/Claude-compatible skill definition that validates `/find-rpt {ticker} {date} {broker}` and invokes a deterministic local CLI.
2. **Corpus catalog**: a generated local index containing path, parsed filename date/broker/hash, PDF validity, page count, internal dates, subject company, normalized ticker candidates, and evidence locations. Invalid files remain catalog records with an error status.
3. **Normalizer and resolver**: exact date matching, broker aliases, Bloomberg ticker canonicalization, and scored subject-security matching. It returns one match, no match, or an explicit ambiguity list; it never silently chooses a low-confidence report.
4. **Layout-aware document adapter**: `pdfplumber` positioned words as the common interface, with text blocks and table candidates. `pypdf` supplies metadata and a fast fallback. OCR can be added later behind the same interface.
5. **Structured extraction schema**: report identity, title, one-line takeaway, rating/target changes, revisions by metric/period, consensus values, rationale, context, management contact, other first-read items, and evidence spans. Every substantive field carries document/page/bounding boxes and extraction confidence.
6. **Validation layer**: checks period/unit alignment, recomputes stated revision percentages when inputs exist, distinguishes source values from derived values, prevents unsupported claims, and applies the rationale-ambiguity gate.
7. **Local citation viewer**: serves the original local PDF in a PDF.js-style viewer and overlays highlight rectangles from the evidence spans. Inline links encode a document ID, page, and rectangles. A plain `#page=N` link is a fallback, not sufficient for the final requirement.
8. **Renderer and safe escalation**: produces the sub-minute brief. If revisions exist but rationale confidence is below threshold, it adds a named analyst email draft with specific questions and stops. The package contains no email-send integration.

Generated catalog and citation-coordinate files should remain local/ignored. The original PDFs stay immutable and outside Git.

## Implementation plan as testable vertical slices

### Slice 1: Safe catalog and exact candidate narrowing

Build a CLI that inventories `corpus/`, parses filenames, validates PDF signatures/parsing, and filters by exact filename date plus normalized broker.

Acceptance tests:

- reports 173 corpus entries, 172 valid PDFs, and the known invalid payload;
- returns the expected candidate counts for each date/broker pair;
- handles broker punctuation and aliases;
- never writes to or stages a PDF.

### Slice 2: Ticker-to-report retrieval

Extract identity blocks from candidate first pages, normalize Bloomberg variants, and score the subject security separately from incidental mentions.

Acceptance tests:

- resolves explicit forms such as space, colon, and combined Reuters/Bloomberg fields;
- supports a slash-bearing ticker root;
- returns no-match or ambiguity instead of guessing;
- records both filename date and internal publication date when they differ.

### Slice 3: One evidence-backed identity response

For a single fixture, return ticker, broker, both relevant dates, title, rating, target price, analyst, and inline links to a local page/rectangle highlight viewer.

Acceptance tests:

- clicking each link opens the correct original PDF page with the correct words highlighted;
- source files remain byte-for-byte unchanged;
- missing fields are explicit and unsupported fields are absent.

### Slice 4: Complete revision path on the Kepler fixture

Implement the brief's worked-report class end to end: old/current rating and target, multi-year revisions, consensus EPS, rationale, context, valuation, and first-read caveat.

Acceptance tests:

- extracted percentages and periods match the page;
- derived consensus spreads are arithmetically verified and labelled derived;
- the rationale is plain English, at most two short paragraphs, and every material claim has evidence.

### Slice 5: Generalize estimate and consensus structures

Add adapters/heuristics for BofA previous/current tables, Nordea percentage-change matrices, ODDO actual/estimate/consensus prose, and J.P. Morgan later-page actual-versus-expected tables.

Acceptance tests:

- preserves adjusted/reported distinctions, currencies, units, and fiscal periods;
- does not coerce `NA`, `ns`, or `n.m.`;
- leaves consensus-before/after blank when not supplied;
- identifies source-stated versus system-calculated changes.

### Slice 6: Context and rationale across note types

Handle results reviews/previews, event reactions, one-page news, and management-meeting notes. Add glossary expansion for house shorthand.

Acceptance tests:

- identifies management meeting participants where explicit;
- says context not given when absent;
- produces a valid no-revision brief for rationale-rich event notes;
- keeps the rationale within the two-paragraph limit.

### Slice 7: Ambiguity escalation with no send path

Add the three-way gate: no revisions, revisions with supported rationale, revisions with unclear rationale. Implement lead-analyst selection and draft generation only for the third state.

Acceptance tests:

- names the lead covering analyst rather than sales/ESG contacts;
- inserts `[TODO: address]` when needed;
- questions refer to the specific unexplained metric/period;
- surfaces the draft and stops;
- static/package tests confirm there is no email-send capability.

### Slice 8: Packaging and submission evidence

Package the skill for Codex and, if practical, Claude Code; write setup/configuration documentation and capture several representative runs.

Acceptance tests:

- clean-install smoke test succeeds;
- examples cover match, no match/ambiguity, revisions with citations, and escalation;
- at least one example demonstrates a clickable highlighted citation;
- `git ls-files` contains no PDFs, generated citation artifacts, secrets, caches, or virtual environments;
- development transcripts/logs are included without report content redistribution.

## Recommended first implementation fixtures

- Kepler Schaeffler: richest single-page match to the brief's example and a date-mismatch test.
- Nordea Synsam: compact percentage revision matrix plus clear rationale and explicit Bloomberg/analyst fields.
- BofA Hannover Re: previous/current values, consensus, glossary, and dense multi-column ordering.
- J.P. Morgan Compass: sidebar identity plus later actual/house/consensus tables.
- Goldman Sachs FinecoBank: management-meeting context with no obvious revision table.
- ABG Ericsson: combined local/Bloomberg identifiers and analyst-email-only extraction behavior.
- The invalid Goldman-labelled payload: catalog validation and graceful failure.
