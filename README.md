# find-rpt

This repository currently implements the first retrieval slice only: given a Bloomberg ticker, corpus date, and broker, it returns one safely matched local PDF, a transparent not-found result, or an ambiguous result with ranked evidence.

It does not summarize reports, generate citations or charts, or draft/send email.

## Setup

Use Python 3.11 or newer in a local virtual environment:

```text
python -m venv .venv
python -m pip install -e .
```

Run the second command after activating the environment with the platform-appropriate activation command. The only runtime dependency is `pypdf`; it is necessary to inspect PDF text locally. Source PDFs remain local under `corpus/` and are never installed or committed.

## CLI

Human-readable output:

```powershell
find-rpt "SHA0 GY" 20260622 "Kepler Cheuvreux"
```

Structured JSON:

```powershell
find-rpt "BP/ LN" 20260511 "Broker Name" --format json
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

## Current limitations

- Only the first two pages are inspected. A ticker absent from both produces not found.
- Broker matching is normalized exact matching; it does not yet maintain a broker alias registry.
- Ticker resolution is deterministic lexical evidence scoring, not company/entity resolution.
- A multi-security or sector report can still contain a strongly labelled ticker for a non-primary security. This slice has no company-identity resolver, so such results require particular scrutiny.
- `GY`/`GR` aliasing is project-specific and could be inappropriate for a corpus where those suffixes intentionally distinguish listings.
- Evidence line numbers refer to extracted page text and are retrieval diagnostics, not final claim citations.
