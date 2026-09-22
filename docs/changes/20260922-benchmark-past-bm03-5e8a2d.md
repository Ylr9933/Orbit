---
record_version: 1
task_id: "20260922-benchmark-past-bm03-5e8a2d"
title: "BM03: independent PAST-Bench adapter and stateful sequence evidence"
branch: "feat/benchmark-past-bm03"
base_commit: "7c74c0f8278fe6d8f63e213ce2e8cc4164db7eaf"
work_status: completed
updated_at: "2026-09-22T23:05:00+08:00"
pull_request: null
---

## Goal and acceptance

- Implement BM03 as an independently installable PAST-Bench adapter pinned to a reviewed upstream
  revision, without adding benchmark-name branches to the core scheduler.
- Preserve a complete family as one ordered paired-sequence work unit. Represent native episode
  order, fresh sessions, persistence on/off conditions, state branch isolation, history anchors and
  native failure/aggregation semantics without platform-injected memory.
- Run only a bounded, model-free CPU engineering profile in this task. Any real Agent/model trial,
  credentials, network service, Docker or GPU acceptance requires a separately stated scope.
- Validate planning determinism, source/version checks, invocation freezing, queue/recovery
  compatibility, native output interpretation and paired evidence consistency.

## Changes

- Added the independently installable `agent-infra-past-bench` package pinned to PAST-Bench
  `f8223517ae7491e776b69793d9f11e9d074ab42e`, including explicit enablement, dependency lock,
  capability fixture and an SM01 request.
- Modelled one complete family as one `paired_sequence` with ordered episodes and isolated
  persistence on/off `StatePolicy` branches. Planning freezes the family, native config, Agent
  registry and installed runner digests.
- Added a native runtime that delegates session/history/state, grading and aggregation to the
  pinned PAST runner. Credentials use owner-only file references and never enter argv or Records.
- Added a model-free engineering profile using native manifest/state/aggregation primitives,
  result verification, native evidence archival and a disposable installed-wheel acceptance.
- Extended the generic native invocation with backward-compatible bounded log and artifact limits,
  allowing this family output to be captured without changing existing prepared-execution digests.
- Documented the implementation, operating flow, real-Agent prerequisites and limits; updated the
  architecture/status/navigation documents.

## Decisions

- Keep PAST protocol knowledge in `adapters/past-bench`; reuse the generic Benchmark SDK,
  ExecutionBackend, BM05-A queue/leases and Records paths.
- Let the pinned native family runner own episode ordering and state mechanics. The platform treats
  the family/pair as the atomic scheduled unit and imports child evidence rather than independently
  scheduling episodes.
- Treat the engineering profile as protocol evidence only. Real Agent combinations require a new
  capability claim and remain non-official; BM03 does not claim Docker sandbox equivalence.
- Keep original native failure handling. `infra_blocked` episodes are retained in evidence and are
  not silently retried or translated to a platform success.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git/context inspection | `7c74c0f8278fe6d8f63e213ce2e8cc4164db7eaf` | passed | Isolated stacked BM03 branch created. BM05-A remains unmerged/unpushed. |
| `PAST_BENCH_CHECKOUT=... pytest -q adapters/past-bench/tests/test_adapter.py tests/unit/benchmarks/test_execution.py tests/unit/runs/test_benchmark_execution.py` | final workspace | passed | 29 tests; planning/state/failure interpretation and generic capture-limit propagation. |
| Four pinned upstream PAST family/schema/order/no-persistence test files | upstream `f8223517...` + final workspace environment | passed | 114 tests; no model or external service. |
| `uv build && PAST_BENCH_CHECKOUT=... uv run --locked python scripts/acceptance/past_bench.py` | final workspace | passed | Built and installed independent wheels in a disposable venv; SM01 pair, state evidence, native aggregation, Records artifact and lease release passed. |
| Adapter/core Ruff checks | final workspace | passed | Adapter source/tests/acceptance and changed core files are formatted and lint-clean. |
| `make verify` | final workspace | passed | Import contracts, mypy, repository/doc links, 382 non-integration/e2e tests, Python wheel and Web production build passed; one existing Pydantic warning. |
| Real PAST Agent/model/judge or Docker sandbox | final workspace | not_run | Outside the approved model-free implementation scope; a real run needs an Agent choice, credentials, budget and a combination-specific capability claim. |

## Open items and blockers

- None for the approved model-free BM03 implementation. Real Agent quality, judge behavior,
  Docker sandbox equivalence and official submission remain later acceptance scopes.

## Next steps

- User review and integration in dependency order after BM05-A; do not start BM04 until requested.

## Compatibility and rollback

- The package is optional and explicitly enabled. Rollback removes its configuration/package and
  reverts the two optional invocation-limit fields; existing BM01 files keep their old canonical
  representation because default fields are omitted. Retained BM03 plans identify exact adapter,
  suite and upstream runner revisions but require that pinned package environment to execute.
