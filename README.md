# find-rpt

`find-rpt` is a local-first Codex skill and Python CLI that selects exactly one sell-side research PDF from a private corpus and renders a concise, evidence-backed brief. The query contract is:

```text
/find-rpt {Bloomberg ticker} {corpus date} {broker}
```

The package performs deterministic report selection, revision arithmetic, evidence geometry, citation validation, semantic-output validation, and escalation gating. Inside Codex, the active agent may interpret only a compact bounded evidence bundle; no model API key is required. The existing loopback OpenAI-compatible provider remains available for standalone use. The system can draft an analyst clarification email when material revisions remain unexplained, but it has no send path.

## Architecture

```text
/find-rpt request
  -> deterministic filename/date/broker shortlist
  -> deterministic ticker resolution (one report or stop)
  -> local PDF blocks, words, pages, and bounding boxes
  -> deterministic revisions, arithmetic, units, periods, and citations
  -> bounded evidence bundle
  -> active Codex agent interpretation OR optional loopback API interpretation
  -> Python grounding checks and unsupported-claim removal
  -> concise brief or review-only analyst draft
  -> loopback highlighted citation viewer
```

This separation matters: a model is useful for plain-English interpretation, but it must not choose files, perform authoritative arithmetic, invent missing values, or create source coordinates. If deterministic evidence cannot establish one report or support a claim, the system returns an explicit partial, not-found, ambiguous, or error result.

## Requirements

- Python 3.11 or newer;
- a local `corpus/` directory containing the supplied PDFs, or another configured local path;
- Codex for agent-hosted semantic output, or an optional OpenAI-compatible loopback endpoint for standalone complete output; and
- a browser for opening highlighted citations from the loopback viewer.

Runtime dependencies are constrained in `pyproject.toml`: `pypdf>=6,<7` and `PyMuPDF>=1.26,<2`. No database, cloud service, telemetry client, mail library, or web framework is required.

## Install from a clean checkout

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

POSIX shell:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The `dev` extra installs pytest for repository development and verification. Runtime-only installation uses `python -m pip install .`. Installation provides both `find-rpt` and `python -m find_rpt`.

## Corpus and configuration

Put source reports in `corpus/`. PDFs, local configuration, caches, rendered inspection images, and generated real-report output are ignored by Git. The project never modifies a source PDF.

Optional local TOML configuration:

```powershell
Copy-Item find-rpt.example.toml find-rpt.toml
```

Configuration precedence is launcher flags, environment variables, `[find_rpt]` in ignored `find-rpt.toml`, then defaults.

| Setting | Launcher option | Environment | TOML key | Default |
| --- | --- | --- | --- | --- |
| Corpus | `--corpus` | `FIND_RPT_CORPUS` | `corpus_path` | `corpus` |
| Citation cache | `--cache-dir` | `FIND_RPT_CACHE_DIR` | `cache_path` | `.cache/find-rpt/citations` |
| Model mode | `--model-mode` | `FIND_RPT_MODEL_MODE` | `model_mode` | `api` in the standalone launcher; the Codex skill uses `agent-hosted` stages |
| Model provider | `--model-provider` | `FIND_RPT_MODEL_PROVIDER` | `model_provider` | `local-openai-compatible` |
| Model name | `--model-name` | `FIND_RPT_MODEL_NAME` | `model_name` | `local-rationale-model` |
| Model URL | `--model-url` | `FIND_RPT_MODEL_URL` | `model_url` | `http://127.0.0.1:11434/v1/chat/completions` |
| API-key variable | `--model-api-key-env` | `FIND_RPT_MODEL_API_KEY_ENV` | `model_api_key_env` | `FIND_RPT_MODEL_API_KEY` |
| Viewer host | `--citation-viewer-host` | `FIND_RPT_CITATION_HOST` | `citation_viewer_host` | `127.0.0.1` |
| Viewer port | `--citation-viewer-port` | `FIND_RPT_CITATION_PORT` | `citation_viewer_port` | `8765` |
| No-model mode | `--no-model` | `FIND_RPT_NO_MODEL` | `no_model` | `false` |

`.env.example` documents equivalent variables, but the package does not auto-load `.env` files. `FIND_RPT_MODEL_MODE` accepts `agent-hosted`, `api`, or `none`. `agent-hosted` is the Codex-skill default and must use the prepare/finalize commands; a standalone one-shot `brief` cannot summon a Codex host. `api` retains the existing loopback OpenAI-compatible provider and is the standalone default only when `FIND_RPT_MODEL_API_KEY` is configured. `none` or `--no-model` produces transparent partial output. Model and citation hosts must resolve to loopback.

## Semantic modes

The Codex skill uses `FIND_RPT_MODEL_MODE=agent-hosted`: Python emits bounded evidence, the active Codex model returns strict rationale JSON, and Python reselects the report, validates the JSON, removes unsupported claims, builds citations, and renders the final brief. The Codex host is used only when the skill runs inside Codex.

