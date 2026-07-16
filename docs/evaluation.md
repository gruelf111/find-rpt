# Retrieval, evidence, revision, bounded-rationale, citation, and brief evaluation

Evaluation date: 2026-07-16

## Scope

This evaluation covers deterministic report retrieval, the PDF evidence layer, deterministic estimate-revision extraction, bounded rationale-passage retrieval, the rationale model boundary, post-model grounding validation, precise local citation highlighting, and final structured brief rendering. Analyst-email escalation and skill packaging remain out of scope. No external service is used.

The evaluation dataset contains query metadata and expected local filenames only. This document contains no report text, extracted passages, analyst contact data, report screenshots, or PDF-derived artifacts.

## Automated verification

Command:

```text
PYTHONPATH=src python -m unittest discover -s tests -v
```

Original retrieval milestone result: **21 tests passed; 0 failed; 0 skipped.**

Pre-commit evidence-layer review result: **28 tests passed; 0 failed; 0 skipped.**

Revision-candidate pre-commit review result: **41 tests passed; 0 failed; 0 skipped.**

Bounded-rationale adversarial-review result: **60 tests passed; 0 failed; 0 skipped.**

Citation final-review result: **77 tests passed; 0 failed; 0 skipped.**

Brief-renderer focused result: **22 synthetic/CLI/corpus test methods passed; 0 failed; 0 skipped.**

Final renderer-review suite result: **102 tests passed; 0 failed; 0 skipped.** Python compilation and `pip check` also passed; Ruff and mypy are not configured or installed.

Coverage includes:

- filename date and normalized broker shortlisting;
- punctuation and spacing normalization for Bloomberg tickers;
- page-1 early exit and bounded page-2 fallback;
- explicit-field, header, weak-body, tied, and near-tied evidence handling;
- human-readable and JSON output;
- malformed input and missing corpus handling;
- invalid, encrypted, unreadable, and symlinked PDF candidates;
- sanitized errors and evidence output that excludes report text;
- case-insensitive PDF extensions and filename hashes; and
- portable relative result paths.

Revision coverage additionally includes:

- positive, negative, and zero-denominator arithmetic;
- percentage changes, percentage points, and basis points;
- currency, millions/billions, per-share, and rate units;
- fiscal, calendar, quarterly, half-year, and unspecified period labels;
- adjusted, diluted, reported, ordinary, basic, stated, restated, and other common qualifiers, including abbreviated forms;
- prose old/new statements, aligned tables, grouped multi-year tables, and percentage-only matrices;
- explicit numeric consensus spreads, exact same-page consensus-table enrichment, and directional consensus with no fabricated value;
- disclosure-only pages excluded from revision candidate scoring;
- unit mismatch, rounded-value mismatch, conflicting-source, `NA`, `n.m.`, and `ns` behavior;
- stable page/block evidence resolution and repeatable JSON; and
- direct-path plus locator-backed `revisions` CLI integration.

Rationale coverage additionally includes:

- revision-anchored candidate passages, adjacency, nearby-page signals, opening context, and deterministic size bounds;
- results preview/review, roadshow, management meeting, initiation, reiteration, rating change, and event-reaction signals;
- explicit names and roles for management participants;
- valid, invented, and unselected evidence block references;
- clear, partial, and unclear rationale outcomes;
- revisions with no explanation and reports with no estimate revisions;
- unsupported drivers, metrics, fiscal periods, numbers, context, management contact, people, and takeaways;
- malformed model JSON, missing schema fields, missing API configuration, and loopback-only provider configuration;
- deterministic fake-model behavior and repeatable structured output;
- UTF-8 CLI output on Windows; and
- fifteen local reports with repeatable inputs bounded to 24 blocks and 12,000 characters.

Citation coverage additionally includes stable IDs, selected-document checks,
evidence-to-page resolution, finite/in-bounds geometry, word/line box merging,
multi-line and multi-block passages, multi-page splitting, invalid and
cross-document block IDs, changed sources, invalid citation IDs, traversal,
unindexed files, loopback binding, correct page routes, no-store headers, cache
privacy, revision/rationale structured-input adapters, and period-specific table
highlight narrowing.

