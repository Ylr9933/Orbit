---
record_version: 1
task_id: "20260923-benchmark-integration-cleanup-4e9b62"
title: "Review benchmark integration, prevent ambiguous native resubmission, and integrate branches"
branch: "refactor/benchmark-integration-cleanup"
base_commit: "5776abc224f7d298d927712dfd791d29f0ae8e8f"
work_status: completed
updated_at: "2026-09-23T09:56:38+08:00"
pull_request: null
---

## Goal and acceptance

- Review the current repository for concrete maintenance problems in the newly added benchmark path.
- Prevent a second HTCondor submission when the first submit outcome is ambiguous; preserve exact
  native ownership and conservative recovery semantics.
- Validate affected code and integrate the local BM05-A, BM03 and BM04 dependency chain. Publish
  the resulting `main` to both configured remotes and verify their target revisions.

## Changes

- PostTrainBench HTCondor backend now retains its submit intent and refuses automatic resubmission
  when a submit file exists but no native job ID can be recovered. This closes the ambiguous reply
  window that could launch two expensive training jobs.
- Added a scheduler fault-window regression and removed a redundant terminal status expression.
- Reconciled the project overview and current benchmark documentation for the planned integration;
  historical task records retain their original branch-time evidence.

## Decisions

- Keep the cleanup scoped to evidenced problems in the benchmark execution path. Independent
  adapter packages and benchmark-native policies retain their existing ownership boundaries.
- A missing scheduler row is insufficient proof that `condor_submit` did not launch a job. Keep the
  existing operation quarantined until an operator can verify the cluster history and ownership.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git branch/remote inspection | `5776abc224f7d298d927712dfd791d29f0ae8e8f` | passed | Three local branches form one linear chain; both remote `main` refs are `6dc5580`. |
| Adapter/Core/Run focused tests | final task branch workspace | passed | 33 tests, including an ambiguous submit reply and assertion that only one scheduler submit occurs. |
| Adapter Ruff, format and strict mypy | final task branch workspace | passed | Seven checked Python files; six source modules type-clean. |
| `make verify` | final task branch workspace | passed | Import contracts, core mypy, Web typecheck, policy/links, 383 tests, Python/Web builds passed; 32 tests deselected and one existing Pydantic warning. |
| Final staged diff review | final task branch workspace | passed | `git diff --cached --check` clean; staged files are limited to benchmark backend/test, current docs, and this record; no credential values found. |

## Open items and blockers

- None for code and validation. Git integration and publishing remain the next action.

## Next steps

- Merge the linear BM05-A → BM03 → BM04 → cleanup chain through the repository review flow; then
  synchronize both configured remotes and verify their `main` refs.

## Compatibility and rollback

- No public contract or stored schema changed. Existing ambiguous native submissions remain
  recoverable by scheduler identity query but are not automatically resubmitted. Reverting this
  guard restores the duplicate-job risk; retain it while native HTCondor mode is supported.
