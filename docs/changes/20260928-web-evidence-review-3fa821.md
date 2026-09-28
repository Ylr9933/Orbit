---
record_version: 1
task_id: "20260928-web-evidence-review-3fa821"
title: "Surface benchmark evaluation health and evidence-linked research reviews"
branch: "feat/benchmark-review-20260928"
base_commit: "55f5c31"
work_status: in_progress
updated_at: "2026-09-28T22:33:24.075896+08:00"
pull_request: null
---

## Goal and acceptance

- Show saved scores, evaluation anomalies and actual terminal evidence separately without rescoring or altering original runs.
- Import version-bound authored reviews into existing batch/task pages, with validated evidence links and a readable/downloadable full report.
- Validate nested failures, terminal ambiguity, missing evidence, stale reviews, ownership and browser navigation; check real 60-task results read-only.
- Integrate all outstanding local branches and publish to both remotes as explicitly authorized.

## Changes

- Integrated the offline ASI review branch and reconciled its findings with the existing Web usability work.
- Added bounded recursive scoring diagnostics, terminal-event interpretation, independently labelled original execution status, batch filters and comparison/export warnings. Original metrics/aggregation are unchanged.
- Added strict review attachment validation, optimistic revisions and exact run/attempt/execution/artifact/result snapshot binding. Validate visible member ownership and exact trace steps; stale summaries are suppressed while the old report remains accessible.
- Reused existing batch/task pages for authored observations, explanations, hypotheses, evidence links and plain-text Markdown report view/download. No new navigation, runtime engine or dependencies.
- Updated the workbench runbook and proposed project overview. Prepared the real 20-case / 90-link report attachment outside Git.

## Decisions

- Reuse Workspace metadata and Records; no extra execution path, model runs or dependencies. Review prose is authored analysis, distinct from machine-record facts.
- Keep original metrics and aggregation unchanged. Unavailable evidence is unknown, not healthy.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git inventory and remote fetch | 55f5c31 | passed | Clean original checkout; both remotes fetched; review clone imported; isolated sibling worktree. |
| `make verify` | Implementation workspace on 64f2396 | passed | Lint, formatting, import boundaries, mypy, frontend checks, repository links, 428 Python tests (33 integration/E2E deselected), wheel/sdist and Web build. One existing Pydantic annotation warning. |
| Final Python lint/format/mypy, `pnpm check`, repository link check; workspace tests | Final source plus execution-plan snapshot binding | passed | 8 workspace tests repeated after final snapshot field addition; source checks passed. |
| `node --test tests/web/benchmark.test.mjs tests/web/execution-trace.test.mjs` | Web source | passed | 9 tests, including anomaly filters preserving zero/mean and unknown evidence. |
| `node tests/web/benchmark.smoke.cjs` with local Playwright/Chromium | Production Web build | passed | Real HTTP with explicit synthetic persisted evidence; filters, upload, report download, escaped HTML, scoring-file and trace links, existing comparison/navigation, desktop and 390px mobile. |
| `/tmp/prepare-web-review.py`; `/tmp/review-real-browser.cjs` | Existing immutable ASI batch; task Web build | passed | 60 numeric scores, unchanged mean 35.43277818088395, 19 evaluation anomalies, 59 completed terminal turns / 1 quota failure and 13 native-state conflicts. 20 cases / 90 scoped links validated. Browser GET-only, separate console registration state; report view/download and evidence navigation passed. |
| SHA-256 checks against original review source-hashes.json | Original ASI batch | passed | All 65 business files unchanged; runtime report and extracted artifacts stay outside Git. |
| New model/judge/Docker/GPU execution | None | not_run | Read-side/UI change; no rescoring or new execution budget. |
| Both remote branch settings and ancestry | origin/main and zjunlpgit/main at 6601e3d | passed | Both fetched tips are ancestors; GitHub reports main unprotected. No required review was bypassed or policy changed. |

## Open items and blockers

- Product implementation and acceptance passed. Import into the active local console, service update and remote publication remain.

## Next steps

- Import the validated runtime attachment, update only the Web process, fast-forward the integrated local branches and publish to both remotes.

## Compatibility and rollback

- Additive read models and console metadata only; preserve original scores and artifacts. Revert through a task branch and rebuild Web to roll back.

The first browser run exposed reduced first-screen density; compact health notices fixed it without weakening the test. Adding the score fixture also required disambiguating the old filename search. Final browser checks use explicit scoring paths. Temporary preview startup initially rejected a short test token, then passed with a valid test-only token. These were corrected before acceptance.

Full reports are displayed as escaped Markdown source; offline relative report links still require the original review directory. Online case evidence links are independently validated. Rules currently cover known BenchFlow/Codex evidence formats, not arbitrary evaluator failures or scientific correctness. Original scoring/status producers remain unchanged; the UI does not repair the evaluator or claim corrected scores.