Brief coverage additionally includes complete and partial briefs, no revisions, missing consensus, old/new/consensus comparisons, clear/partial/unclear rationale, absent context, management meetings, rating changes, negative and zero estimates, percentage-point margins, long metric names, multiple periods, citation presence/absence, visualization scaling/omission, Markdown/JSON/text, deterministic ordering, no empty sections, ambiguous retrieval, partial pipeline failure, conservative metadata, and shared-evidence claim bindings.

## Research-brief rendering evaluation

The complete `brief --no-model` path was exercised in memory across the eleven manually verified locator cases and eleven broker/layout families. This ran retrieval, full PDF evidence, revision extraction, bounded rationale passage selection, conservative front-matter extraction, citation construction, structured brief assembly, and all three renderer code paths without saving proprietary briefs. It intentionally used `--no-model`: no loopback rationale endpoint or key was configured, and policy prohibits sending report passages externally.

| Measure | Result |
| --- | ---: |
| Real reports attempted | 11 |
| Correct deterministic report selections | 11 / 11 |
| Briefs produced in transparent partial mode | 11 / 11 |
| Revision status distribution | 6 found / 3 unresolved / 2 none |
| Validated source revision rows available | 178 |
| Rows retained in concise views | 34 |
| Rendered source/title/analyst/revision citation links counted | 52 |
| Total title, date, analyst, and revision citations built | 199 |
| Failed citation requests | 0 |
| Reports with a comparison visualization | 5 / 11 |
| Comparison panels | 8 |
| Conservatively identified report titles | 11 / 11 |
| Unique internal publication dates / material date differences shown | 8 / 2 |
| Explicit analyst records | 8 across 4 reports |
| Visible brief word count, min / max / average | 55 / 214 / 105.3 |
| Absolute local paths in rendered output | 0 |
| Proprietary generated briefs saved to repository | 0 |

The materiality policy caused the three numeric consensus comparisons in the BofA layout to remain visible despite its 46-row extraction result. Reports with only percentage matrices, no unit, one observation, or equal observations omitted the visualization. Negative-value reports used the zero-axis representation. Every displayed revision row had at least one local citation; multi-source rows retained additional links through claim bindings.

Synthetic output was manually read for section order, compactness, missing-value symbols, percentage versus percentage-point language, table alignment, negative/zero bars, inline citation placement, empty-section omission, and Markdown/text readability. All eleven real partial outputs were below 300 words and the longest was 214 words after the final review caps. This supports partial-format readability, but it is not a claim that every real semantic brief can be read in under one minute: real rationale and first-read prose were unavailable without a local model.

### Accuracy and release-gate findings

- Retrieval remained 11/11 and the previously validated 178 revision rows were unchanged.
- Citation construction resolved every rendered row and produced zero failed requests. The renderer does not create page coordinates or repair invalid citations.
- Every rendered title, analyst, and revision citation used by the BofA, Nordea, and Kepler partial briefs was opened through the live loopback viewer and returned HTTP 200. This exercises link resolution but is not substituted for the unavailable visual/manual review of three complete semantic briefs.
- The front-matter adapter found a cited title candidate on all eleven first pages and a unique top-of-page publication date on eight; two differed from the corpus/query date and are shown separately. Eight analyst records survived the strict printed-name-plus-explicit-email rule; missing analysts remained warnings rather than inferred contacts.
- No model-generated real-report rationale, context classification, management participant, takeaway, or first-read claim was produced. Therefore real rationale grounding, unsupported-claim count, context accuracy, and semantic one-minute readability remain **not measured**, not zero.
- Synthetic validation retained no unsupported claim from the existing adversarial rationale suite. The renderer adds no factual prose beyond fixed descriptions of structured status/context fields.
- Three complete real briefs could not be opened end to end because no local rationale model was configured. The citation builder and runtime corpus test did validate all citations used by the partial briefs, but this is not represented as the requested visual/manual review of three complete semantic briefs.

