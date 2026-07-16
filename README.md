# find-rpt

This repository implements deterministic retrieval, a PDF evidence layer, conservative estimate-revision extraction, and bounded rationale interpretation. Given a Bloomberg ticker, corpus date, and broker, it returns one safely matched local PDF, exposes page-scoped text blocks with exact coordinates, structures explicitly revised financial metrics with arithmetic checks, and can retrieve a small evidence set for model-assisted explanation.

It does not generate the final research brief, render citation highlights or charts, or draft/send email. The rationale milestone returns structured grounded data only.

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

The evidence tests also run extraction against five local broker/layout families when
`corpus/` is available. They validate one-based page numbering, bounded rectangles,
source-page text membership, deterministic block order/IDs, direct-path extraction,
and retrieval-to-evidence CLI integration. Corpus text and coordinates remain in
memory and are not written to test artifacts.

The revision tests cover arithmetic (including negative and zero old values), percentages versus percentage points and basis points, currency/scale/per-share units, fiscal/calendar periods, qualifiers, exact same-page consensus joins and spreads, unit mismatches, disclosure-only pages, unresolved table states, repeatability, CLI integration, evidence resolution, and 11 local reports across multiple brokers.

Rationale tests cover candidate retrieval under dense revision evidence, context signals, explicit management participants, valid and invented evidence IDs, cross-document revision rejection, clear/partial/unclear rationale, proximity-only false drivers, rating/valuation separation, role and jargon validation, malformed/extra-schema output, provider failures, missing configuration, loopback enforcement, fake-model determinism, CLI behavior, and repeatability. Fifteen local reports across thirteen broker/layout families are checked in retrieval-only mode, including results preview/review, rating change, roadshow, and management-meeting samples. The complete suite currently contains 60 tests.

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
