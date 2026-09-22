---
record_version: 1
task_id: "20260922-benchmark-reliability-bm05a-91d7c4"
title: "BM05-A: persistent benchmark queue, leases, and recovery reconciliation"
branch: "feat/benchmark-reliability-bm05a"
base_commit: "6dc55803864d6f52145f8500bf6f269850724fca"
work_status: completed
updated_at: "2026-09-22T21:51:53+08:00"
pull_request: null
---

## Goal and acceptance

- Implement BM05-A only: a minimal persistent FIFO queue, durable resource leases and execution
  association/reconciliation before adding another long-running benchmark.
- Preserve idempotent operation submission. A second valid operation waits instead of failing when
  the bounded execution capacity is occupied; queued cancellation must never launch a backend job.
- Persist lease/request ownership and owner epoch. Restarted coordinators query the existing native
  handle before progressing, never launch the same operation twice, and do not release capacity
  until execution cleanup is positively confirmed.
- Distinguish unsatisfiable requests from temporary waiting, retain reconciliation/quarantine
  states, and reject stale-owner updates.
- Validate with bounded local CPU processes only: no model, Docker, GPU, network job or remote node.

## Changes

- Added a SQLite-backed Resources lease ledger with persisted capacity identity, idempotent
  request/owner claims, owner epochs, native job association, reconciliation quarantine, positive
  cleanup release and retained history.
- Changed new benchmark execution intents to durable FIFO `queued` state. Only the queue head can
  request a lease; temporary shortage waits, impossible configured requests fail without launch,
  and queued cancellation never contacts the backend.
- Made launch and collection recovery lease-aware. A crash after lease commit reuses the same
  request, lost submission replies retain capacity for reconciliation, and cleanup/Records
  completion is required before release.
- Added `agent-infra benchmark queue`, wiring for shared stores, unit fault-window coverage, and an
  installed-wheel two-operation acceptance scenario. Updated reference, implementation, operation,
  development and project-status documentation.

## Decisions

- Keep one authoritative queue in Runs and one persistent lease ledger in Resources. Do not add a
  second queue to the resource layer.
- Maintain deliberately low local concurrency for BM05-A. Wider fairness, backfill, sampling,
  budgets and remote Worker/Ray scheduling remain BM05-B or later.
- Keep default numeric capacity unset: the lease proves exclusive local admission, while the
  execution backend remains responsible for physical CPU, memory and GPU enforcement. Persisted
  capacity cannot silently change when reopening a state directory.
- Related plans: [benchmark stages](../development/benchmark-development-plan.md) and
  [six optimization workstreams](../development/infra-six-optimizations-plan.md).

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git/context inspection | `6dc55803864d6f52145f8500bf6f269850724fca` | passed | Clean synchronized `main`; isolated BM05-A branch created. |
| Focused unit tests: `pytest -q tests/unit/resources/test_persistent.py tests/unit/runs/test_benchmark_execution.py tests/unit/benchmarks/test_execution.py` | Final workspace snapshot before commit | passed | 27 passed; includes contention, stale owner, cleanup quarantine, FIFO restart, queued cancel, lease-commit crash and no duplicate native launch. |
| Installed-package acceptance: `uv build && uv run --locked python scripts/acceptance/benchmark_execution.py` | Final workspace snapshot before commit | passed | Core and external adapter wheels installed in a disposable venv; two real bounded CPU processes queued in order, leases/native IDs persisted and released, fresh CLI queries and Records artifact completed. No model, Docker, GPU or network job. |
| Repository verification: `make verify` | Final workspace snapshot before commit | passed | Ruff, formatting, import boundaries, mypy, Biome/TypeScript, repository policy/links, 381 non-integration/non-E2E tests and Python/Web builds passed. 32 tests were deselected by the target; one pre-existing Pydantic settings warning remained. |
| Diff review: `git diff --check` and final staged review | Final workspace snapshot before commit | passed | No whitespace errors, generated runtime state or credentials included. |

## Open items and blockers

- None for the approved BM05-A scope. There is no constant scheduler loop, cross-state-directory
  authority, physical process resource enforcement, fair concurrency, usage sampling or remote
  Worker/Ray support; these remain explicit BM05-B/backend work rather than BM05-A blockers.

## Next steps

- User reviews BM05-A. Do not start BM03 PAST-Bench until the next instruction.

## Compatibility and rollback

- Existing BM01/BM02 control schema remains version 1. New submissions use additive document
  fields; legacy `accepted` intents without launch authorization retain conservative no-auto-launch
  behavior. The new lease database has its own schema/version and rejects a different capacity.
- Before rollback, drain/cancel work and confirm all leases released; back up control, lease,
  backend spool and Records together. Older code ignores the lease ledger, so it must not operate
  the same state directory while a lease or native job may still be active.
