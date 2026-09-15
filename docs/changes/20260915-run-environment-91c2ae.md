---
record_version: 1
task_id: "20260915-run-environment-91c2ae"
title: "Implement solver-only research and isolated evaluator execution"
branch: "feat/run-environment"
base_commit: "8f09c14b7b984c7064c9c1c62d02b01068a71957"
work_status: completed
updated_at: "2026-09-15T20:54:54+08:00"
pull_request: null
---

## Goal and acceptance

- Implement the [Run/Environment contract](../architecture/run-environment-contract.md):
  solver-only research, frozen submissions, optional no-answer submission execution and clean scorer.
- Validate real CPU Docker isolation, cleanup and resource settings with bounded local fixtures.
- Keep execution, scoring, cleanup and lease release distinct; retain leases on uncertain cleanup.

## Changes

- Environment exposes generic immutable sandbox/process/lifecycle contracts and a local Docker backend.
  Resource limits come from leases; containers have owner labels, no privileged host mounts, readonly
  roots and bounded logs. Collection rejects symlinks, special files, traversal and excess artifacts.
- Run coordinates existing Tasks, Resources and command-Agent launch plans, preserving solver visibility.
  Absent/none evaluation completes without a scorer; unresolved/unsupported requirements fail closed.
- Trusted Tasks evaluation recipes separate submitted code execution from private answer scoring.
  Only explicitly projected feedback leaves controller records; feedback=none returns no detail.
- Local Records persists lifecycle events, environment references and final outcomes. Docker raw logs
  remain controller-only. Shared file hashing moved into contracts without changing Tasks digests.
- Added Chinese design/reference documentation, navigation and proposed project-status updates.

## Decisions

- Branch from existing Tasks implementation; broader unfinished authoring/tool/native-benchmark work
  stays in its [own record](20260915-task-implementation-a71e40.md).
- Use shell-free Docker CLI calls, local Unix daemon endpoints and one sequential lease per attempt.
  No new runtime dependencies, database migrations or global Docker changes.
- Research does not require evaluation. Declared evaluators cannot silently disappear from a run.
- Real tests use this host, existing python:3.12-slim, 1 CPU/256 MiB, stages of at most 15 seconds;
  no GPUs, model calls or network. Only test-owned containers are removed.
- Initial Docker tests exposed incompatible local logging compression with max-file=1.
  Explicit compress=false fixed startup; final real tests passed.

## Validation

Final code snapshot SHA-256: 42300788d115e3ba266c4108107df7a991e30d44938af2df4ae76ef37f7903a1.
Reproduce by sorting all *.py files under src/agent_infra and tests together with pyproject.toml
and uv.lock; feed each relative POSIX path, NUL, file bytes, NUL into SHA-256.
Documentation-only finalization follows that tested snapshot.

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Initial real Docker suite | Pre-fix workspace | failed | 6 failed/1 passed: Docker logging initialization; fixed before delivery. |
| make verify | Final code snapshot above | passed | Static/import/type/policy/link checks, 104 deterministic tests, Python and Web builds. |
| uv run --locked pytest tests/e2e/test_run_environment.py -q | Final code snapshot above | passed | 7 real Docker tests, 37.30 seconds. Solver-only, isolated scoring, actual submitted Python execution without answers, wrong-answer feedback, readonly inputs, timeout/cancel, background process removal, log bounds and unsafe paths. |
| uv run --locked python scripts/ci/smoke_wheel.py | Wheel built from final code snapshot | passed | Independent installed package and CLI smoke. |
| Docker container listing filtered by agent-infra.owner | Final test cleanup | passed | No remaining matching containers; tests also verify each handle removal. |
| Real model / GPU / Ray / native benchmark | None | not_run | Outside this CPU contract scope; no claim of provider authentication, GPU workload or native scoring equivalence. |

Docker image used: python:3.12-slim,
sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea.
OOM and cleanup-failure outcomes are deterministic fake-backed tests, not real OOM or daemon-outage experiments.

## Open items and blockers

- None for the approved local CPU execution contract and optional-evaluation scope.
- Follow-up capabilities: Run CLI/HTTP, host-Agent execution, persistent leases/crash recovery,
  ToolBinding, extra public inputs for submitted-code execution, native budget/environment adapters,
  native benchmark scorer equivalence and real model/GPU/multi-node validation.
- PR is null because this work has not been published; completion does not imply main integration.

## Next steps

- Maintainer review of this task branch. Continue with a budgeted real Agent vertical slice and Run
  gateways after review; no push or merge performed in this task.

## Compatibility and rollback

- Additive Python execution APIs. Existing Task material digest and manifest imports remain compatible.
  Unsupported native policies are rejected instead of ignored.
- Runtime state contains private credentials/logs/evaluator data and must remain outside Git and
  solver mounts. Retention and credential deletion are controller responsibilities.
- Before rollback, verify task-owned containers are gone; never discard leases while execution may
  remain. Revert this task branch's changes through the normal reviewed workflow.
