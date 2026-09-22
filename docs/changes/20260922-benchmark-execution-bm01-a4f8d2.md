---
record_version: 1
task_id: "20260922-benchmark-execution-bm01-a4f8d2"
title: "BM01: durable managed execution and conservative recovery"
branch: "feat/benchmark-execution-bm01"
base_commit: "e3a30a8122dda570dfcd2f19c7d04802bb70e4f7"
work_status: completed
updated_at: "2026-09-22T17:27:46+08:00"
pull_request: null
---

## Goal and acceptance

- Implement BM01 only, extending BM00 independent packages with a separate execution extension.
- Public Environment ExecutionSpec/Handle and submit/observe/cancel/reconcile/collect/cleanup
  contracts. Freeze and review a command before execution; preserve BM00 planning compatibility.
- Reuse RunControlStore and Records. Persist operation intent before launch; same operation
  never silently reruns, changed payload conflicts, and recovery queries before taking action.
- A local cooperative process supervisor survives CLI/coordinator exit, persists bounded raw
  logs and timeout/cancellation/result evidence, and retains unknown operations for reconciliation.
- Confirm cleanup before releasing the durable execution slot; retain raw data until Records
  collection succeeds. Execution, capture, cleanup and scoring remain separate.
- Test lost replies, crash windows, resumed log cursors, PID ownership, cancellation, timeout,
  collection errors and slot quarantine. Real acceptance uses task-owned temporary CPU processes
  on this node, one job at a time, no models/Docker/GPU/network jobs; each command at most 30 s.

## Changes

- Added optional SDK execution extension 1.0 and independently installable CPU process fixture;
  planning-only BM00 packages and files remain valid.
- Environment contracts plus detached Linux process supervisor: durable launch/owner/result
  journal, boot/PID/starttime identity, scoped pidfd signals, bounded raw logs and safe outputs.
- Run coordination reuses RunControlStore and Records: durable operation intent, query-first
  recovery, retained execution slot, idempotent events/cursors, and separate capture/cleanup results.
- Thin prepare/run/status/cancel/reconcile/events/artifacts CLI and isolated benchmark state;
  actual backend admission rejects unsupported allocations, private materials and platform retries.
- Fixed existing Records raw-stream creation and file/cursor commit crash windows required by
  BM01 recovery; committed data loss fails explicitly rather than inventing bytes.
- Added reference/implementation guides, independent-wheel acceptance and fault/process tests;
  updated documentation routing, stage plan and proposed project overview.

## Decisions

- Build on unmerged BM00; no merge, push or BM02 work in this task.
- Initial backend is explicitly trusted/cooperative host processes. Its cleanup scope is the
  owned process group; it is not a sandbox for hostile agents, escaped daemons or Docker children.
- First runnable plan is one atomic WorkUnit and one native-owned phase; the native runner
  owns any internal sequence. Reject unsupported resource/isolation requirements rather than
  infer GPU/container enforcement. Multi-unit scheduling remains BM05.
- Reuse the control store under a benchmark subdirectory, avoiding interference with the existing
  research Controller's interrupt-and-clean recovery. A durable single execution slot is not a
  numeric resource lease; persistent shared resource allocation remains BM05-A.
- Reference: [stage plan](../development/benchmark-development-plan.md),
  [BM00](20260922-benchmark-sdk-bm00-c7e2a1.md).

## Validation

Final implementation snapshot: SHA-256
`ea59cd778eed78fc3598d43be7603a47866d8e69ce15757c1d3047e5a266eaeb`.
Calculated over the sorted unique cached/untracked non-ignored Git file list under `src/`,
`tests/`, `scripts/`, and `examples/benchmark-execution/` (245 files), concatenating each
relative UTF-8 path, NUL, file bytes, NUL. Documentation outside these paths is not part of
this code snapshot; the final documentation links and staged diff were checked separately.

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git status/diffs and existing contracts inspected | `e3a30a8` | passed | Clean BM00 branch; new task branch created. |
| `make verify` | Final implementation snapshot above | passed | 366 tests passed, 31 integration/E2E deselected; lint/format, 141-file mypy, dependency graph, docs, frontend checks and both builds passed. Existing MCP/Pydantic lifespan forward-reference warning remains. |
| `uv run --locked pytest -q -m integration tests/integration/test_managed_process.py` | Final implementation snapshot | passed | 8 backend integration tests, including real Linux jobs and injected launch failure: re-instantiation, same operation once, timeout/cancel, background cleanup, bounded logs, unknown launch/owner, symlink rejection and credential environment exclusion; 5.11 s. |
| `uv run --locked python scripts/ci/smoke_wheel.py` | Core wheel built by make verify | passed | Existing installed core CLI/project smoke plus independent BM00 adapter wheel and all four synthetic planning fixtures; no source-tree imports. |
| `uv run --locked python scripts/acceptance/benchmark_execution.py` | Core wheel + independent process example wheel from final snapshot | passed | Outside checkout: opt-in before state creation, freeze/prepare/run, separate CLI processes, duplicate operation, native identity, 5 nonduplicated events, one artifact, Records raw sum/result bytes and final slot release. Temporary operation cleaned. |
| `uv run --locked ruff check examples/benchmark-execution` and `ruff format --check examples/benchmark-execution` | Final implementation snapshot | passed | Independent example source and configuration scripts checked. |
| `uv run --locked python scripts/ci/check_repository.py`; `git diff --check` | BM01 documentation workspace | passed | Policy mirrors unchanged; local Markdown targets valid; no whitespace errors. |
| Real models, Docker/GPU, four upstream benchmarks, remote backend | None | not_run | Outside BM01 acceptance; no scoring equivalence or hardware allocation claimed. |

## Open items and blockers

- None for approved BM01 scope. Native runner adapters, container/job-scoped cleanup and resource
  enforcement, durable queue/leases, formal scoring, and manual quarantine resolution remain later
  stages. The host process backend is not a security boundary.

## Next steps

- User reviews BM01 before authorizing BM02-A. No BM02 changes, merge or push in this task.

## Compatibility and rollback

- Additive APIs/commands. Preserve SDK 1.0 planning files and existing research state.
- Stop task-owned processes before reverting runtime code; keep benchmark control/evidence
  directories for diagnosis. Never automatically replay unknown operations after rollback.
