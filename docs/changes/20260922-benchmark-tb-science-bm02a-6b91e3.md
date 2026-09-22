---
record_version: 1
task_id: "20260922-benchmark-tb-science-bm02a-6b91e3"
title: "BM02-A: independent TB-Science adapter and managed native Harbor trials"
branch: "feat/benchmark-tb-science-bm02a"
base_commit: "3f76d722ef40d5c9fe6e5903bb9562c8ea94d920"
work_status: completed
updated_at: "2026-09-22T19:01:06+08:00"
pull_request: null
---

## Goal and acceptance

- Implement BM02-A only on the BM01 branch chain; no merge/push or later benchmark stages.
- An independent pinned TB-Science adapter maps original tasks without changing instructions,
  resource/network budgets, artifact transfer, separate verifier or native reward semantics.
- Extend generic execution/interpretation seams as necessary; never branch on benchmark name
  inside core. Native job identity, cleanup and CPU/memory limits must be verified before release.
- Preserve native raw logs/results/trajectories in Records; report execution, evaluation,
  protocol compatibility and cleanup separately. Compare original verifier on identical outputs.
- Validate unit/contract failures, external wheel installation, and a bounded real local Docker
  trial plus cancellation/cleanup. No paid model calls without a task-specific approved budget.

## Changes

- Added independent TB-Science and reusable pinned Harbor runtime packages, CLI native opt-in,
  native backend validation/interpretation extension, and backward-compatible cancellation grace.
- Added native identity/ownership, per-service CPU/memory attestations, separate verifier,
  bounded raw/structured logs and ADMIN artifacts; positive Docker cleanup before slot release.
- Added operation and implementation guides plus repeatable real Docker acceptance script.
- Initial native verifier attempt rejected strict resource mode with unspecified verifier values;
  corrected to preserve native auto policy and explicitly enforce defaults in Docker overlay.
- Second attempt hit Docker Hub timeout and incomplete pre-build Compose cleanup. Corrected
  absent-object teardown; imported the exact upstream OCI digest through the previously supplied
  proxy without changing Docker daemon configuration or benchmark files.
- Wheel-installed CLI trial succeeded: Run `ab8c66f3fd3e4bf7859ed2c919532d74`, native trial
  `75c4bc79-c0e1-44c4-b685-b3a46c5c7e79`, reward 1.0, complete capture and confirmed cleanup.
  This is native Oracle engineering evidence, not model performance.

## Decisions

- Local upstream checkout is read-only; its untracked `my_doc/` belongs to the user.
- [Stage plan](../development/benchmark-development-plan.md),
  [BM01](20260922-benchmark-execution-bm01-a4f8d2.md).
- Exact native versions and actual execution budgets will be recorded before acceptance runs.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git/context inspection | `3f76d72` | passed | Clean BM01 branch; isolated BM02-A task branch created. |
| `make verify` | final core workspace; code diff digest below | passed | 375 tests; lint, format, strict mypy, import direction, documentation, TypeScript checks and both builds. One existing Pydantic warning. |
| `uv run --locked pytest -q tests/integration/test_managed_process.py tests/unit/benchmarks/test_tb_science.py` | BM02-A workspace | passed | 18 checks, including 9 real-process checks; no Docker/models. |
| Runtime Python `-m pytest -q adapters/harbor-runtime/tests` | final installed runtime wheel | passed | 4 checks: namespace collision, pending create cancellation, unknown create quarantine, all-environment cleanup. |
| `ruff check src tests scripts adapters`, format, `mypy`, `lint-imports --no-cache`, `scripts/ci/check_repository.py` | final workspace | passed | Core and optional package lint; dependency graph kept, policy mirrors unchanged. |
| `uv build` core + both adapters; `uv pip install --no-deps .../*.whl` in dedicated runtime | final wheel installation | passed | Non-editable independent packages; pinned Harbor installed from Git dependency lock. CLI plan/prepare/run/status used these wheels. |
| `uv run --locked python scripts/ci/smoke_wheel.py` | built core wheel | passed | Fresh environment CLI smoke. |
| `scripts/acceptance/benchmark_tb_science.py --allow-docker --source <pinned symbolic-regression> --output /tmp/agent-infra-bm02a-hardened --config adapters/tb-science/adapters.toml --capabilities adapters/tb-science/capabilities.json --request adapters/tb-science/request.json` via runtime Python | final installed wheels; raw evidence below | passed | Platform native trial + direct Harbor same-output regrade both reward 1.0; source artifacts unchanged; duplicate submission no restart; cancel after real container start released slot with positive cleanup. Zero model calls. |
| Docker read-only owned-label/container/network/volume checks | final native receipts | passed | No task-owned residual containers; per-project queries also confirmed no networks/volumes. Unrelated containers/services were not stopped or restarted. |
| Initial direct `.venv/bin/pytest` full-suite invocation | development workspace | failed | 17 checks could not find `agent-infra`/`lint-imports` on PATH. Corrected invocation to `uv run --locked`; subsequent full checks passed, no test weakened. |
| Initial native trials | pre-fix development wheels | failed | Unspecified verifier resources and Docker Hub/pre-build cleanup failures described above; fixed and final real acceptance passed. |
| Nop real execution / paid model Agent / GPU / other benchmark profiles | None | not_run | Not part of this profile; do not claim model or complete benchmark-suite acceptance. |

### Reproducible evidence

- Final source snapshot: SHA256 `3c157d971f4cdd7839a363cd40e7e12942707d82cd6234932907a21b318bb53c`
  of `git diff 3f76d722ef40d5c9fe6e5903bb9562c8ea94d920 -- src tests scripts adapters`.
  Documentation-only finalization does not change this code snapshot.
- Final platform Run `d6e16edad2e64767b0ae77bfd4cd7619`; cancelled Run
  `249417c39d9c44f48909f87455898d0c`.
- Local, unversioned evidence: `/tmp/agent-infra-bm02a-hardened/acceptance.json`, platform Records,
  `native-regrade/`, native result/cleanup/attestation files. These are disposable validation data,
  not a promised production backup. No benchmark data/solutions/logs were committed.
- Regraded submission tree digest: `sha256:46b379ed9b8aef1475cc2ae1d435e5d4b55573e17ffad4a91299118324841353`.
- Main solver/verifier containers each verified at 1e9 NanoCpus / 2147483648 bytes;
  verifier network sidecar 1e8 NanoCpus / 134217728 bytes. Sequential phases, no GPU.
  Container runtime limits do not bound image building or disk usage. Each acceptance operation
  had a 20-minute observation deadline, then scoped cancellation.

## Open items and blockers

- None for BM02-A's CPU single-task native Oracle/Nop engineering profile.
- Model Agent compatibility, full suite coverage, global numeric leases/queues, GPU, multi-service
  tasks, large-artifact transfer and leaderboard submission remain explicitly outside this stage.
- Early development failure state remains under `/tmp/agent-infra-bm02a-acceptance`; one old
  trial is conservatively quarantined after its pre-fix cleanup failed. Read-only Docker checks
  found no remaining task-owned containers. Final acceptance uses fresh isolated state; no
  receipt was fabricated and no old execution was silently relaunched.

## Next steps

- User reviews BM02-A. Do not begin BM02-B or merge/push without the next instruction.

## Compatibility and rollback

- Keep BM00 planning and BM01 managed-process interfaces backward compatible.
- Never discard unknown native jobs or release resources before scoped cleanup evidence.
