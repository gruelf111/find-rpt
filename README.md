# find-rpt

This repository implements deterministic retrieval, a PDF evidence layer, conservative estimate-revision extraction, bounded rationale interpretation, precise local citations, and a concise research-brief renderer. Given a Bloomberg ticker, corpus date, and broker, it selects one local PDF, validates estimate revisions, grounds the explanation, builds highlighted loopback citations, and renders Markdown, JSON, or terminal text with an optional compact estimate comparison.

It does not draft or send email and is not packaged as the final agent skill yet.

## Setup

Use Python 3.11 or newer in a local virtual environment:

```text
python -m venv .venv
python -m pip install -e .
```

Run the second command after activating the environment with the platform-appropriate activation command. Runtime dependencies are `pypdf` for bounded retrieval and PyMuPDF for layout-aware evidence. Source PDFs remain local under `corpus/` and are never installed or committed.

## CLI

Human-readable output:

```powershell
find-rpt "SHA0 GY" 20260622 "Kepler Cheuvreux"
```

Structured JSON:

```powershell
find-rpt "BP/ LN" 20260511 "Broker Name" --format json
```

Evidence JSON for the uniquely selected report:

```powershell
find-rpt evidence --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --format json
```

Direct local extraction, with an optional one-based page range:

```powershell
find-rpt evidence --pdf-path "corpus/example.pdf" --pages "1-3,5" --format json
```

Estimate-revision JSON after deterministic report selection:

```powershell
find-rpt revisions --ticker "SAP GY" --date "2026-06-22" --broker "Kepler Cheuvreux" --format json
```

Direct extraction from exactly one local PDF:

```powershell
find-rpt revisions --pdf-path "corpus/example.pdf" --format json
```

Bounded rationale extraction after deterministic report selection:

```powershell
find-rpt rationale --ticker "SAP GY" --date "2026-06-22" --broker "Kepler Cheuvreux" --format json
```

Direct local extraction, or passage retrieval without a model:

```powershell
find-rpt rationale --pdf-path "corpus/example.pdf" --format json
find-rpt rationale --pdf-path "corpus/example.pdf" --no-model --format json
```

Render the complete research brief:

```powershell
find-rpt brief --ticker "SAP GY" --date "2026-06-22" --broker "Kepler Cheuvreux"
find-rpt brief --ticker "SAP GY" --date "2026-06-22" --broker "Kepler Cheuvreux" --format json
find-rpt brief --ticker "SAP GY" --date "2026-06-22" --broker "Kepler Cheuvreux" --format text
```

Use `--no-visualization` to suppress comparison bars. Use `--no-model` to exercise the entire local deterministic pipeline and render a transparent partial brief when no local rationale model is configured. A normal brief command without `--no-model` fails clearly if model configuration is missing; it never fills rationale gaps from general knowledge.

### Brief output

The default Markdown order is one-glance header, title and takeaway, revisions, rationale/context, estimate picture, first-read items, source/analyst information, then material warnings. When a unique top-of-page internal publication date differs from the corpus/query date, the header shows both with evidence. Empty optional sections are omitted. The concise view shows at most eight cited revision rows, two comparison panels, and four first-read items. It prioritizes rows with consensus and complete old/new values and then sorts revenue, EBITDA, EBIT, margins, EPS, modelling items, target price, and other metrics. An omission count is explicit; no missing value is inferred. `—` means unavailable.

Synthetic example:

```text
ABC LN — Example Broker — 22 Jun 2026

Synthetic Company: Pricing improves [source]
Pricing supports the earnings outlook. [source]

What changed
Metric          Period    Old             New             Revision  Consensus
Revenue         FY2026E   100 EURm        110 EURm        +10%      105 EURm
Adjusted EPS    FY2027E   1.20 EUR/share  1.30 EUR/share  +8.3%     1.10 EUR/share

Estimate picture
EPS FY2027E (EUR/share)
Old                  │█████████   1.2
New                  │██████████  1.3
Consensus            │████████    1.1
```

