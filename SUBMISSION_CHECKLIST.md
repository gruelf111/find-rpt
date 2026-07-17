# Submission checklist

Status vocabulary: **Complete**, **Incomplete**, **Not applicable**, or **Manual action remaining**. This checklist separates repository readiness from uncompleted real-model acceptance.

## Repository and package

| Item | Status | Evidence or remaining action |
| --- | --- | --- |
| `/find-rpt {ticker} {date} {broker}` is packaged as a thin Codex skill | Complete | `.agents/skills/find-rpt/`; official skill validator passed. |
| Python remains the authoritative pipeline | Complete | The launcher calls `python -m find_rpt brief --format agent-json`; extraction logic is not duplicated. |
| README covers installation, configuration, usage, limitations, tests, privacy, and cleanup | Complete | `README.md`. |
| Safe complete, escalation, and not-found examples are included | Complete | `examples/`. |
| AI-assisted development record is prepared | Complete | `DEVELOPMENT_LOG.md` and `development-notes/AI_ASSISTED_DEVELOPMENT.md`. |
| Raw Codex transcript export | Manual action remaining | Export only if the submission channel requires it; follow `development-notes/TRANSCRIPT_EXPORT.md` and perform human redaction. |
| Optional public repository publication | Not applicable | Not requested or authorized during review. |

## Acceptance and safety

| Item | Status | Evidence or remaining action |
| --- | --- | --- |
| Correct report selected for the 12-case manual evaluation sample | Complete | 12/12 expected selections; see `docs/evaluation.md`. |
| Unsupported causal claims remaining after exercised validation | Complete | Zero in synthetic adversarial validation; real no-model briefs emitted no causal prose. Real-model accuracy is separately incomplete. |
| Material rendered claims are cited or explicitly unavailable | Complete | Invalid citations suppress claims; no-model semantics are explicitly unavailable. |
| Deterministic revision arithmetic and tests | Complete | Positive, negative, zero, unit, percentage-point, and reconciliation tests pass. |
| Citation opens correct report, page, and highlighted passage | Complete | 11/11 manually opened citations passed; automated viewer tests pass. |
| Ambiguous and not-found selection fails transparently | Complete | Unit, integration, launcher, and real not-found control pass. |
| Unclear rationale produces a review-only draft | Complete | Synthetic package and escalation tests pass; one manually labelled partial case was exercised in memory. |
| No automatic email-send mechanism | Complete | Frozen `sent: false`, source/dependency guard, smoke scan, and repository scan pass. |
| No PDF or proprietary report artifact is tracked | Complete | Git and full-history scans find no PDF; report-derived output remains ignored/local. |
| No real analyst contact, secret, credential, or local absolute path is tracked | Complete | Current-tree and history scans pass; documented API-key names/placeholders are not credentials. |
| Source PDFs unchanged during final verification | Complete | Identical 174-file byte/size/name manifest before and after the final run. |
| No accidental generated submission artifact | Complete | No unignored cache, render, database, or generated real output is present. Intentional local `.venv`, `.cache`, and corpus data remain ignored. |

## Engineering verification

| Item | Status | Evidence or remaining action |
| --- | --- | --- |
| Full unit/integration/packaging suite | Complete | 148/148 tests passed in the fresh reviewer environment. |
| Python compilation and dependency consistency | Complete | `compileall` and `pip check` pass. |
| Linting | Not applicable | No lint command is configured. |
| Static type checking | Not applicable | No static-type command is configured. |
| Smoke test | Complete | All seven checks pass in explicit no-model mode. |
| Fresh-environment install | Complete | Local package and declared dependencies install and invoke successfully. |
| Packaged skill and optional Claude wrapper | Complete | Package tests, official skill validation, direct launcher checks, and wrapper inspection pass. |
| Real successful complete semantic brief | Incomplete | Configure a loopback rationale model and manually approve at least three complete real briefs. |
| Real unclear-rationale packaged invocation | Manual action remaining | Run only if the corpus supplies a genuine unclear/partial case; do not relabel a clear report. Synthetic behavior is complete. |

## Release control

| Item | Status | Evidence or remaining action |
| --- | --- | --- |
| Final working-tree diff reviewed | Complete | Code, tests, documentation, examples, and untracked additions reviewed against `HEAD`. |
| Local release commit and annotated tag | Complete | Explicitly authorized for the scoped submission; created as the final local release operation. |
| Push, upload, publication, or remote repository | Manual action remaining | Not authorized or performed. |

## Current verdict

The repository is ready for the authorized local release commit with the release claim explicitly limited to the verified deterministic/no-model pipeline and synthetic semantic validation. It is **not evidence of complete real-report semantic performance** until the incomplete real-model item is completed. Push, publication, and remote-repository creation remain outside this release action.
