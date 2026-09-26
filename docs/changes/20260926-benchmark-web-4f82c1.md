---
record_version: 1
task_id: "20260926-benchmark-web-4f82c1"
title: "Benchmark workspace, comparison and evidence review"
branch: "feat/benchmark-web-workspace"
base_commit: "b7079f4c3226460639104186bddb38131dd6b216"
work_status: completed
updated_at: "2026-09-26T09:17:15.973376+00:00"
pull_request: null
---

## Goal and acceptance

- Deliver a compact Benchmark workspace: register existing batches across state directories, inspect all members, compare scores on matched tasks, inspect evidence, save notes and export results.
- Keep missing/invalid scores visible; distinguish descriptive means from native/official aggregation. No new model execution, automatic retry or scoring changes.
- Support searchable trajectories, stable links, side-by-side runs, artifact preview/download and configuration comparison.
- Preserve existing console APIs and unrelated research screens. Validate backend boundaries, comparison semantics, browser desktop/mobile flows and `make verify`.

## Changes

- Added a separate Benchmark workspace metadata store for registered batch directories, optimistic notes, project/tags and default baseline.
- Added pure Run score/config projections and matched-task comparisons; preserve missing, invalid, zero, duplicate and incompatible results. Trend excludes incomplete/duplicate task sets.
- Added run-scoped artifact previews/downloads and full normalized archive search with bounded fallback, paired tool steps, deep links, side-by-side review and task navigation.
- Added optional Records read-only construction and bounded committed stream tails. Cancel writes only an existing Run intent for the worker.
- Replaced the default Benchmark screen with a batch/results workflow; retained prior Campaign and compatibility diagnostics behind an expandable section. No new dependencies or execution backend.
- Added CSV, Markdown and SVG export, browser opt-in completion notifications, explicit coverage and failure summaries; responsive desktop/mobile layout.
- Original TB-Science worktree remains untouched. Adapter packages and source manifests are unchanged.

## Decisions

- Base on the committed batch implementation. Generic archived-evidence support will accept ASI and Harbor projections without depending on uncommitted adapter work.
- Use existing batch manifests, Run control state and Records; keep workspace annotations separate from immutable execution evidence.
- Read routes must not advance queues or launch execution. Registration explicitly selects a batch directory; never scan arbitrary host directories.
- Native real-time trace streaming remains a later extension; display persisted activity and archived evidence honestly.

## Validation

Final source/test snapshot: SHA256 `99bb35cc9d77d9c7ca0ecde5d5cff2ca111d4b027638df2a0cb8c8241f26aa5e` of `git diff --cached -- src tests` against base `b7079f4` (before documentation-only finalization).

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git/source inspection | b7079f4 plus isolated worktree | passed | Existing TB-Science edits overlap Web; work isolated without copying or changing them. |
| `make verify` | Implemented workspace based on b7079f4 | passed | 412 tests passed, 33 integration/E2E deselected; Ruff, mypy, import boundaries, links, Python/Web builds. One existing Pydantic warning. `/tmp/benchmark-web-verify.log`. |
| `node --test tests/web/benchmark.test.mjs` | Workspace frontend | passed | 3 checks: CSV zero/missing/formula escaping, explicit tool pairing, config/status interpretation. |
| Synthetic browser workflow | Built workspace frontend | passed | 60-task pagination, paired comparison/trend export, notes/reload, trace search and deep links, files/downloads, registration, incomplete results, 390px layout. Final polling refinement also passed. Screenshots: `/tmp/benchmark-web-comparison.png`, `/tmp/benchmark-web-evidence.png`, `/tmp/benchmark-web-mobile.png`. |
| Existing research browser regression | Final Web build | passed | Init/compile/preflight/idempotent submit/reload/cancel/artifacts/analysis/mobile/private filtering passed. Corrected a stale English `cancelled` assertion to the existing Chinese label; no research behavior change. |
| Final frontend and documentation checks | Final workspace | passed | `pnpm check`, Web build, 6 Node tests (Benchmark + research trace), Ruff/check-format, Markdown links and `git diff --check`. |
| Existing real ASI batch read-only projection | Current stored 60-task batch, no execution action | passed | Registered through a temporary console. At inspection: 60 members, 13 scored; sampled artifact had 15 files and 90 searchable steps, capture partial retained. No model, submit, cancel or worker call. |
| Real model/Docker/GPU execution | None | not_run | Not required for this UI/read-model change. No new score or benchmark acceptance claim. |

## Open items and blockers

- None for the delivered batch review/comparison/evidence workflow.
- Native real-time token streaming, arbitrary replay/new-run launch, batch stop-dispatch controls, official suite aggregation and multi-seed significance remain future execution/protocol work; current UI does not claim those capabilities. Long artifacts retain documented preview/download bounds.

## Next steps

- Implementation and validation complete. Review/integrate `feat/benchmark-web-workspace` when authorized; no push or merge requested. Original TB-Science branch was not modified by this task.

## Compatibility and rollback

- Additive console queries/metadata and explicit Run cancel-intent command; preserve native plans, scores and Records. Revert this branch to restore the prior UI; workspace annotations may remain on disk.