For direct standalone CLI use, either configure API mode or request no-model output. Standalone execution without an API key or `--no-model` fails clearly; it does not silently treat the process as agent-hosted.

| Invocation/configuration | Exact behavior |
| --- | --- |
| Codex skill, model mode unset | Runs `agent prepare`/`agent finalize`; no API key or provider call is required. |
| `FIND_RPT_MODEL_MODE=agent-hosted` with the two-stage commands | Same agent-hosted behavior; the commands never invoke the API provider. |
| One-shot standalone command with `agent-hosted` | Fails with instructions to use the two-stage commands. |
| `FIND_RPT_MODEL_MODE=api` | Uses the retained loopback OpenAI-compatible provider. |
| API mode without `FIND_RPT_MODEL_API_KEY` | Fails explicitly; no fallback prose is produced. |
| `FIND_RPT_MODEL_MODE=none` or `--no-model` | Returns a transparent partial result without semantic interpretation. |
| Standalone mode unset, API key configured | Selects API mode. |
| Standalone mode and API key both unset | Fails explicitly and asks for API configuration or no-model mode. |

### Optional standalone API mode

Point the launcher at an OpenAI-compatible chat-completions endpoint running locally, then set its model name and key in the shell. The key may be a placeholder if the local server does not authenticate.

```powershell
$env:FIND_RPT_MODEL_URL = 'http://127.0.0.1:11434/v1/chat/completions'
$env:FIND_RPT_MODEL_NAME = 'local-rationale-model'
$env:FIND_RPT_MODEL_API_KEY = 'local-only-key'
$env:FIND_RPT_MODEL_MODE = 'api'
```

Report passages are never permitted to leave the machine. When no local model is available, use `--no-model`; the result is intentionally partial and does not fabricate a takeaway, rationale, context classification, or escalation decision.

## Citation viewer

Start the viewer in a separate terminal:

```powershell
find-rpt citations serve --corpus corpus --cache-dir .cache/find-rpt/citations --host 127.0.0.1 --port 8765
```

Brief citations link to this loopback server. Each citation validates the source size and SHA-256 digest, opens the correct one-based page, and overlays the stored evidence boxes. If the source changed, the citation fails stale instead of opening mismatched evidence.

## Enable the Codex skill

The canonical repository-local skill is `.agents/skills/find-rpt/SKILL.md`. Open this repository root in Codex so it discovers the skill, then invoke it exactly as `$find-rpt {ticker} {date} {broker}`. The Python package must be installed in the interpreter Codex invokes.

Optional personal installation copies the same repository-local package into the personal Codex skills directory:

