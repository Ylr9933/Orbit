---
record_version: 1
task_id: "20260923-benchmark-posttrain-bm04-7b2e91"
title: "BM04: independently packaged PostTrainBench training adapter"
branch: "feat/benchmark-posttrain-bm04"
base_commit: "5793d663458f16b652e460cc2b51fef3a4b5e6fa"
work_status: completed
updated_at: "2026-09-23T09:42:57+08:00"
pull_request: null
---

## Goal and acceptance

- Implement PostTrainBench as an optional independent adapter pinned to the reviewed upstream
  revision, without benchmark-name branches in the core scheduler.
- Preserve the native task, training budget, solver/public-evaluation/final-model/judge boundaries,
  and separate engineering evidence from official-compatible evidence.
- Add the minimum reusable execution/storage contracts required for scoped GPU allocation,
  immutable final-model handoff and bounded large-artifact references.
- Validate with a bounded model-free engineering profile. Real H100, model Agent, HTCondor,
  Apptainer and judge execution require a separately declared resource and cost scope.

## Changes

- Added an independently installable PostTrainBench adapter pinned to upstream revision
  `3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1`, with explicit enablement, dependency lock,
  engineering request and capability fixture.
- Modelled one evaluation task as one native training job. The frozen plan preserves the solver's
  public evaluation feedback, target-model identity, training/resource budget, private judges,
  final evaluation and native retry ownership.
- Added a dual execution backend: model-free engineering runs use the managed process backend;
  native runs create a scoped HTCondor job with durable intent, operation ClassAd, native job ID,
  recovery queries, bounded logs, exact-ID cancellation and terminal cleanup attestation.
- Added content-addressed final-model handoff with symlink/special-file rejection, size budget,
  per-file hashes, copy verification, atomic publication, idempotent recovery and a bounded Records
  evidence view for metrics, traces, monitoring and judge verdicts.
- Extended the generic benchmark execution timeout ceiling from one day to seven days for bounded
  external long jobs; the research Controller retains its separate one-day policy.
- Added implementation/operation documentation and updated the architecture, status and navigation.

## Decisions

- Build BM04 on the stacked BM05-A/BM03 branch so long-running jobs use durable queue/lease
  semantics. Preserve the dependency chain explicitly until integration.
- Refuse native local-process execution. The pinned upstream final evaluation kills GPU processes
  visible to its job, so native mode requires scheduler-enforced GPU visibility isolation.
- Keep model weights outside ordinary Records blobs. Records stores a content manifest and stable
  private filesystem reference; remote replication and object storage remain later work.
- Keep raw accuracy, judge eligibility and official submission state separate. Engineering output
  is protocol evidence only and can never be score-eligible.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git/context inspection | `5793d663458f16b652e460cc2b51fef3a4b5e6fa` | passed | Isolated stacked BM04 branch; BM05-A and BM03 remain unmerged/unpushed. |
| Adapter Ruff and standalone mypy | final workspace | passed | Six adapter source modules are format-, lint- and type-clean. |
| Adapter tests | final workspace + pinned upstream checkout | passed | 7 tests cover planning boundaries, tracked-only stable protocol digests, immutable/idempotent handoff, native ID recovery, exact cancellation, scheduler cleanup and collection. Scheduler commands are deterministic test doubles; no GPU/model. |
| Focused adapter/core/Run tests | final workspace | passed | 31 tests, including multi-day timeout compatibility and benchmark Run recovery. |
| `POSTTRAIN_BENCH_CHECKOUT=... .venv/bin/python scripts/acceptance/posttrain_bench.py` | final workspace | passed | The script built and installed independent wheels in a disposable venv; prompt, judge evidence, model handoff, Records and lease release passed. |
| Fixed upstream source checks | upstream `3ed1d32...` | passed | Reviewed native prompt, task schema, run script, HTCondor description, result/judge aggregation and compiled selected Python entrypoints. Upstream revision has no repository test files in the inspected scope. |
| `make verify` | final workspace | passed | Import contracts, core mypy, repository/doc links, 383 non-integration/e2e tests, Python wheel and Web production build passed; one existing Pydantic warning. |
| Real HTCondor/H100/Apptainer/Agent/judges | final workspace | not_run | Requires a cluster with verified GPU visibility isolation, shared storage, images, credentials and an explicit compute/model budget. |

## Open items and blockers

- None for the approved model-free BM04 implementation. Real native acceptance is blocked on the
  required external cluster/resources and separate authorization, not on the engineering profile.

## Next steps

- User review and integration after BM05-A/BM03; do not start BM05-B until requested.

## Compatibility and rollback

- The adapter is optional and explicitly enabled. Removing its package/config disables new runs;
  retained plans still identify exact source/runner/model contracts. Reverting the generic timeout
  extension restores the one-day execution-spec ceiling and makes prepared multi-day BM04 files
  unreadable, while existing shorter benchmark files remain compatible. Model snapshots are
  external data and require an explicit storage-retention decision during rollback.
