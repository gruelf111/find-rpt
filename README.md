# find-rpt

This repository implements deterministic retrieval plus a PDF evidence layer: given a Bloomberg ticker, corpus date, and broker, it returns one safely matched local PDF, then can expose page-scoped text blocks with exact coordinates.

It does not extract estimates, summarize reports, render citation highlights or charts, or draft/send email.

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

`tests/evaluation_cases.json` contains 11 manually verified query/filename pairs. It contains no PDF text or extracted report data.

The evidence tests also run extraction against five local broker/layout families when
`corpus/` is available. They validate one-based page numbering, bounded rectangles,
source-page text membership, deterministic block order/IDs, direct-path extraction,
and retrieval-to-evidence CLI integration. Corpus text and coordinates remain in
memory and are not written to test artifacts.

## Current limitations

- Only the first two pages are inspected. A ticker absent from both produces not found.
- Broker matching is normalized exact matching; it does not yet maintain a broker alias registry.
- Ticker resolution is deterministic lexical evidence scoring, not company/entity resolution.
- A multi-security or sector report can still contain a strongly labelled ticker for a non-primary security. This slice has no company-identity resolver, so such results require particular scrutiny.
- `GY`/`GR` aliasing is project-specific and could be inappropriate for a corpus where those suffixes intentionally distinguish listings.
- Evidence line numbers refer to extracted page text and are retrieval diagnostics, not final claim citations.
- The evidence layer requires a usable embedded text layer; it does not perform OCR.
- Reading order is PyMuPDF's deterministic sorted block order and may not recover every complex table's semantic order.
- Boxes extending outside a PDF page are clipped to the page boundary; degenerate boxes are omitted.
- Block IDs are stable for unchanged PDF bytes with the supported PyMuPDF extraction behavior. Replacing a PDF or changing parser behavior intentionally invalidates references.