Known rendering limitations:

- The eight-row concise view is a deterministic materiality policy, not issuer-specific judgement; omitted count is explicit.
- Front-matter title selection is geometric/lexical and conservative but has not had an independent eleven-report semantic title audit.
- Analyst extraction requires name and email in the same evidence block, so split sidebars are intentionally missed.
- JSON represents the concise view and omission count; it does not dump every extracted revision row.
- Unicode block bars require a terminal font with block glyphs; values remain the plain-text fallback on each line.
- Real semantic/manual release gates require a configured loopback model and local human review. No email escalation or skill packaging is present.

## Precise citation evaluation

The locator-backed `citations build` command was run for five revision-bearing
broker/layout families. The ignored local cache contained 176 citations across the
five selected documents. A complete deterministic validation pass resolved
**176/176** against the current source size, digest, page, block IDs, and boxes, with
zero failed resolutions. No report text, screenshots, coordinates, or local URLs
from the cache are committed.

| Measure | Result |
| --- | ---: |
| Citations generated | 176 |
| Citations resolving successfully | 176 / 176 |
| Failed evidence resolutions | 0 |
| Manually opened real citations | 10 |
| Broker/layout families manually reviewed | 5 |
| Correct-page rate | 10 / 10 (100%) |
| Correct-passage highlight rate | 10 / 10 (100%) |
| Overly broad highlights after refinement | 0 / 10 |
| Stale-citation detection | Pass (build, validator, and HTTP 409) |
| Invalid/traversal/unindexed/arbitrary-path HTTP checks | 4 / 4 rejected with HTTP 404 and no path disclosure |
| Repeated citation-ID generation | 176 / 176 identical |
| Multiple-block real citations | 165 |

Every sample citation was regenerated during the final review, opened in the
loopback viewer, and visually checked against the rendered source page. The first
manual pass found two viewer defects: evidence
anchors could run before image layout, and a table-sized block could highlight
unrelated rows. A later metadata audit found a compact row that retained its label
but lost separately positioned old/new cells. The final implementation uses a
normal-flow URL fragment for landing plus deterministic metric/period and same-row
cell selection. All ten final citations were re-opened after those fixes.

Only safe manual-review metadata is recorded:

| Document hash | Broker/layout | Page | Highlight boxes | Correct page | Relevant passage | Unrelated text included | Result |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| `870f45ba29947eb5` | BofA Global Research | 1 | 3 | Pass | Pass | No | Pass |
| `870f45ba29947eb5` | BofA Global Research | 1 | 7 | Pass | Pass | No | Pass |
| `ba6b57292ed2b5c5` | Nordea Equity Research | 1 | 3 | Pass | Pass | No | Pass |
| `ba6b57292ed2b5c5` | Nordea Equity Research | 1 | 4 | Pass | Pass | No | Pass |
| `cca068928dc517a6` | Intermonte Securities | 4 | 7 | Pass | Pass | No | Pass |
| `cca068928dc517a6` | Intermonte Securities | 4 | 7 | Pass | Pass | No | Pass |
| `2c440c5dc94f1a86` | Stifel Nicolaus | 1 | 1 | Pass | Pass | No | Pass |
| `7ac075ece8b8d0fe` | Kepler Cheuvreux | 1 | 2 | Pass | Pass | No | Pass |
| `7ac075ece8b8d0fe` | Kepler Cheuvreux | 1 | 2 | Pass | Pass | No | Pass |
| `7ac075ece8b8d0fe` | Kepler Cheuvreux | 1 | 2 | Pass | Pass | No | Pass |

Known viewer limitations:

- cited pages are rasterized at 1.5x and do not expose the source PDF's selectable
  text, native search, forms, or accessibility structure;
- a compact source line containing two fiscal periods can retain both because
  splitting a word-level source statement more aggressively could hide context;
- line narrowing depends on the embedded text geometry and has no OCR fallback;
- the ignored cache and a running matching loopback server are required for URLs;
  and
- the original-PDF link lands on the page but has no overlay; the local page viewer
  is the highlighted citation surface.