The actual Markdown uses a compact table and inline local links. Relative percentage changes and percentage-point margin moves are different fields; a 10% to 12% margin change renders as `+2pp`, not `+20%`. Negative observations use a zero-axis bar, and charts are omitted for a single value, equal values, non-finite values, or missing units. The text renderer is the plain-terminal fallback, preserves each citation URL in angle brackets, and uses the same Unicode block/axis representation supported by Codex and Claude Code terminals.

Warnings are emitted only when they affect interpretation or completeness: unresolved/no revisions, unavailable rationale or takeaway, missing report title/analyst, failed or invalid citations, omitted uncited facts/rows, row caps, and material arithmetic conflicts. A report with no revisions remains a valid partial brief. Individual citation failures omit the affected facts and produce a transparent warning; a total citation-construction error, ambiguous or failed retrieval, unusable PDF, or model failure stops before a misleading complete brief is rendered. The `brief` command always extracts the complete selected PDF and deliberately has no `--pages` option.

Build precise citations from deterministic revision evidence:

```powershell
find-rpt citations build --ticker "SAP GY" --date "2026-06-22" --broker "Kepler Cheuvreux" --format json
find-rpt citations build --pdf-path "corpus/example.pdf" --format json
```

The direct path must resolve under the configured `--corpus` directory. Add
`--with-rationale` only when a loopback model is configured and citations for the
validated rationale claims are also required.

Start the local highlighted viewer:

```powershell
find-rpt citations serve
```

The server binds to `127.0.0.1:8765` by default. Stop it with `Ctrl+C`. Validate a
cached citation without opening a browser:

```powershell
find-rpt citations validate --citation-id "cit-0123456789abcdef01234567"
```

Use matching `--host`, `--port`, `--corpus`, and `--cache-dir` options when the
builder and viewer use non-default local settings. `--base-url` on `citations build`
controls the portable local URLs placed in JSON. It must be a complete loopback
HTTP origin with an explicit port; remote hosts, credentials, paths, queries, and
fragments are rejected.

## Local citation viewer

A citation URL has the form:

```text
http://127.0.0.1:8765/citation/<citation-id>#evidence-target
```

Activating it resolves the citation ID through the local ignored index, verifies
the source size and SHA-256 digest, opens the correct one-based page, lands at the
evidence area, and overlays translucent highlights. The page label identifies the
claim/evidence role. An `open original PDF` link serves the same indexed source
through an opaque document ID and preserves the page fragment.

The viewer uses PyMuPDF to render the cited page in memory and an inline SVG for
the highlight boxes. It requires no PDF.js download, remote font, analytics, CDN,
or other external asset. It does not create an annotated PDF or modify the source.
Word boxes are merged into compact line fragments. For structured revision tables,
the validated metric and fiscal period narrow the highlight to the relevant row,
period cells, and necessary headers. Evidence spanning pages becomes separate
citations.

Generated metadata is stored at `.cache/find-rpt/citations/index.json` by default.
It contains document fingerprints, portable corpus-relative filenames, pages,
block IDs, boxes, labels, and local URLs, but no report passage or absolute path.
The whole cache is disposable:

```powershell
Remove-Item -Recurse -Force .cache/find-rpt/citations
```

On POSIX systems use `rm -rf .cache/find-rpt/citations`. Rebuild citations after
cleanup.

### Privacy and security model

- The server accepts loopback hosts only and defaults to `127.0.0.1`; `0.0.0.0`
  and non-loopback addresses are rejected.
- URL paths contain validated citation/document IDs, never report paths. Unknown
  IDs, traversal attempts, and unindexed files are not served.
- Only regular, non-symlink PDF files beneath the configured corpus root resolve.
- The original-PDF route serves the source filename from the fingerprint-validated
  citation record, not duplicated document-index path metadata.
- Every request rechecks the source size and SHA-256 digest. A changed source
  returns a clear stale-citation error instead of showing potentially wrong evidence.
- PDF, image, HTML, and error responses use private `no-store` headers. The server
  suppresses request logging and never logs extracted report text.
- Shutting down the viewer closes the server only; source PDFs remain untouched.

### Citation troubleshooting and fallback behavior

