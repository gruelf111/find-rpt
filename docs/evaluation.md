# Retrieval milestone evaluation

Evaluation date: 2026-07-16

## Scope

This evaluation covers only deterministic report retrieval from Bloomberg ticker, filename date, and filename broker. Summarization, claim citations, charts, and email drafting remain out of scope.

The evaluation dataset contains query metadata and expected local filenames only. This document contains no report text, extracted passages, analyst contact data, report screenshots, or PDF-derived artifacts.

## Automated verification

Command:

```text
PYTHONPATH=src python -m unittest discover -s tests -v
```

Result: **21 tests passed; 0 failed; 0 skipped.**

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