## Bounded-rationale evaluation

### Real-report passage retrieval

The `rationale --no-model` path was run on the eleven locator-backed, manually reviewed retrieval cases plus four direct-path context cases: a DNB Carnegie results preview, an ABG results review, and Goldman Sachs roadshow and management-meeting notes. This covers explicit revisions, unresolved revision signals, no revisions, results preview/review, rating change, roadshow, management interaction, and absent deterministic context signals. The locator-backed sample selected the expected PDF in 11/11 cases. No candidate passage, model prompt, coordinate, screenshot, person, or report-derived value was persisted.

| Measure | Result |
| --- | ---: |
| Reports evaluated in retrieval-only mode | 15 |
| Brokers/layout families represented | 13 |
| Locator-backed expected reports selected | 11 / 11 |
| Minimum / maximum selected blocks | 15 / 24 |
| Average selected blocks | 22.9 |
| Minimum / maximum passage characters | 3,337 / 11,998 |
| Average passage characters | 8,693.9 |
| Estimated total prompt + payload characters, min / max | 7,157 / 17,287 |
| Estimated total prompt + payload characters, average | 13,230.3 |
| Inputs exceeding configured bounds | 0 |
| Repeated inputs differing | 0 |
| Candidate block IDs/pages/text checked against source | 344 |
| Invalid IDs, page mismatches, text mismatches, or duplicates | 0 |
| Direct context scenarios retained in the bounded set | 5 / 5 |

The largest estimated input was 17,287 characters including the fixed prompt, revision summary, enums, JSON structure, and 11,923 passage characters. This is roughly a few thousand tokens and was not flagged as unexpectedly large. The original eleven reports comprise six `revisions_found`, three `candidates_unresolved`, and two `no_revisions`; the four context cases add one preview with revisions, one unresolved results review, one no-revision roadshow, and one unresolved management-meeting note.

### Semantic and validation findings

No local rationale model endpoint or API key was configured during this run. Repository policy prohibits sending report passages to an external API, so real-report semantic generation was not performed. Consequently, no model-generated real-report claim exists to review, and the following requested accuracy measures are intentionally recorded as not measured rather than estimated:

| Requested measure | Result |
| --- | --- |
| Real-report rationale clarity distribution | Not measured - no local model configured |
| Explicit real-report drivers correctly identified | Not measured - no local model configured |
| Unsupported real-report drivers before validation | Not measured - no local model configured |
| Unsupported real-report drivers remaining after validation | Not measured - no local model configured |
| Correct real-report context classifications | Not measured - deterministic signals are retrieval hints only |
| Incorrect real-report context classifications | Not measured - deterministic signals are retrieval hints only |
| Real-report management-interaction extraction accuracy | Not measured - passage retrieval passed 1/1 management sample |

| Additional requested metric | Synthetic/manual validation result |
| --- | --- |
| Rationale clarity distribution | 4 clear / 1 partial / 4 unclear across 9 schema-valid synthetic cases |
| Manually checked driver claims | 6 synthetic claims |
| Correctly supported driver claims | 2 direct explicit claims retained |
| Partially supported driver claims | 1 source-hedged inferred claim retained |
| Unsupported claims produced before validation | 3 drivers: invented evidence, proximity-only fact, valuation-as-earnings rationale |
| Unsupported claims remaining after validation | 0 |
| Report-context classification accuracy | 1 / 1 validated synthetic output; 5 / 5 real context signals retrieved, not semantically classified |
| Management-interaction extraction accuracy | 2 / 2 synthetic contacts; invented role removed |
| False-positive causal drivers after validation | 0 / 6 checked driver proposals |
| Missed material drivers | 0 in the constructed synthetic cases; not measured on real reports |
| Model parsing/provider failures | 3 injected / 3 failed safely with no extraction |
| Known unsupported layouts or report types | Real semantic accuracy not measured; split rationale/table layouts and implicit-causality notes remain unsupported release risks |