- `source PDF changed after citation build`: rebuild evidence and citations from
  the current source. Do not reuse the stale ID.
- `citation ID is not indexed`: use the same cache directory for build, validate,
  and serve, or rebuild the citation.
- A 404 from a document URL means the document is not indexed/cited or its safe
  corpus-relative path no longer resolves.
- A viewer URL using a custom port must be built with the corresponding
  `--base-url`, although the citation ID itself remains valid on another loopback
  viewer instance.
- Image-only PDFs remain unsupported because evidence extraction has no OCR. The
  viewer intentionally has no annotated-derivative fallback: if safe in-memory page
  rendering fails, it returns an error and leaves the original untouched. The
  original-PDF link is a navigation aid, not a substitute for a highlighted citation.

`--no-model` returns the selected candidate passages, deterministic context signals, revision status, and exact model-input block/character counts. It marks semantic interpretation as skipped. Without `--no-model`, missing model configuration fails clearly.

## Rationale model configuration

The model boundary is the `RationaleModel` protocol. Tests use `DeterministicFakeRationaleModel`. The configured runtime provider speaks the OpenAI-compatible chat-completions shape but deliberately accepts only `localhost` or another loopback address, so proprietary passages cannot be sent to an external service.

Configuration is environment-only:

```powershell
$env:FIND_RPT_MODEL_API_KEY="local-endpoint-key"
$env:FIND_RPT_MODEL_URL="http://127.0.0.1:11434/v1/chat/completions"
$env:FIND_RPT_MODEL_NAME="local-rationale-model"
```

The URL and model name have the displayed defaults; the API key has no default. No `.env` file is loaded. The provider sends only the bounded candidate passages, a grouped revision summary, deterministic context hints, and allowed enum values. It never sends a PDF or unrelated report.

The structured result includes rationale clarity; grounded drivers with metrics, periods, categories, evidence block IDs, causal-link type, and confidence; why-now; report context; management contact and named participants; one-line takeaway; jargon definitions; important first-read items; and warnings. Python rejects mismatched report/revision data, unknown block IDs, claims outside the bounded passages, unsupported metrics or fiscal periods, unsupported numbers, extra schema fields, and malformed types. A driver survives only when its cited sentence contains either direct causal language or explicit hedged causal language; proximity alone is removed. Rating or valuation evidence cannot become an earnings driver, and a `valuation only` driver must link to target price. Model/provider failures return an explicit warning and no invented fallback text.

The brief renderer consumes only validated structured metadata, revision, rationale, and citation models. It does not parse PDFs, call a model, calculate authoritative revision values, or create evidence coordinates. A separate conservative front-matter adapter supplies a cited title and only retains analysts whose printed name and email appear together in report evidence; it never derives a name from an address.

Confidence is deterministic, not model-calibrated. A driver is `high` only when it has direct causal support plus a supported metric and period; `medium` means direct support is incomplete or the causal link is explicitly hedged/inferred; `low` means only minimal structured linkage remains. Other grounded claims are `high` for strong single-block lexical support, `medium` for sufficient multi-block or partial lexical support, and otherwise removed or `low`.

`revisions` returns `revisions_found`, `no_revisions`, or `candidates_unresolved`. The last status means revision signals were present but no safe row could be structured. A successful response includes candidate pages and block IDs plus revision rows with metric, qualifiers, period and period basis, old/new values, normalized unit, stated and calculated percentage changes, separately represented percentage-point changes, consensus and derived spreads when explicitly supported, direction, extraction method, confidence, warnings, and page/block evidence references. Missing values are JSON `null`.

The deterministic parsers currently cover prose `from/to` statements, old/new/consensus columns, grouped multi-year new/old/change tables, percentage-only revision matrices, compact `Change in` headers, and tightly bounded same-page consensus joins. A consensus observation is joined only when page, metric, qualifiers, period, and unit match exactly and the match is unique. The parsers never infer an old value from a percentage. Relative changes use `abs(old)` as the denominator; zero denominators remain unresolved. Stated and calculated changes reconcile within a documented 0.25 percentage-point tolerance.

