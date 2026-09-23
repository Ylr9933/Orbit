---
record_version: 1
task_id: "20260923-benchmark-delivery-bm07-8c6e41"
title: "BM07 benchmark usage and extension acceptance"
branch: "feat/benchmark-delivery-bm07"
base_commit: "f4c1c67e4eaa7eb202611f89715048b1a97d9f91"
work_status: completed
updated_at: "2026-09-23T11:14:13+08:00"
pull_request: null
---

## Goal and acceptance

- Give the local administrator a usable Batch/Campaign view without revealing benchmark private
  material or duplicating the benchmark Run state machine.
- Add an adapter-owned native submission handoff with explicit scope and evidence, and a pinned
  compatibility matrix that does not turn declarations into official certification.
- Rehearse a new independent benchmark package using only package/configuration changes for an
  already-supported backend; document where a genuinely new backend is necessary.
- After validation, integrate the currently unmerged BM05-B, BM06 and BM07 branches through the
  authorized review path, then perform a scoped repository cleanup and integration checks.

## Changes

- Added authenticated read-only Batch/Campaign/compatibility Web projection, without raw private
  benchmark results or commands. Existing queue, lease and campaign databases use read-only
  connections for this view.
- Added pinned compatibility matrix publication with enabled-adapter identity checks and local
  `run:` evidence verification. External evidence remains an explicit administrator claim.
- Added adapter-owned submission preparation and explicit one-shot sender. Persisted intent
  precedes external send; uncertain outcomes cannot be blindly retried.
- Added independent third-party wheel rehearsal in an isolated venv, plus CLI/Web user guidance.

## Decisions

- Keep native official upload adapter-owned and opt-in. The generic bridge prepares a bounded,
  immutable handoff; without a native submission extension it remains a manual external handoff.
- Build read-only Web queries from existing benchmark control/lease/campaign state.
- Submission receipts indicate delivery only, not official acceptance. Reference adapters have no
  submission hook; the one-shot bridge is exercised with a local test adapter.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Branch and plan inspection | `f4c1c67e4eaa7eb202611f89715048b1a97d9f91` | passed | Clean BM06 branch; BM05-B and BM06 are the only local branches not merged into main. |
| `uv run --locked pytest -q tests/unit/benchmarks/test_bm07.py` | BM07 workspace, 2026-09-23 11:12+08:00 | passed | 3 focused tests: matrix identity, one-shot handoff, HTTP privacy/auth. |
| `uv build && uv run --locked python scripts/acceptance/benchmark_extension.py` | BM07 workspace, 2026-09-23 11:12+08:00 | passed | New wheel installed in isolated venv; one real local CPU Run, Records, matrix and dashboard projection. |
| `uv run --locked ruff check src/agent_infra tests/unit/benchmarks/test_bm07.py && uv run --locked mypy && uv run --locked lint-imports --no-cache` | BM07 workspace, 2026-09-23 11:12+08:00 | passed | 149 source files, dependency direction kept. |
| `pnpm check` and `uv run --locked python scripts/ci/check_repository.py` | BM07 workspace, 2026-09-23 11:12+08:00 | passed | TypeScript, Biome, policy mirrors and Markdown links. |
| `make verify` | BM07 workspace, 2026-09-23 11:14+08:00 | passed | 398 non-integration/non-E2E tests; wheel and Web production build. One pre-existing Pydantic warning. |

## Open items and blockers

- BM07 implementation has no remaining acceptance item. Integration and scoped post-merge maintenance
  are separate Git steps. Real official submission, paid Agent calls and GPU/multi-node work are
  outside this acceptance scope.

## Next steps

- Commit BM07, merge BM05-B/BM06/BM07 through review, then inspect integrated code in a maintenance task.

## Compatibility and rollback

- Existing Run control state and benchmark protocol are unchanged. Additive compatibility and
  submission files under the benchmark state directory should be retained during code rollback;
  Web and CLI routes can be removed independently. Submitted external results cannot be undone by
  reverting code.
