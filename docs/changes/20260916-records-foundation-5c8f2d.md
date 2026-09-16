---
record_version: 1
task_id: "20260916-records-foundation-5c8f2d"
title: "Implement the Records foundation and connect local runs"
branch: "feat/records-foundation"
base_commit: "11bfad18522c5dace7fbfb07cca888a0c394c7b3"
work_status: completed
updated_at: "2026-09-16T16:44:12+08:00"
pull_request: null
---

## Goal and acceptance

- Implement the R0-R3 Records foundation described by `docs/architecture/records-design.md`: typed public contracts, a durable local SQLite/CAS backend, idempotent events, streams, artifacts, manifests, queries, and trace reconstruction.
- Replace direct `LocalRunJournal` use with the Records API and connect Run lifecycle, Environment jobs/logs/submissions/cleanup, evaluations, and supported Agent native/normalized events.
- Add a first versioned Attempt-to-trajectory derivation and JSONL dataset export with explicit coverage and training eligibility so future Agentic-RL work has stable lineage.
- Preserve compatibility for existing `LocalRunJournal` callers while moving new runs to the new backend.
- Validate deterministic behavior with unit/contract tests and the real local Docker fixture when the host environment permits it. Host-managed external Agents, remote object storage, and multi-node spool transport remain separate capabilities because their execution transports do not yet exist.

## Changes

- Added backend-neutral Records contracts for manifests, scoped producer contexts, canonical events, streams, blobs, Artifacts, write receipts, queries, and Trace graphs.
- Implemented a local SQLite WAL metadata store and filesystem content-addressed blob store with schema versioning, atomic blob commits, idempotent events, retry-safe stream offsets, pagination, concurrent producers, and directory Artifact manifests.
- Replaced `LocalRunService` journal writes with Records lifecycle, task/policy snapshots, lease events, environment jobs, bounded stdout/stderr streams, Agent normalization, submissions, private evaluation, reward, credential cleanup, and final status records.
- Added a versioned Attempt trajectory builder, explicit training eligibility/limitations, private-evaluation filtering, terminal reward assignment, stable lineage, and JSONL dataset export manifests.
- Added local Records CLI commands for Run, Attempt, event, Artifact, trajectory, and export inspection.
- Added API/reference and implementation documentation, refreshed the Run reference and project overview, and retained `LocalRunJournal` only as a compatibility writer for direct legacy callers.

## Decisions

- Keep all Records runtime types and storage interfaces in the lower `records` layer; Run supplies scoped context and orchestration.
- Use the standard-library SQLite driver and filesystem content-addressed storage so the first backend adds no runtime dependency.
- Store observable messages and provider-native output only; do not synthesize hidden model reasoning.
- Use one central `state_dir/_records` store for cross-Run queries while retaining task-owned execution workspaces under each Run directory.
- Treat scorer streams and result Artifacts as evaluator-private; derive reward only from explicitly projected numeric `reward`/`score` or boolean `passed` feedback.
- Associate Attempt-level terminal rewards only with the final derived step. Mark missing token IDs/logprobs and capture truncation explicitly rather than claiming full RL eligibility.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | `feat/records-foundation` workspace at 2026-09-16T16:44:12+08:00 | passed | Ruff, formatting, import boundaries, mypy, Web checks, repository links/policy, 111 non-E2E tests, Python distributions and Web production build passed. |
| `uv run --locked pytest -q tests/e2e/test_run_environment.py -m e2e` | Same workspace | passed | Seven real local Docker cases passed in 41.39 seconds; no model, GPU or network was used. |
| `git diff --check` | Same workspace | passed | No whitespace errors were reported. |

## Open items and blockers

- None for the approved local Records scope. A real model Agent was not invoked, so provider-native normalization is covered by adapter fixtures and deterministic Run fixtures rather than paid model execution.
- Host/external Agent capture, resource time-series sampling, cross-process Worker spool, remote archival, HTTP authorization and training-framework-specific exporters remain separate follow-up capabilities because their transports or gateways do not yet exist.

## Next steps

- Review and merge this branch, then use the persisted events and manifests for durable resource queue/lease recovery before implementing multi-node Worker spool transport.

## Compatibility and rollback

- Existing `LocalRunJournal` remains available for direct legacy callers. New Runs use `state_dir/_records`; older per-Run `events.jsonl`/`result.json` directories are not automatically imported.
- `RunResult` adds the required `attempt_id` field, and callers that instantiate it positionally must update. Public Agent, Task, Environment and Resource contracts otherwise remain compatible.
- Rollback can restore Run's journal dependency and the prior `RunResult`; new SQLite/CAS directories can remain as inert evidence or be archived. No task input or external database is mutated.