The evidence response preserves `pages -> blocks -> words`. It includes a SHA-256 document ID, source filename, total page count, one-based page numbers, dimensions in PDF points, reading-order text blocks, stable block IDs, bounded block coordinates, and word coordinates with PyMuPDF line/word numbers. PyMuPDF uses zero-based page indexes internally; the Python API and all JSON use one-based page numbers. For locator extraction, the response also includes the deterministic retrieval result. Evidence is emitted to stdout only; no index, cache, page image, or derivative PDF is written.

Python API:

```python
from find_rpt import PdfEvidenceExtractor

document = PdfEvidenceExtractor().extract("corpus/example.pdf", pages="1-3")
```

Without installing the package, set `PYTHONPATH` and use the module directly. PowerShell:

```powershell
$env:PYTHONPATH="src"
python -m find_rpt "SHA0 GY" 20260622 "Kepler Cheuvreux" --format json
```

POSIX shells:

```sh
PYTHONPATH=src python -m find_rpt "SHA0 GY" 20260622 "Kepler Cheuvreux" --format json
```

Exit codes are `0` for found, `2` for not found, `3` for ambiguous, and `1` for invalid input.

## Retrieval behavior

1. Parse filename metadata and shortlist exact date plus punctuation/case-normalized broker.
2. Inspect page 1 of each shortlisted file.
3. Prefer an explicit Bloomberg field, then an explicit ticker field, then title/header evidence, then body evidence.
4. Return immediately when one candidate has a strong, safe lead.
5. Otherwise inspect page 2 as a bounded fallback.
6. Return ambiguous for weak, tied, or near-tied matches rather than guessing.
7. Return ambiguous if any shortlisted candidate cannot be inspected, because uniqueness cannot then be proved.

Ticker punctuation and whitespace are normalized, so `BP/ LN` and `BP LN` are equivalent. The German Bloomberg suffixes `GY` and `GR` are treated as aliases because the supplied assignment example and report use different forms for the same fixture.

Scores are fixed ranking heuristics, not probabilities or statistically calibrated confidence. Results expose a categorical confidence label, inspected pages, evidence kind, extracted line number, matched normalized ticker, and sanitized per-file errors. They do not emit the report line, surrounding report text, or a report-derived text fingerprint. Candidate paths use portable forward-slash form and do not expose an absolute local path.

## Tests

Run unit tests plus the local filename-only corpus evaluation:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

On POSIX shells, use `PYTHONPATH=src python -m unittest discover -s tests -v`.

`tests/evaluation_cases.json` contains 11 manually verified query/filename pairs. `tests/revision_evaluation_cases.json` contains only safe filename/broker metadata and expected extraction status/counts for 11 real reports. Neither file contains PDF text, financial values, coordinates, or screenshots.

The evidence and citation tests also run extraction against local broker/layout families when
`corpus/` is available. They validate one-based page numbering, bounded rectangles,
source-page text membership, deterministic block order/IDs, direct-path extraction,
retrieval-to-evidence CLI integration, citation resolution, and correct page targeting.
Corpus text and coordinates remain in memory and are not written to test artifacts.

### Brief troubleshooting

- `FIND_RPT_MODEL_API_KEY is not configured`: configure the loopback model above or add `--no-model` for a clearly labelled partial brief.
- `rationale not available` or `semantic interpretation skipped`: the revision table and citations are still validated, but the explanation/takeaway is intentionally absent.
- `report title not identified` or `analyst not identified`: the conservative front-matter rules did not find safe evidence. No contact detail is inferred.
- `citation requests failed` or `uncited revision rows omitted`: affected facts are not rendered. Rebuild against the same source/evidence and inspect the citation error.
- No estimate picture: fewer than two distinct finite observations with one validated unit were available, or `--no-visualization` was used.
- Citation links do not open: start `find-rpt citations serve` with the same corpus/cache/host/port used by the brief. The local viewer is required for highlighted passage links.

