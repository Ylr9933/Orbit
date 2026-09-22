---
record_version: 1
task_id: "20260922-benchmark-asi-bm02b-4d2c81"
title: "BM02-B: independent ASI-Bench adapter and native scoring boundaries"
branch: "feat/benchmark-asi-bm02b"
base_commit: "e85b95add3565b63465df57646b285b04540da96"
work_status: completed
updated_at: "2026-09-22T20:31:40+08:00"
pull_request: null
---

## Goal and acceptance

- Implement BM02-B only after locally integrating BM00, BM01 and BM02-A into `main`.
- Add an independent, pinned ASI-Bench adapter package without benchmark-name branches in core.
- Preserve seed, prompt level, task/instance IDs, native produce-only evidence and attempt status.
- Run public seed31415 scoring through ASI-Bench's native BenchFlow contract and keep its
  non-official score separate from execution and submission state.
- Describe and validate seed42 OS-Docker provenance and local bundle eligibility without reading
  private references, authenticating, uploading or claiming an official score.
- Validate package isolation, deterministic re-scoring, cancellation/cleanup and a bounded CPU
  native trial. Do not call a paid model or use a GPU for engineering acceptance.

## Changes

- Fast-forwarded the linear BM00/BM01/BM02-A chain into local `main`, then created this branch.
- Added `adapters/asi-bench` as an independently installable package pinned to ASI-Bench commit
  `38ab4b5364f1fde5515fef7e9210ff3c9db6a2ba`, with explicit enablement, capability profile,
  dependency lock, immutable planning, a native backend and bounded evidence collection.
- Implemented one public seed31415 produce-only attempt through the native CLI and scoring through
  ASI-Bench's schema-v2 BenchFlow API. Native task/instance/prompt identities and attempt status
  are verified before the non-official score is interpreted.
- Added a seed42 local bundle command which delegates provenance and seed validation to ASI-Bench,
  disables archive/upload behavior, and never returns an official score.
- Added the maintainer implementation guide, bounded operations guide, documentation navigation
  and proposed project status update.

## Decisions

- Treat the user's ASI-Bench checkout as read-only. Its modified `.gitignore` and untracked
  `my_md/` files are unrelated user work and will remain untouched.
- Use ASI-Bench's public BenchFlow boundary for materialized seed31415 attempts instead of
  duplicating scorers or reference-generation code in Agent Infra.
- Keep local seed31415 scores, seed42 bundle eligibility, authenticated submission and official
  scores as distinct states and evidence.
- Collect only explicit result/evidence paths. ASI-Bench's native output contains a temporary
  workspace symlink; including the whole tree would make evidence collection unsafe and brittle.
- The BM02-B engineering profile is intentionally model-free and uses `--sandbox none`. Its local
  score proves contract wiring only and cannot be used as a leaderboard result.
- Related design: [benchmark stages](../development/benchmark-development-plan.md),
  [integration layer](../architecture/benchmark-integration-layer.md),
  [BM02-A](20260922-benchmark-tb-science-bm02a-6b91e3.md).

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git integration and branch isolation | `e85b95add3565b63465df57646b285b04540da96` | passed | BM00/BM01/BM02-A were a linear five-commit fast-forward from local `main`; development moved to this task branch. No push performed. |
| ASI-Bench source inspection | upstream `38ab4b5364f1fde5515fef7e9210ff3c9db6a2ba` | passed | Confirmed package version 0.1.5, schema-v2 BenchFlow scorer, seed31415 local/non-official policy and seed42 OS-provenance submission validation. |
| Package tests and process isolation: `pytest -q adapters/asi-bench/tests/test_adapter.py tests/integration/test_managed_process.py` | BM02-B workspace after implementation | passed | 18 checks; seed42 policy, score interpretation, durable process behavior, cancellation and an unrelated process surviving owned cleanup. No model/GPU. |
| Core benchmark regression: `pytest -q tests/unit/benchmarks tests/unit/runs/test_benchmark_execution.py` | BM02-B workspace after implementation | passed | 62 checks. |
| Pinned lock install and package build | BM02-B workspace after implementation | passed | Wheel/sdist built; clean Python 3.12 venv installed 73 locked ASI dependencies from the pinned Git commit plus both local packages; imported ASI-Bench 0.1.5. |
| Real platform CPU trial: plan/check/prepare/run/status | Run `3a3bb2b393964473a2fe5e7a20c214ff`, attempt `attempt_2748a083272b4a119a73130a455f5327` | passed | Official public instance `math.sigma_linear_diophantine__seed31415`, b1, frozen public scorer policy, native fixture; execution completed, native local score 0.0/100 with `official=false`, protocol valid, evidence complete, owned process-group cleanup confirmed. No model/GPU/upload. |
| Documentation and source checks: Ruff, `scripts/ci/check_repository.py`, `git diff --check` | BM02-B workspace after implementation | passed | Python style, policy parity and local documentation links passed. |

## Open items and blockers

- None for the approved model-free, single-public-instance BM02-B engineering profile.
- Real Agent execution, OS Docker isolation, GPU, whole-suite runs, authenticated submission and
  official scoring remain later compatibility/acceptance profiles rather than BM02-B blockers.

## Next steps

- User reviews BM02-B. Do not begin BM05-A or any later stage without the next instruction.

## Compatibility and rollback

- Existing benchmark SDK and TB-Science package must remain compatible.
- No core public contract changed. Existing SDK, BM01 and TB-Science behavior remains unchanged.
- Removing the independent adapter package and its enablement configuration rolls back ASI support;
  native run artifacts remain external to the repository. Local state can be retained as evidence
  or deleted by the operator after review.
