# Development log

## 2026-07-16

- Used AI assistance to translate the discovery findings and assignment constraints into a bounded deterministic retrieval design.
- Chose a compact Python package with `pypdf`, standard-library CLI/JSON support, and `unittest`; no service, database, model call, or external API was introduced.
- Defined fixed ticker-evidence weights and confidence margins so header/title evidence dominates incidental body mentions and tied/weak cases cannot be selected silently.
- Added punctuation/spacing normalization for Bloomberg inputs and a `GY`/`GR` alias based on the discrepancy already documented in discovery.
- Added synthetic unit tests and a manually verified filename-only local evaluation set. No report passages, page images, or PDF-derived fixtures were added to the repository.
- The first corpus evaluation exposed a split table-header/value layout. Updated deterministic classification to recognize Bloomberg/ticker labels on either of the two preceding extracted lines and added a regression test without lowering the safety threshold.
- Kept summarization, claim citation generation, charting, and email drafting/sending out of this vertical slice.
- Initial slice verification passed 12 tests, including all 11 manually verified corpus cases. A real not-found CLI run inspected only the first two pages of the seven filename-shortlisted reports and returned a transparent JSON result.
- Performed a skeptical senior-engineer self-review. Material findings included unsafe selection around unreadable candidates, report-line leakage in evidence output, over-permissive date/ticker parsing, broad field/header heuristics, Windows-formatted result paths, and missing ignore rules for the actual local brief filename and Python build artifacts.
- Hardened selection, privacy, normalization, path serialization, symlink handling, and error sanitization without adding dependencies or expanding beyond retrieval.
- Removed raw evidence snippets and the initially considered line hash from serialized output; retrieval evidence now contains locator/classification metadata only.
- Added real synthetic invalid-payload and encrypted-PDF tests so parser failure handling is verified rather than assumed.
- Post-review verification passed all 21 tests, including the 11-case local corpus evaluation and the new adversarial error, privacy, portability, and false-positive tests.
- Retrieval milestone acceptance run: reran the complete suite with 21/21 passing and 11/11 manually verified corpus queries selecting the expected local filename.
- Audited commit candidates for PDFs, PDF payloads, recipient watermarks, analyst contact data, extracted report passages, absolute workstation paths, and serialized raw evidence. No report PDF or proprietary extracted text is included in the milestone artifacts.
- Added `docs/evaluation.md` with filename-only results, safety behavior, and known limitations. No later milestone work was started.
- Inspected the retrieval implementation before starting the next slice and kept deterministic report selection unchanged.
- Added a PyMuPDF evidence adapter for only the uniquely selected report. It preserves page boundaries and emits stable block identifiers, exact extracted text, bounding boxes, page dimensions, and source block numbers as structured JSON without writing derivative artifacts.
- Prototyped exact-reference resolution and tamper checks, then replaced that flat-block prototype with the requested nested page/block/word schema before the milestone review.
- Added synthetic page-boundary, ID-stability, JSON, malformed-input, and page-range tests plus runtime-only corpus tests. No report passages or coordinates were added to repository artifacts.
- Kept estimate extraction, claim selection, highlighting/viewer generation, and LLM summarization out of this slice.
- Installed the declared PyMuPDF dependency locally and ran the full suite: 25 tests passed, 0 failed, 0 skipped. Verified every generated evidence block resolved back to its original page in all four tested broker reports.
- Expanded the evidence slice to the requested nested document/page/block/word schema and added content-derived document IDs, one-based page-range filtering, a dedicated `find-rpt evidence` subcommand, direct local-path extraction, and explicit unreadable/encrypted/textless/page-range errors. The legacy positional retrieval command remains compatible.
- Real-layout validation now covers five brokers/layouts: ABG, BofA, J.P. Morgan, Nordea, and Kepler. No report text, coordinates, screenshots, or derived page artifacts were persisted.
- The first five-layout run exposed a Nordea text box slightly beyond the page boundary. Added deterministic page clipping and degenerate-box omission, then reran the evidence tests successfully (6/6).
- Manual verification included parsing evidence JSON from the direct-path CLI, checking one-based page filtering, confirming absolute paths are absent from serialized output, and comparing every returned real-report block against text extracted from its own source page in memory.
- Final verification passed the complete suite: 28 tests, 0 failures, 0 skips. This includes an in-memory locator CLI run that selected the Kepler report and extracted only page 1, without writing evidence output to disk.
- Pre-commit review reran all 28 tests successfully and exercised the actual locator-based evidence CLI twice across ABG, BofA, J.P. Morgan, Nordea, and Kepler. All 50 pages had correct one-based sequences on both runs, every emitted block rectangle remained within its page, and repeated block ID lists were identical.
- Manually checked block ordering against PyMuPDF's sorted extraction sequence and spot-checked header/body progression across the five layouts. Dense multi-column table semantics remain explicitly out of scope.
- Audited tracked and untracked candidate changes for PDFs, source writes, proprietary passages, cached text, absolute paths, large files, unnecessary dependencies, and broker-specific branches. No material implementation issue was found; corrected stale documentation describing the superseded flat-block resolver prototype.