The synthetic figures above were manually checked against their committed non-proprietary source sentences as well as asserted automatically. They prove validation behavior, not real-corpus semantic accuracy. The adversarial cases specifically show that an invented block, a nearby but unlinked fact, an earnings claim based only on valuation/rating evidence, an incorrect management role, and an incorrect EPS definition do not survive unchanged.

Known failure cases and conservative behavior:

- a supported paraphrase can be removed when it has insufficient lexical overlap with its evidence;
- a direct causal link expressed without one of the bounded causal patterns is removed unless the source contains explicit hedged causal language;
- deterministic context patterns can retrieve multiple plausible hints and do not choose the authoritative context;
- management names and roles must appear literally in selected passages, so split-layout identity text can be omitted;
- the 24-block/12,000-character cap can omit a relevant distant passage, though direct context categories now receive reserved priority; and
- real-model accuracy and manual claim review remain a release gate requiring a configured local endpoint.

## Estimate-revision corpus evaluation

Eleven real reports across eleven brokers were run twice through the evidence and revision layers. The checked-in evaluation file contains only safe broker/filename/status/count metadata. Report text, values, coordinates, and screenshots are not persisted.

| Measure | Result |
| --- | ---: |
| Reports tested | 11 |
| Reports with emitted revisions | 6 |
| Reports with explicit no-revision result | 2 |
| Reports with unresolved revision candidates | 3 |
| Emitted revision rows | 178 |
| Manually checked revision rows | 32 |
| Correct manual row extractions | 32 / 32 |
| Referenced source blocks resolved automatically | 493 / 493 |
| Comparable stated-versus-calculated changes | 98 |
| Arithmetic reconciliations within tolerance | 79 / 98 (80.6%) |
| Rows warned for rounding/reconciliation mismatch | 19 |
| False-positive rows in the manual sample | 0 |
| Known missed explicit revision rows | 45 |
| Conflicting source candidates retained and warned | 2 |
| Rows enriched from an exact consensus table match | 3 |

All 178 emitted rows were validated automatically for deterministic repeatability, arithmetic recomputation, and evidence resolution. A representative 32-row sample was then compared manually with the source PDFs across all six revision-bearing reports: 8 rows from the aligned previous/current and percentage-matrix layout, 6 from a compact side-by-side table, 9 from the grouped multi-year table, 6 compact inline prose changes, and 3 target-price prose rows. The checks covered metric names and qualifiers, fiscal-period alignment, currency/scale/per-share/rate units, same-row or explicitly linked old/new provenance, stated and calculated changes, percentage points, consensus, warnings, and intentional nulls. All 32 sampled rows were correct and no sampled row was a false positive.

Representative pages from the five reports without emitted revisions were also inspected. Two contain no estimate revision and now return `no_revisions`; one of those had previously been an unresolved result caused solely by disclosure boilerplate. Three contain revision-like, guidance, actual-versus-consensus, or comparison language but no safely linked old/new broker estimate row; they remain `candidates_unresolved` and emit no fabricated values.

| Broker/layout | CLI result | Emitted rows | Manually checked rows | Representative coverage |
| --- | --- | ---: | ---: | --- |
| ABG Sundal Collier | `candidates_unresolved` | 0 | 0 | event narrative; no safely linked revision row |
| BofA Global Research | `revisions_found` | 46 | 8 | old/new table, percentage matrix, consensus |
| J.P. Morgan | `candidates_unresolved` | 0 | 0 | actual/guidance/consensus comparisons only |
| Nordea Equity Research | `revisions_found` | 18 | 6 | compact table and accounting qualifiers |
| Degroof Petercam | `revisions_found` | 1 | 1 | prose target-price change |
| Deutsche Bank Research | `candidates_unresolved` | 0 | 0 | comparison language without linked old/new estimates |
| Intermonte Securities | `revisions_found` | 104 | 9 | grouped table, negatives, percentage points |
| Jefferies | `no_revisions` | 0 | 0 | disclosure-only false candidate removed |
| KBC Securities | `no_revisions` | 0 | 0 | no revision passage |
| Stifel Nicolaus | `revisions_found` | 2 | 2 | conflicting prose candidates retained |
| Kepler Cheuvreux | `revisions_found` | 7 | 6 | compact inline percentage and old/new prose |

