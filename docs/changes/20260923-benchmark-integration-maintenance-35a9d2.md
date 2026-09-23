---
record_version: 1
task_id: "20260923-benchmark-integration-maintenance-35a9d2"
title: "Post-merge benchmark code maintenance"
branch: "refactor/benchmark-bm07-integration"
base_commit: "204df61cc061464729cfdaa929619e2f758646e0"
work_status: completed
updated_at: "2026-09-23T11:25:26+08:00"
pull_request: null
---

## Goal and acceptance

- Review the integrated BM05-B/BM06/BM07 code and remove an avoidable BM07 orchestration tangle.
- Keep compatibility display read-only, preserve native handoff and Run semantics, and verify the
  independent-adapter acceptance still works.
- Reconcile the project overview with the integrated main branch.

## Changes

- Moved compatibility publication, local evidence checks and native handoff dispatch from
  `bootstrap/benchmark_execution.py` to `bootstrap/benchmark_delivery.py`; no new core path.
- Made compatibility `show` avoid creating benchmark state, and use read-only Run control only when
  local Run evidence is referenced. Kept the existing atomic matrix file update.
- Made read-only lease/campaign SQLite URIs robust to escaped paths and fixed Web matrix row keys
  for multiple exact tuples. Reconciled project status and BM07 reference with merged PR facts.

## Decisions

- Scope maintenance to the newly integrated benchmark delivery path; preserve the established
  public contracts and benchmark-specific semantics.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git integration review | `204df61cc061464729cfdaa929619e2f758646e0` | passed | PRs #6, #7 and #8 are merged into origin/main. |
| `uv run --locked pytest -q tests/unit/benchmarks/test_bm07.py tests/unit/benchmarks/test_execution.py` | maintenance workspace, 2026-09-23 11:25+08:00 | passed | 20 tests, including empty-state read-only behavior. |
| `uv build && uv run --locked python scripts/acceptance/benchmark_extension.py` | maintenance workspace, 2026-09-23 11:25+08:00 | passed | Independent wheel and one real local CPU Run with Records and matrix. |
| `make verify` | maintenance workspace, 2026-09-23 11:25+08:00 | passed | 398 non-integration/non-E2E tests, wheel and Web build; one pre-existing Pydantic warning. |

## Open items and blockers

- None within this maintenance scope. Real official submissions, model calls, GPU and multi-node
  runs remain separate acceptance work.

## Next steps

- Submit this branch for review and verify its merge into main.

## Compatibility and rollback

- No contract or schema change intended. Reverting this refactor must leave BM07 state files intact.
