---
record_version: 1
task_id: "20260922-benchmark-layer-design-6a4d9e"
title: "Design extensible benchmark execution and optimization protocols"
branch: "docs/benchmark-integration-design"
base_commit: "57c8e4da0a9774cd149715424ee172aa143760ef"
work_status: completed
updated_at: "2026-09-22T15:05:16+08:00"
pull_request: null
---

## Goal and acceptance

- Specify an implementable Benchmark layer for ASI-Bench, TB-Science and later adapters.
- Preserve native execution, evaluation, visibility, provenance and submission rules.
- Distinguish current code from proposed interfaces and break the work into testable milestones.
- Extend this unmerged proposal to PostTrainBench and PAST-Bench, covering long training,
  ordered stateful episodes, backend-neutral execution, trace evidence and bounded optimization.

## Changes

- Added `docs/architecture/benchmark-integration-layer.md` as a design proposal.
- Added a documentation navigation entry. Product capabilities and project status are unchanged.
- Revised the unmerged proposal to v0.2 with four benchmark mappings, execution handles,
  phase/sequence state and feedback policies, resource ownership, artifact lineage and bounded campaigns.
- Added the proposed [protocol/execution ADR](../adr/20260922-benchmark-protocol-execution.md).
- Replaced B0–B4 labels with BM00–BM07 to avoid confusion with delivered research planning work.

## Decisions

- Start with native-runner-managed execution to preserve upstream behavior and ownership.
- Keep batch orchestration and resource admission in Agent Infra, but require proof of child-container enforcement.
- Treat local score, official score, execution and cleanup as separate facts.
- Review feedback expands the same unmerged design task; preserve native feedback, retry,
  persistence and aggregation semantics rather than assume independent one-shot tasks.
- Keep domain contracts in public domain APIs; Run translates benchmark plans to lower-level
  execution specs to avoid a dependency cycle. One queue and one allocation owner per job.
- Do not assume PostTrainBench main has Harbor support or safe shared-host cleanup; review its
  pinned HPC pipeline and identify the open Harbor PR as experimental.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Official docs and local code review | Documentation branch from `57c8e4d` | passed | Reviewed ASI-Bench and TB-Science/Harbor official docs; compared current Tasks, Run, Resources, Records code. No native benchmark run. |
| `uv run --locked python scripts/ci/check_repository.py` | Documentation branch working tree, 2026-09-22T14:35:17+08:00 | passed | Policy mirrors and local Markdown links passed. |
| `git diff --check` | Same working tree | passed | No whitespace errors. |
| `git fetch origin --prune`; `git fetch zjunlpgit --prune`; `git branch -a --no-merged main` | Base `57c8e4d`, before creating this task branch | passed | No local or remote branches unmerged into main; both remote mains match local main. |
| Official fixed-source and implementation review for v0.2 | PostTrainBench `3ed1d32`; PAST-Bench `f822351`; infra `7841d23` | passed | Inspected native prompt, judges, runtime script, sequence schema, public paper and PR #8; checked local allocator, Planner, iteration and Records contracts. |
| `uv run --locked python scripts/ci/check_repository.py`; `git diff --check` | v0.2 documentation workspace based on `7841d23`, 2026-09-22T15:05:16+08:00 | passed | Local Markdown links/policy mirrors and whitespace checks passed; manually reconciled interfaces and dependency direction. |
| Real benchmark / Docker / GPU / model execution | None | not_run | Design-only scope; no runtime implementation or native equivalence claimed. |

## Open items and blockers

- None for the document scope. All proposed runtime interfaces and native adapters remain unimplemented.

## Next steps

- User reviews v0.2; implement BM00/BM01 in separate tasks, then the four protocol-specific validations.

## Compatibility and rollback

- Documentation only. No runtime contract or dependency changes; revert this documentation commit if the proposal is declined.
