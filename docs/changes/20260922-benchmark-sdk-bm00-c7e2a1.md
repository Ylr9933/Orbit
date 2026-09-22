---
record_version: 1
task_id: "20260922-benchmark-sdk-bm00-c7e2a1"
title: "BM00: external benchmark adapter SDK and explicit preflight"
branch: "feat/benchmark-sdk-bm00"
base_commit: "0c8527b7a4233190afd914a9e715da81bfe0d59e"
work_status: completed
updated_at: "2026-09-22T16:33:28+08:00"
pull_request: null
---

## Goal and acceptance

- Deliver BM00 only; the user reviews each stage before authorizing the next stage.
- Public, versioned Benchmark SDK expresses pinned sources, single/sequence/paired/native work,
  resources, state, visibility, feedback, retry and independent outcome dimensions.
- Install an external adapter package, explicitly enable its distribution/version/entry point,
  and inspect/plan/check it without changing core registration or execution code.
- Validate four synthetic protocol fixtures and fail closed on incompatible packages, malformed
  plans, missing capabilities and inconsistent source/selection. A valid plan is not runtime proof.
- Supply an independent package template, authoring guidance and reproducible installation check.
- Preserve existing research entrypoints. No benchmark execution, models, Docker/GPU, publishing
  or merging in this stage. BM01 and official adapters remain separate tasks.

## Changes

- Added `benchmarks/api.py` SDK 1.0 immutable, strict JSON contracts and public `testing.py`
  conformance helper; separate `registry.py` for distribution metadata/explicit activation and
  `planning.py` for input snapshots, plan preservation, digests and offline capability checks.
- Added thin `benchmark adapters/inspect/plan/check` CLI with separate bootstrap composition.
  Plans are exclusive-created mode 0600, outside the immutable source. No execution path added.
- Added an independently buildable `examples/benchmark-adapter/` package consuming only public
  SDK imports, its own tests and four clearly synthetic fixtures. No official adapter claimed.
- Declared existing locked Pydantic as a direct dependency (no resolved version upgrades),
  incorporated the benchmarks layer in import-linter and tested reverse dependency rejection.
- Added installed-wheel acceptance in `scripts/ci/smoke_benchmark_adapter.py`, called by the
  existing wheel smoke check. No hosting/branch protection/CI requirements were weakened.
- Updated architecture/ADR, SDK reference, authoring guide, stage plan, documentation map,
  and project overview (BM00 explicitly marked task-branch/pending integration).

## Decisions

- Build on the reviewed design branch; retain its two unmerged documentation commits.
- External adapters use an explicitly enabled Python entry point; installing a package alone
  does not activate it. Adapters are trusted code, not a sandbox.
- Four fixtures prove expressiveness, not native benchmark scoring or official compatibility.
- SDK ships with core; adapter packages install separately and use `agent_infra.benchmarks.v1`.
  Distribution version and SDK must match explicit operator configuration. Enumeration does
  not import even enabled code; native metadata cannot select arbitrary Python modules.
- Unknown resource values remain unspecified. Native session, memory, checkpoint, material
  visibility and allowed in-trial evaluation remain distinct; no platform default rewrites them.
- Exact Agent/version/model/backend/protocol claims supplement required backend features.
  These are offline declarations only; check success never sets `runtime_ready` true.
- BM00 snapshots small local manifest roots. Remote data/image digests, runtime isolation,
  resource enforcement and native scoring equivalence require later adapter/backend evidence.
- Related design: [Benchmark layer](../architecture/benchmark-integration-layer.md),
  [design record](20260922-benchmark-layer-design-6a4d9e.md).

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git status and staged/unstaged diff inspection | `0c8527b` | passed | Clean design branch before creating task branch. |
| `uv run --locked pytest -q tests/unit/benchmarks tests/unit/test_cli.py` | BM00 source snapshot below | passed | 42 tests; 32 SDK/loader/CLI cases plus 10 existing CLI regressions. |
| `make verify` | Initial BM00 implementation, before final error-detail/factory-test additions | passed | 338 tests; lint/format/imports/mypy/docs, Web checks and both distributions passed. |
| `uv run --locked python scripts/ci/smoke_wheel.py` | Initial BM00 built wheel | passed | Existing isolated research CLI smoke plus external adapter wheel, four protocol plans and package tests; no PYTHONPATH/source-tree imports. |
| Final `make verify` and `uv run --locked python scripts/ci/smoke_wheel.py` | BM00 source snapshot below | passed | 342 tests, 23 integration/E2E deselected; lint/types/import/docs/Web/build all passed. Core + external adapter wheel checks passed outside source tree; four synthetic shapes and package conformance tested. |
| Scoped example lint/format, docs links, policy parity, `git diff --check` | BM00 workspace | passed | No policy mismatch or broken local links. |
| Real benchmark / Agent / Docker / GPU | None | not_run | Outside BM00 scope. |

Identifiable final code/tests/scripts/examples snapshot:
`sha256:d72fda3ed541df55a8112ca66b74d26713093bdee12601b53dc9a6bca3745c87`.
Computed over sorted unique `git ls-files --cached --others --exclude-standard` entries under
`src/agent_infra`, `tests`, `scripts`, `examples/benchmark-adapter`, plus `pyproject.toml` and
`uv.lock`: update SHA-256 with each UTF-8 path, NUL, file bytes, NUL. Documentation excluded.
Initial SDK roundtrip tests exposed a strict JSON-array conversion issue in a model-level
validator; moving version validation to a field validator fixed it before the successful checks.
The full suite emits one MCP/Pydantic settings forward-reference warning; no checks failed.
Temporary installation/plan directories were removed by the acceptance scripts; no runtime
artifacts, credentials, official benchmark data or installed plugin environments were committed.

## Open items and blockers

- None within BM00. Real adapters/execution are deliberately deferred, not BM00 blockers.

## Next steps

- Wait for the user's BM00 review before opening BM01. No further implementation authorized
  until that stage check; merging/publishing was not requested in this task.

## Compatibility and rollback

- Additive CLI and Python API; existing research state and execution paths are unchanged.
- Revert this task's code/docs/dependency changes to remove BM00. No state migration is planned.
- Existing research paths and runtime state were not changed or restarted. No branch merged,
  pushed or published; the two earlier design commits remain in this task branch's ancestry.