The 19 arithmetic mismatches are retained warnings, not extraction failures. They occur where displayed old/new values are too coarsely rounded to reproduce the source-stated percentage within the 0.25 percentage-point tolerance. Zero denominators and mismatched units do not enter the reconciliation denominator.

The 45 known misses are conservative omissions counted manually in two dense tables: 15 nested segment subrows whose metric would have to be inherited from a parent row, and 30 wrapped or abbreviated rows that are not safely normalized. Additional misses may exist in the three unresolved layouts and are not assigned a fabricated count. This evaluation therefore demonstrates high precision on the sampled emitted rows, not complete corpus recall.

The real set includes explicit old/new values, prose-only revisions, percentage-only matrices, exact same-page consensus comparisons, 24 emitted rows containing negative old or new values, 33 emitted rows with stated or calculated percentage-point treatment, two no-revision reports, and ambiguous or poorly reconstructed layouts. Three consensus rows were joined only because page, metric, qualifiers, period, and unit matched uniquely; the consensus block is included as separate evidence. Synthetic tests prove that qualifier or period mismatches remain null.

## Manually verified corpus cases

All cases inspected page 1 only. `high_explicit` means an explicit Bloomberg/ticker field; `strong` means compact first-page header/title evidence. These labels are deterministic policy categories, not probability estimates.

