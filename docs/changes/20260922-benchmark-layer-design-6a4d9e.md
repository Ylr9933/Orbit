---
record_version: 1
task_id: "20260922-benchmark-layer-design-6a4d9e"
title: "Design benchmark integration layer for ASI-Bench and TB-Science"
branch: "docs/benchmark-integration-design"
base_commit: "57c8e4da0a9774cd149715424ee172aa143760ef"
work_status: completed
updated_at: "2026-09-22T14:35:17+08:00"
pull_request: null
---

## Goal and acceptance

- Specify an implementable Benchmark layer for ASI-Bench, TB-Science and later adapters.
- Preserve native execution, evaluation, visibility, provenance and submission rules.
- Distinguish current code from proposed interfaces and break the work into testable milestones.

## Changes

- Added `docs/architecture/benchmark-integration-layer.md` as a design proposal.
- Added a documentation navigation entry. Product capabilities and project status are unchanged.

## Decisions

- Start with native-runner-managed execution to preserve upstream behavior and ownership.
- Keep batch orchestration and resource admission in Agent Infra, but require proof of child-container enforcement.
- Treat local score, official score, execution and cleanup as separate facts.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Official docs and local code review | Documentation branch from `57c8e4d` | passed | Reviewed ASI-Bench and TB-Science/Harbor official docs; compared current Tasks, Run, Resources, Records code. No native benchmark run. |
| `uv run --locked python scripts/ci/check_repository.py` | Documentation branch working tree, 2026-09-22T14:35:17+08:00 | passed | Policy mirrors and local Markdown links passed. |
| `git diff --check` | Same working tree | passed | No whitespace errors. |
| `git fetch origin --prune`; `git fetch zjunlpgit --prune`; `git branch -a --no-merged main` | Base `57c8e4d`, before creating this task branch | passed | No local or remote branches unmerged into main; both remote mains match local main. |

## Open items and blockers

- None for the document scope. All proposed runtime interfaces and native adapters remain unimplemented.

## Next steps

- User reviews the design; implement B0 in a separate task after scope is selected.

## Compatibility and rollback

- Documentation only. No runtime contract or dependency changes; revert this documentation commit if the proposal is declined.
