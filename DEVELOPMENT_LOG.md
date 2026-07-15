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
