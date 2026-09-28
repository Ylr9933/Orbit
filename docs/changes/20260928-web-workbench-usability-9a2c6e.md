---
record_version: 1
task_id: "20260928-web-workbench-usability-9a2c6e"
title: "Simplify the research and benchmark Web workbench"
branch: "feat/web-workbench-usability-20260928"
base_commit: "6601e3dafeea1c98cb5cdef5ac836b96bc1bb169"
work_status: completed
updated_at: "2026-09-28T20:10:22+08:00"
pull_request: null
---

## Goal and acceptance

- Implement the approved workbench design as a maintainable, usable first UI improvement: U1 navigation/results, U2 task evidence, and organization of the existing comparison workflow.
- Use existing API/Records contracts and real ASI 60-task records for read-only acceptance; preserve research project initialization, submission and old deep links.
- Verify exact score/coverage semantics, URL-persistent filters and navigation, completed-run polling, desktop/mobile/browser workflows, and required repository checks.
- Persistent benchmark rerun orchestration (U4) remains a separate backend task; do not add nonfunctional launch buttons or start model/Docker workloads in this UI task.

## Changes

- Reorganized the UI around four primary entries: experiments, research projects, resources and settings. Existing task, run, records, overview and Agent routes remain available through settings and direct links.
- Separated experiment list, batch results and task review. Batch results show valid-score mean/median, coverage, zero scores and measured median runtime; task names open readable results before trajectory/files/configuration. Running tasks still open collected logs.
- Added task/domain/state search and filters, numeric ordering, 20/50-item pagination and URL persistence. Returning from a task restores the result filters, page and scroll position. Keyboard users can skip directly to the main content; narrow screens retain local table scrolling without page overflow.
- Distinguished native solver timeout, measured duration and outer orchestration budget. Zero remains valid; missing/invalid scores are not filled with zero. Display values use two decimal places (scientific notation for tiny nonzero values); CSV exports and the experiment-summary Markdown preserve raw score precision. The comparison Markdown is a formatted reading summary; use its CSV for full precision.
- Made native trace messages readable, retained command/output blocks and deep links, and exposed incomplete capture clearly. File browsing prioritizes scoring/submission evidence while preserving the existing preview/download limits and visibility filtering.
- Reorganized comparison around baseline selection, configuration differences, per-task changes and optional side-by-side trajectories; folded trend/matrix views behind explicit expansion. Existing notes and exports remain functional.
- Added research project name/goal and status filtering. Extracted `features/execution-events.tsx` so research execution and legacy Records share readable event grouping, search and pagination.
- Stopped automatic reads of completed batches and runs; provided manual refresh for finished task evidence. `useData` preserves the last successful response during refresh so forms and navigation do not disappear unnecessarily.
- Split Web responsibilities across `batch-list`, `batch-header`, `batch-summary`, `batch-detail`, `run-result` and pure `presentation` helpers. No backend contract, database, execution engine, dependency or lockfile changes.
- Updated the [workbench runbook](../operations/benchmark-workspace.md), [Web guide](../operations/web-console.md), design status, documentation map and proposed [project overview](../project-status.md).

## Decisions

