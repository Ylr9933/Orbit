---
record_version: 1
task_id: "20260915-task-model-3a91bf"
title: "Model tasks, visibility and benchmark-preserving imports"
branch: "docs/task-model"
base_commit: "99dbd1ad23a30b8dabaac4529e166bc20fd506ce"
work_status: completed
updated_at: "2026-09-15T20:02:39+08:00"
pull_request: null
---

## Goal and acceptance

- Design a practical task abstraction covering tools, resource intent, instructions, supplied data,
  user context and private evaluation, with an extensible material manifest.
- Explain research-task completion and benchmark conversion without inventing native requirements.
- Ground examples in local ASI-Bench and ResearchClawBench code; mark all new interfaces as proposals.

## Changes

- Added `docs/architecture/task-model.md` with the task definition, solver view, execution plan,
  material manifest, tool/resource integration, hidden evaluation boundaries and import examples.
- Added a documentation navigation entry. Project overview unchanged: no capability was implemented.

## Decisions

- Branch directly from main; the previous implementation-guides branch remains independent.
- Keep task parsing deterministic and provider-neutral. Agent-assisted authoring is a separate flow.
- Preserve native benchmark semantics and distinguish runtime choices from source requirements.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Local source inspection | infra `99dbd1a`; ASI-Bench `38ab4b5`; ResearchClawBench `b76fdec` | passed | Reviewed task loading, workspace construction, Agent contracts and resource boundaries. |
| `uv run --locked python scripts/ci/check_repository.py`; `git diff --check` | Documentation workspace based on `99dbd1a`, 2026-09-15T20:02:39+08:00 | passed | Policy mirrors and local links passed; no whitespace errors. |
| Manual source/design reconciliation | Same workspace | passed | Native generated instructions, prompt variants, evaluation visibility and missing-field semantics are explicit; proposed tool interfaces are not presented as implemented. |

## Open items and blockers

- None for the design scope. Runtime contracts, adapters and compatibility tests remain future work.

## Next steps

- User reviews the proposal before choosing the implementation scope.

## Compatibility and rollback

- Documentation only. Existing contracts and source benchmarks remain unchanged; revert this task's
  commit to remove the proposal and its navigation link.
