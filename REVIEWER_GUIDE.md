# Reviewer guide

The fastest safe review takes about ten minutes. Run every command from the repository root. Real-report output must remain local and untracked.

## 1. Fresh install and safe configuration

PowerShell:

```powershell
python -m venv tmp\reviewer-venv
$python = (Resolve-Path .\tmp\reviewer-venv\Scripts\python.exe).Path
& $python -m pip install 'setuptools>=69' .
$env:FIND_RPT_CORPUS = (Resolve-Path corpus).Path
$env:FIND_RPT_NO_MODEL = 'true'
```

This is the fastest deterministic setup. The corpus defaults to `corpus/`; the explicit environment variable makes that choice visible. No-model mode produces a transparent partial brief and never fabricates rationale, context, or escalation. For a complete semantic brief, use the installed Codex skill's agent-hosted flow. Standalone CLI review must instead configure the loopback-only API settings in `README.md`; never use a remote endpoint.

## 2. Run the automated gates

```powershell
& $python -m unittest discover -s tests -v
& $python -m compileall -q src tests
& $python -m pip check
```

No separate lint or static-type command is configured. The test suite includes packaging, clean-target installation, no-send guards, citation validation, real-corpus retrieval manifests, and synthetic semantic behavior.

## 3. Start citations and exercise the packaged skill

In a second terminal at the repository root, resolve the same reviewer interpreter and start the viewer:

```powershell
$python = (Resolve-Path .\tmp\reviewer-venv\Scripts\python.exe).Path
& $python -m find_rpt citations serve --corpus corpus --cache-dir .cache/find-rpt/citations --host 127.0.0.1 --port 8765
```

Back in the first terminal, run the seven-check smoke test:

```powershell
& $python scripts/smoke_test.py
```

The canonical repository-local Codex skill is `.agents/skills/find-rpt/SKILL.md`. Open the repository root in Codex to discover it. Optional personal installation copies that same package:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' }
$skillsDir = Join-Path $codexHome 'skills'
New-Item -ItemType Directory -Force $skillsDir | Out-Null
Copy-Item -Recurse -Force .agents\skills\find-rpt (Join-Path $skillsDir 'find-rpt')
```

The package must also be installed in the Python interpreter that Codex invokes. The isolated `$python` environment below proves packaging and the direct launcher; if Codex uses another interpreter, install the local project into that interpreter before reloading the skill.

Invoke an authorized known corpus query:

```text
$find-rpt {ticker} {date} {broker}
```

Before using the Codex UI, the same packaged launcher can be checked directly:

```powershell
& $python .agents/skills/find-rpt/scripts/find_rpt.py --command '/find-rpt SHA0 GY 2026-06-22 "Kepler Cheuvreux"' --no-model
& $python .agents/skills/find-rpt/scripts/find_rpt.py --command '/find-rpt ZZZZ LN 2026-05-11 "BofA Global Research"' --no-model
```

The first command should select one report and return a transparent partial brief. The second should return `not_found`. These commands also exercise a broker containing spaces. Punctuation and alternative-date parsing are covered by the automated package tests and can be checked with `BP/ LN` and `22 Jun 2026` when an authorized matching query is available. Every output state must retain `sent: false`.

## 4. Verify one citation locally

With the viewer running, open one inline citation from the successful local command. Confirm that it opens the selected report, lands on the stated page, and highlights the precise supporting passage. Do not save or attach the rendered page. `& $python scripts/smoke_test.py` provides the viewer health check; the citation tests verify resolution, stale handling, traversal rejection, and page rendering.

## 5. Complete the semantic acceptance gate

First run the synthetic agent-hosted boundary suite:

```powershell
& $python -m unittest tests.test_agent_hosted -v
```

It covers valid agent JSON, invented block IDs, unsupported numbers, unsupported names, malformed JSON, partial and unclear rationale, final rendering, and the absence of an external model call. To inspect the boundary manually without exposing report output, run `find-rpt agent prepare ... --format json`, create strict semantic JSON from only that bundle, and pipe it to `find-rpt agent finalize ... --input - --format agent-json`. Confirm that prepare contains no page numbers, citation URLs, bounding boxes, or unrelated report text, and that only finalizer-produced Markdown is displayed.

For the literal no-key Codex path, unset `FIND_RPT_MODEL_API_KEY`, invoke `/find-rpt {ticker} {date} {broker}`, and confirm the skill runs the two commands above. English dates such as `11 May 2026`, punctuation-bearing tickers, and brokers containing spaces are supported. A complete result must have `citation_viewer_available: true` when the matching viewer is running; otherwise it must be `partial` with `citation_viewer_unavailable`.

The synthetic review-only escalation path is reproducible without report content:

```powershell
& $python -m unittest tests.test_skill_packaging.LauncherIntegrationTests.test_partial_no_revisions_and_unclear_escalation_are_preserved -v
& $python -m unittest tests.test_escalation.RenderingAndSafetyTests.test_brief_surfaces_draft_last_and_stops -v
```

For real semantic acceptance, run the skill inside Codex (agent-hosted, no API key) or configure standalone `FIND_RPT_MODEL_MODE=api` with a loopback-only rationale model, then manually inspect at least three complete real briefs. Check every causal statement and context label against its inline evidence; reject unsupported claims. Include an honestly identified partial or unclear report if one exists. If none exists, record that corpus limitation and rely on the synthetic escalation suite rather than relabelling a clear report. Standalone use without API mode must pass `--no-model` or set `FIND_RPT_MODEL_MODE=none`.

## 6. Privacy and release checks

Before committing or packaging, confirm:

```powershell
git status --short
git ls-files -- '*.pdf'
git diff --check
```

Also inspect the diff for real analyst contacts, report passages, screenshots, absolute workstation paths, caches, credentials, and generated real outputs. Do not publish until the unchecked items in `SUBMISSION_CHECKLIST.md` have been resolved or explicitly accepted as limitations.

The evaluation is in `docs/evaluation.md`, design decisions are in `docs/decisions.md`, and the development record is in `DEVELOPMENT_LOG.md` plus `development-notes/`. When finished, remove `tmp/reviewer-venv` and any disposable local render directory without touching `corpus/`.