- Follow [the workbench proposal](../product/experiment-workbench-design-20260928.md), keeping research projects directly accessible and module diagnostics secondary.
- No new frontend framework or dependencies; reuse existing comparison, trajectory and evidence APIs.
- Treat a UI experiment as an existing benchmark batch; do not merge that object with the research Experiment contract. Comparison still uses the backend's protocol/material matching and reports configuration differences separately.
- Keep ASI-specific friendly domain labels in presentation helpers; unknown task IDs are preserved. Do not infer missing resource, model, timeout or trace data.
- Retain the original HTML attachment as a design prototype. Production behavior is implemented in `src/web/`; the prototype's rerun preview is not presented as an implemented feature.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git and design/source inspection | 6601e3d | passed | Clean main; isolated task branch; existing read models and browser fixtures available. |
| `make verify` | Intermediate task workspace on 6601e3d; Vite assets `index-DzVLJisJ.css` / `index-DqBtlVFu.js` | passed | Lint/format, typing, import boundaries, repository policy/links, 418 Python tests, wheel/sdist and frontend build. 33 integration/E2E tests deselected; one existing Pydantic annotation warning. Backend files remained unchanged after this check. |
| `pnpm check` and `pnpm build` | Final source snapshot S1 | passed | 42 files checked, TypeScript and production build successful; final JS `index-BVypV0pb.js`. No new dependencies. |
| `node --test tests/web/benchmark.test.mjs tests/web/execution-trace.test.mjs` | S1 | passed | 8 tests: valid zero/missing scores, search/sort/page bounds, time rounding, config completeness, exports and event/tool pairing. |
| `node tests/web/benchmark.smoke.cjs` with local Playwright/Chromium | S1 | passed | Real HTTP/Records paths with explicit synthetic 60-task data. List/detail, five rows on the 1440×900 first screen, keyboard focus, URL/reload/back/scroll, pagination, stopped polling/manual refresh, notes, comparison/CSV/SVG, trace deep links, files, incomplete batch and 390px layout. No private fixture sentinel or browser exceptions. |
| `node tests/web/workflow.smoke.cjs` with local Playwright/Chromium | Task workspace before final presentation-only cleanup | passed | Research project binding/init/compile/preflight/submit/reload/cancel, results/analysis, Job separation and mobile. Fixture execution backend, no real model or Docker; final cleanup did not change these workflow components. |
| `node tests/web/console.smoke.cjs` with local Playwright/Chromium | Task workspace before final presentation-only cleanup | passed | Legacy project edit/reload, task/run/trace/artifact links, actual host sampling, new navigation, legacy routes, mobile and logout. Real host reads; project/Records data are fixtures. |
| Read-only real ASI browser acceptance: `node /tmp/workbench-real-browser.cjs` | S1; existing `benchmark/asibench/b3-gpt-6-sol-codex01571-20260926` | passed | 60/60 valid scores; mean 35.43, five zero scores. Result → actual archived Codex trace → scoring-file preview; filter return and mobile distribution. Separate temporary Web registration/state, all browser API writes blocked; no changes to original run records. |
| Visual review of real-data desktop, result and mobile screenshots | S1 production assets | passed | Neutral layout, task table in first screen, separate result/configuration, contained horizontal scrolling; screenshots kept outside Git under `/tmp/workbench-asi-*-20260928.png`. No claim of full WCAG audit. |
| `uv run --locked python scripts/ci/check_repository.py`, `git diff --check` and staged review | S1 plus final documentation | passed | Policy mirrors/local links, no whitespace errors; source and task-owned documentation only. |
| New real model, Docker/GPU or benchmark rerun | None | not_run | Outside UI acceptance scope. Existing ASI records were read only; no new execution budget consumed. |

S1 is the SHA-256 of `git diff 6601e3d <task-commit> -- src/web tests/web`:
`62f7e21886278d02433a7dc7476b6909cccecb6c26d25c9adeb6f9077e0c9c08`.
During development the same snapshot was obtained with `git diff --cached -- src/web tests/web | sha256sum`.

Browser commands used `PLAYWRIGHT_MODULE=/home/wangxuehai/.npm-global/lib/node_modules/openclaw/node_modules/playwright-core` and `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/disk/disk_20T/wangxuehai/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome`; nothing was added to repository dependencies. Local check logs are `/tmp/workbench-verify.log`, `/tmp/workbench-check-final.log`, `/tmp/workbench-node-final.log`, `/tmp/workbench-build-final.log`, `/tmp/workbench-browser-final.log`, `/tmp/workbench-research-browser-final.log`, `/tmp/workbench-console-browser.log` and `/tmp/workbench-real-browser-final.log`.

Initial browser checks exposed page overflow at 390px and the legacy Records view still using raw event rows. The grid now explicitly allows shrinking and Records shares the readable event component; both checks passed after correction. Temporary read-only Web acceptance server was stopped after verification; existing user services were not restarted.

## Open items and blockers

- None for this UI scope. Persistent rerun orchestration, attempt selection and budget-aware re-submission (U4) remain follow-up backend work. No live token streaming, official-score equivalence or additional benchmark execution is claimed.

## Next steps

- Review and integrate this task branch when requested. The frontend build is ready in `src/web/dist`; existing services using that directory can serve it on browser reload. No production service/state migration was performed.
- Follow-up: design persistent task attempts and rerun intents before adding executable rerun controls to the workbench.

## Compatibility and rollback

- Existing APIs, Records, benchmark scoring and legacy routes remain compatible; new URL query keys are presentation state. The default navigation changes from overview to experiment list; secondary pages remain under settings.
- Revert the task commit on an appropriate branch and rebuild Web assets to roll back. No runtime database, benchmark protocol, original evidence or credential migration is required.