| # | Query | Expected PDF | Selected PDF | Confidence | Evidence class | Result |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `ERICB SS`, `20260511`, `ABG Sundal Collier` | `20260511_ABG Sundal Collier_0566b42f1d8750853347bf485216f764.pdf` | `20260511_ABG Sundal Collier_0566b42f1d8750853347bf485216f764.pdf` | `strong` | `header_or_title` | Pass |
| 2 | `HNR1 GY`, `2026-05-11`, `BofA Global Research` | `20260511_BofA Global Research_003c2de68007dc1805c646be0e369535.pdf` | `20260511_BofA Global Research_003c2de68007dc1805c646be0e369535.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 3 | `CPG LN`, `20260511`, `J.P. Morgan` | `20260511_JP Morgan_1666c9de5c0a393daa6484be9f484839.pdf` | `20260511_JP Morgan_1666c9de5c0a393daa6484be9f484839.pdf` | `strong` | `header_or_title` | Pass |
| 4 | `SYNSAM SS`, `20260511`, `Nordea Equity Research` | `20260511_Nordea Equity Research_09830ec754626864bb0aa1f8c9f2f71f.pdf` | `20260511_Nordea Equity Research_09830ec754626864bb0aa1f8c9f2f71f.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 5 | `ARGX BB`, `20260511`, `Degroof Petercam` | `20260511_Degroof Petercam_011c59f3f95983c8565a1bd16be40fde.pdf` | `20260511_Degroof Petercam_011c59f3f95983c8565a1bd16be40fde.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 6 | `AZN LN`, `20260511`, `Deutsche Bank Research` | `20260511_Deutsche Bank Research_040af2ec1e0af3c2673f9579d7dd8203.pdf` | `20260511_Deutsche Bank Research_040af2ec1e0af3c2673f9579d7dd8203.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 7 | `ISP IM`, `20260511`, `Intermonte Securities` | `20260511_Intermonte Securities_89370c90d3676fad2c1ae665e4dcf57f.pdf` | `20260511_Intermonte Securities_89370c90d3676fad2c1ae665e4dcf57f.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 8 | `BAVA DC`, `20260511`, `Jefferies` | `20260511_Jefferies_0c66e347fc5b6d6b413d523f33f0f7c2.pdf` | `20260511_Jefferies_0c66e347fc5b6d6b413d523f33f0f7c2.pdf` | `high_explicit` | `explicit_ticker_field` | Pass |
| 9 | `ARGX BB`, `20260511`, `KBC Securities` | `20260511_KBC Securities_983612ba9e74731e074484836c14e498.pdf` | `20260511_KBC Securities_983612ba9e74731e074484836c14e498.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 10 | `BNOR NO`, `20260511`, `Stifel Nicolaus` | `20260511_Stifel Nicolaus_167783c6253b21dd0f9765cc96b64254.pdf` | `20260511_Stifel Nicolaus_167783c6253b21dd0f9765cc96b64254.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |
| 11 | `SHA0 GY`, `20260622`, `Kepler Cheuvreux` | `20260622_Kepler Cheuvreux_098dda895ab76d9a8e9b4c3a3408485a.pdf` | `20260622_Kepler Cheuvreux_098dda895ab76d9a8e9b4c3a3408485a.pdf` | `high_explicit` | `explicit_bloomberg_field` | Pass |

Result: **11/11 expected PDFs selected.**

## Safety outcomes

- Weak or tied matches return `ambiguous` and select no PDF.
- No filename or ticker evidence returns transparent `not_found` output.
- Any unreadable shortlisted candidate prevents a uniqueness claim and returns `ambiguous`.
- Serialized evidence contains only page, extracted line number, evidence class, score, and normalized ticker.
- No report PDF, extracted report passage, report screenshot, analyst contact, or absolute workstation path is part of the evaluation artifacts.

## Known limitations

- Only the first two pages are inspected.
- Matching is lexical and does not yet resolve company identity in multi-security reports.
- Header classification depends on extracted text order.
- Broker normalization can theoretically collapse punctuation-only name differences.
- `GY`/`GR` equivalence is specific to this supplied project fixture.
- Confidence thresholds are conservative policy choices validated on this small evaluation set, not statistically calibrated probabilities.
- Evidence extraction requires an embedded text layer and does not perform OCR.
- Reading order is PyMuPDF's deterministic sorted block order, not semantic table reconstruction.
- Text boxes extending beyond the page boundary are clipped; degenerate boxes are omitted.
- Stable IDs intentionally change if the PDF bytes or supported parser behavior changes.
- Nested table rows that require parent-label inheritance are unsupported.
- Wrapped metric labels and some broker abbreviations remain unresolved.
- Separate consensus tables are joined only on the same page when normalized metric, qualifiers, period, and unit match exactly and uniquely; cross-page, fuzzy, ambiguous, or definition-mismatched tables remain unsupported.
- Percentage-only matrices keep old/new values null and never back-solve an old value.
- Candidate detection can return `candidates_unresolved` for reports with revision-like language but no safely parsed row.
- The 0.25 percentage-point reconciliation tolerance intentionally surfaces discrepancies caused by coarse display rounding.

## Evidence-layer corpus validation

The actual `find-rpt evidence` locator path was run twice for each case below. Only safe metadata is recorded; no report text, coordinates, analyst details, screenshots, or evidence JSON was persisted. `Filename hash` is SHA-256 over the local filename, truncated to 16 hexadecimal characters; it is not a report-content hash.

| Broker/layout | Filename hash | Pages | Blocks | Page numbers | Boxes in bounds | Repeated IDs |
| --- | --- | ---: | ---: | --- | --- | --- |
| ABG Sundal Collier | `d209c20a7c723619` | 8 | 177 | Pass | Pass | Pass |
| BofA Global Research | `8ffa32a9668e1c31` | 11 | 187 | Pass | Pass | Pass |
| J.P. Morgan | `1089e822e49c16df` | 11 | 152 | Pass | Pass | Pass |
| Nordea Equity Research | `5dd058976c22d8ac` | 9 | 158 | Pass | Pass | Pass |
| Kepler Cheuvreux | `7233feedd9853ff6` | 11 | 281 | Pass | Pass | Pass |

Manual review confirmed that public page numbers follow the PDF's one-based sequence and block order follows a sensible header/body progression across the sampled layouts. Dense multi-column tables remain a known semantic-order limitation.

Source integrity review found no tracked PDF, no PDF modification produced by the commands, and no source write path in the implementation. The candidate diff contains no extracted proprietary passage, cached corpus text, absolute workstation path, or large generated artifact.