The revision tests cover arithmetic (including negative and zero old values), percentages versus percentage points and basis points, currency/scale/per-share units, fiscal/calendar periods, qualifiers, exact same-page consensus joins and spreads, unit mismatches, disclosure-only pages, unresolved table states, repeatability, CLI integration, evidence resolution, and 11 local reports across multiple brokers.

Rationale tests cover candidate retrieval under dense revision evidence, context signals, explicit management participants, valid and invented evidence IDs, cross-document revision rejection, clear/partial/unclear rationale, proximity-only false drivers, rating/valuation separation, role and jargon validation, malformed/extra-schema output, provider failures, missing configuration, loopback enforcement, fake-model determinism, CLI behavior, and repeatability. Citation tests cover stable IDs, evidence/page resolution, geometry, multi-line and multi-block passages, multi-page splitting, stale sources, invalid IDs, traversal, unindexed access, loopback binding, cache privacy, period-specific table highlights, CLI integration, and viewer routes. Renderer tests additionally enforce citation gating, cross-document metadata rejection, full-document brief extraction, and URL-preserving text output. Fifteen local reports across thirteen broker/layout families are checked in rationale retrieval-only mode. The complete suite currently contains 102 tests.

## Current limitations

- Only the first two pages are inspected. A ticker absent from both produces not found.
- Broker matching is normalized exact matching; it does not yet maintain a broker alias registry.
- Ticker resolution is deterministic lexical evidence scoring, not company/entity resolution.
- A multi-security or sector report can still contain a strongly labelled ticker for a non-primary security. This slice has no company-identity resolver, so such results require particular scrutiny.
- `GY`/`GR` aliasing is project-specific and could be inappropriate for a corpus where those suffixes intentionally distinguish listings.
- Evidence line numbers refer to extracted page text and are retrieval diagnostics, not final claim citations.
- The evidence layer requires a usable embedded text layer; it does not perform OCR.
- Reading order is PyMuPDF's deterministic sorted block order and may not recover every complex table's semantic order.
- Revision extraction is deliberately partial. Nested row labels, vertically split labels, and tables that require carrying a parent metric into unlabeled subrows remain unresolved.
- A percentage-only matrix supplies a stated revision but no old/new values; the extractor keeps both values `null` rather than back-solving them.
- Consensus values are joined across separate tables only on the same page with a unique exact match on metric, qualifiers, fiscal period, and unit. Cross-page, fuzzy-label, qualifier-mismatched, or unit-mismatched consensus evidence remains unlinked.
- Unprefixed years such as `2027E` retain `period_basis: "unspecified"`; the extractor does not silently relabel them as fiscal or calendar years.
- Display-rounded old/new values can legitimately disagree with a source-stated percentage. These rows are retained with a reconciliation warning.
- Boxes extending outside a PDF page are clipped to the page boundary; degenerate boxes are omitted.
- Block IDs are stable for unchanged PDF bytes with the supported PyMuPDF extraction behavior. Replacing a PDF or changing parser behavior intentionally invalidates references.
- Candidate passage selection is capped at 24 blocks and 12,000 extracted characters. A single oversized first block may be truncated in the model payload while retaining its source block ID.
- Deterministic context signals are retrieval hints, not final classifications; the validated model output still needs direct supporting evidence.
- The lexical validator is intentionally conservative and can remove a well-supported paraphrase when it shares too little terminology with the cited passage.
- Inferred drivers require explicit hedging and causal wording in one cited sentence; genuinely implicit broker reasoning can therefore be omitted and marked unclear.
- Jargon definitions are retained only for a small deterministic glossary or when the report explicitly defines the term. Unsupported house-specific expansions are removed.
- Real-report semantic accuracy requires a configured local model and manual claim review. The checked-in evaluation records bounded retrieval results but does not claim model accuracy without such a run.
- Citation page rendering is rasterized at 1.5x for a dependency-free local viewer; it is not a replacement for the PDF's native search, selectable text, forms, or accessibility tree.
- Revision-table line narrowing is deterministic and conservative. It can retain another period stated in the same compact source line, and it falls back to the validated block geometry when no safe row/period selector resolves.
- The citation cache is not a background catalog. URLs work only while a viewer using the matching corpus and cache is running.
