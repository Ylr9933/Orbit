---
record_version: 1
task_id: "20260923-benchmark-batch-bm05b-6c2f91"
title: "BM05-B: bounded benchmark concurrency, usage accounting and recoverable artifacts"
branch: "feat/benchmark-batch-bm05b"
base_commit: "8ce8a31f45183ad7800ec4eb06ed19b1ecd7d0d2"
work_status: completed
updated_at: "2026-09-23T10:26:14+08:00"
pull_request: null
---

## Goal and acceptance

- Make the durable benchmark queue admit multiple jobs up to an explicit persisted operator capacity,
  preserve deterministic FIFO fairness, and never allocate more than the authorized envelope.
- Expose requested, admitted, physically attested and measured resources separately; retain
  per-attempt elapsed budget and bounded usage evidence across restart and cleanup.
- Recover large artifact transfer without duplicating finished work or treating incomplete bytes
  as a complete Records artifact. Keep private benchmark material outside solver visibility.
- Cover contention, restart, cancellation, exhaustion and transfer failure with meaningful tests.

## Changes

- Persist configurable per-state-directory slot and numeric capacity; read it in every admission
  transaction, retain strict FIFO and add an explicit polling worker.
- Reserve planned wall time per budget group; charge measured terminal time when available and
  fail over-budget work before launch. Store requested, authorized, attested allocation and
  measured usage separately in the final Records result.
- Sample managed process-group CPU, memory and I/O best effort. Import large declared outputs
  through resumable collection and content-addressed Records blobs, publishing only after hash
  validation. Harbor reports Docker-inspected limits without mislabeling parent-process usage.
- Update CLI, operator/reference/implementation guidance and proposed project overview.

## Decisions

- Preserve BM05-A's single-authority SQLite queue and lease ledger. Add capabilities through
  backend-neutral contracts, with unsupported physical metrics represented explicitly as unknown.
- Retain FIFO head-of-line blocking for predictable admission; capacity is authorization, not a
  kernel-enforced process/container limit. The worker is an opt-in local polling process.
- Budget groups are scoped to one state directory and charged conservatively when terminal
  usage is unavailable. Partial blobs remain inaccessible until fully verified.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git/context inspection | `8ce8a31f45183ad7800ec4eb06ed19b1ecd7d0d2` | passed | Clean synchronized `main`; isolated BM05-B branch created. |
| `uv run --locked pytest -q tests/integration/test_managed_process.py tests/unit/runs/test_benchmark_execution.py tests/unit/resources/test_persistent.py tests/unit/records/test_local.py tests/unit/benchmarks/test_execution.py` | BM05-B workspace before final documentation | passed | 51 tests, including interrupted collection, 65 MiB interrupted blob transfer, FIFO capacity and budget exhaustion. |
| `uv run --locked pytest -q tests/unit/resources/test_persistent.py` | BM05-B final code snapshot | passed | 4 tests after adding cross-instance capacity refresh assertion. |
| `uv run --locked pytest -q tests/unit/runs/test_benchmark_execution.py` | BM05-B final code snapshot | passed | 14 tests after adding pre-persistence budget limit conflict rejection. |
| `make verify` | BM05-B final code snapshot | passed | Import graph, Ruff, mypy, documentation links, 389 unit/contract tests, wheel build and Web build passed; 33 integration/E2E excluded by repository target. |
| `uv run --locked ruff check adapters/harbor-runtime/src && uv run --locked ruff format --check adapters/harbor-runtime/src` | BM05-B final code snapshot | passed | Harbor adapter lint and formatting passed. |
| `uv build && uv run --locked python scripts/acceptance/benchmark_execution.py` | BM05-B code snapshot | passed | Independent wheel and real local CPU process completed; Records artifact and resource accounting inspected. |
| Real GPU, multi-node and native Harbor resource monitoring | Not available in this acceptance scope | not_run | Requires explicit runtime/environment scope; unsupported usage fields remain null. |

## Open items and blockers

- No blocker for the scoped single-node implementation. Native container GPU/IO usage and
  cross-node/object-store resumable transfer are later work; current local measurement is best effort.

## Next steps

- Review and merge this branch when the user approves the stage; then use a realistic bounded
  batch before expanding to BM06.

## Compatibility and rollback

- Preserve existing BM01/BM05-A default single-slot behavior and plan schema. Any new persisted
  fields must load safely when absent; state rollback must not drop active leases or artifacts.
- Raising output limits is opt-in per adapter; the default remains 16 MiB. To roll back code,
  first drain worker and leases and preserve the complete state directory, including `.part` files.