PowerShell:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' }
$skillsDir = Join-Path $codexHome 'skills'
New-Item -ItemType Directory -Force $skillsDir | Out-Null
Copy-Item -Recurse .agents\skills\find-rpt (Join-Path $skillsDir 'find-rpt')
```

Direct deterministic no-model launcher check:

```powershell
python .agents/skills/find-rpt/scripts/find_rpt.py --command '/find-rpt SHA0 GY 2026-06-22 "Kepler Cheuvreux"' --no-model
```

Example Codex commands:

```text
$find-rpt SHA0 GY 2026-06-22 "Kepler Cheuvreux"
$find-rpt BP/ LN 22 Jun 2026 "J.P. Morgan"
```

The skill runs the two-stage agent-hosted flow and displays only the final Python renderer's Markdown. It never displays or rewrites the intermediate evidence bundle or semantic JSON.

## Optional Claude Code command

`.claude/commands/find-rpt.md` is a thin project command. Open Claude Code at the repository root and invoke `/find-rpt` with the same three arguments. If project commands are unavailable in the installed Claude Code version, use the shared Python launcher directly.

## CLI usage

Selection only:

```powershell
find-rpt "SHA0 GY" 20260622 "Kepler Cheuvreux"
find-rpt find "BP/ LN" 20260511 "JP Morgan" --format json
```

Complete brief:

```powershell
find-rpt brief --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux"
find-rpt brief --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --format json
find-rpt brief --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --format text
```

Use `--no-model` for transparent partial output, `--no-visualization` to suppress comparison bars, and `--escalate-partial` only when partial rationale should trigger on an unexplained material revision.

Agent-hosted stages used by Codex:

```powershell
find-rpt agent prepare "SHA0 GY" 2026-06-22 "Kepler Cheuvreux" --corpus corpus --format json
Get-Content semantic-output.json -Raw | find-rpt agent finalize "SHA0 GY" 2026-06-22 "Kepler Cheuvreux" --corpus corpus --input - --format agent-json
```

The prepare bundle contains the normalized request, a safe selected-report identifier, grouped validated revision identifiers, bounded non-duplicated rationale/context passages, stable block IDs, closed metric/period allowlists, deterministic analyst candidates without addresses, and warning codes. It contains no authoritative revision values, page numbers, citation URLs, bounding boxes, or unrelated report text. Finalize accepts the exact existing rationale schema through `--input` or stdin, removes unsupported fields and claims, and returns a warning-bearing partial brief if parsing or validation fails.

Diagnostic layers:

```powershell
find-rpt evidence --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --format json
find-rpt revisions --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --format json
find-rpt rationale --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --no-model --format json
find-rpt escalation --ticker "SHA0 GY" --date 2026-06-22 --broker "Kepler Cheuvreux" --format json
```

## Output and stop behavior

A complete brief is ordered as:

1. one-glance ticker, broker, query date, internal publication date when material, title, and takeaway;
2. estimate revisions and consensus comparisons;
3. why the estimates changed;
4. publication context and management interaction;
5. a compact estimate comparison when useful;
6. material first-read items; and
7. source, analyst, and warnings.

`not_found` selects nothing. `ambiguous` selects nothing and may return safe candidate metadata. Invalid or unreadable shortlisted PDFs block uniqueness. The skill never broadens the query or merges reports.

When validated material revisions remain unexplained, the renderer surfaces a draft addressed only to report-evidenced research analysts, uses `[TODO: address]` when needed, states that the draft has not been sent, and stops. There is no SMTP dependency, mail provider, mail-client launcher, `mailto:` action, clipboard integration, or send-capable API.

## Tests and verification

Full suite:

```powershell
python -m unittest discover -s tests -v
```

Focused integration and packaging checks:

```powershell
python -m unittest tests.test_corpus_evaluation tests.test_skill_packaging -v
python -m compileall -q src scripts tests .agents/skills/find-rpt
python -m pip check
python scripts/smoke_test.py
```

No separate lint or static type checker is configured; the release gate records those checks as not configured rather than passed. `python -m compileall` is the syntax check. See `docs/evaluation.md` for automated and manual results.

## Evaluation summary

The final local evaluation uses twelve real reports across twelve broker/layout families and all three corpus dates, plus a not-found control. Deterministic selection is measured separately from revision, rationale, context, citation, rendering, and escalation results. Real report semantics remain unmeasured when a loopback model is unavailable; synthetic adversarial tests cover the grounding validator and complete renderer without overstating real-model accuracy.

Current release evidence, limitations, and acceptance status are in:

- `docs/evaluation.md` - metrics and sample limitations;
- `SUBMISSION_CHECKLIST.md` - release gates;
- `REVIEWER_GUIDE.md` - fastest review path; and
- `DEVELOPMENT_LOG.md` plus `development-notes/` - AI-assisted development record.

## Privacy and data handling

- `candidate_brief.pdf`, `briefing.pdf`, and everything under `corpus/` are immutable local source material.
- Never commit, copy, upload, attach, publish, or redistribute a report, excerpt, report-derived image, or generated real-report brief.
- Evidence coordinates, citation cache, temporary renderings, local configuration, and real transcripts remain ignored and local.
- Agent-hosted mode uses the active Codex model only inside the skill; standalone API mode supports only a loopback endpoint. No external telemetry or upload path exists.
- Committed tests and examples are synthetic or contain only safe query identifiers and aggregate metrics.

## Known limitations

- Retrieval identity is bounded to the first two pages and remains lexical; multi-security documents can be ambiguous.
- There is no OCR fallback for image-only reports.
- Dense nested or wrapped tables can be unresolved or conservatively incomplete.
- Separate consensus tables join only with exact same-page metric, qualifier, period, and unit alignment.
- Analyst extraction favors precision and can miss compressed contacts; it never infers names or addresses.
- Complete real rationale, context, management, takeaway, and escalation accuracy require either the Codex agent-hosted skill or a configured local API model, plus manual review.
- Citation URLs require the matching loopback viewer, cache, and unchanged source PDF.

## Repository layout

```text
src/find_rpt/                 authoritative Python pipeline
.agents/skills/find-rpt/      repository-local Codex skill and thin launcher
.claude/commands/             optional Claude Code wrapper
tests/                        synthetic and safe real-corpus regression metadata
docs/                         requirements, discovery, decisions, evaluation
examples/                     submission-safe synthetic examples and templates
development-notes/            safe AI-development and transcript guidance
scripts/                      smoke test and structural redactor
```

## Troubleshooting

- `configuration_error`: check local paths, TOML types, and loopback hosts/ports.
- `model_unavailable`: for standalone use, select API mode and configure its loopback key, or explicitly use no-model mode. For Codex, use the skill's prepare/finalize workflow.
- `citation_viewer_unavailable`: start the viewer with the same corpus, cache, host, and port.
- stale citation: remove the ignored citation cache and rerun the brief.
- `not_found`: verify the filename date and broker, then the Bloomberg ticker; do not broaden manually.
- `ambiguous`: inspect corpus integrity or query metadata; do not select a candidate by hand.
- garbled terminal bars: use a UTF-8 terminal; numeric values remain alongside every visualization line.

## Cleanup

These commands remove disposable local state without touching `corpus/`:

```powershell
Remove-Item -Recurse -Force .cache\find-rpt -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force tmp -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force build,dist -ErrorAction SilentlyContinue
Get-ChildItem -Directory -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force
```

Remove `.venv/` separately only when you intend to rebuild the environment.
