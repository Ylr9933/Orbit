---
record_version: 1
task_id: "20260915-task-implementation-a71e40"
title: "Implement task definitions, visibility and authoring"
branch: "feat/task-model"
base_commit: "8b95188331c06d8d31e3d6ca9efd310ffb1af68e"
work_status: in_progress
updated_at: "2026-09-15T20:17:22+08:00"
pull_request: null
---

## Goal and acceptance

- Implement the task-model proposal: deterministic versioned manifests, provenance, material
  validation, safe solver views, research authoring, resource-plan validation and benchmark imports.
- Validate missing-field semantics, private-material exclusion, stable snapshots and native source
  preservation with executable fixtures and CLI paths.
- Track tool injection, native evaluator equivalence and real isolation separately: Environment,
  Run and Records runtimes are absent in the starting repository.

## Changes

- Added immutable Tasks contracts, strict versioned YAML, source provenance, missing states,
  relative-path validation, content snapshots and solver-only material projection/copying.
- Added draft creation/review and traceable proposals that cannot replace supplied facts; connected
  resource YAML checks to task bounds without allocating or rewriting task requirements.
- Added native-prepared workspace indexing for ResearchClawBench and selected ASI-Bench prompt
  levels, explicitly labeled indexed_only; native evaluators are not substituted.
- Added explicit evaluator registration and snapshot verification, plus an exact-text fixture scorer.
- Added task CLI commands, two small task packages, regression tests, reference documentation and
  proposed project-status update. The broader design remains in_progress.

## Decisions

- Build on the design branch so its proposal accompanies the implementation.
- Do not execute arbitrary benchmark source during manifest loading or invent unavailable data.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Repository inspection | `8b95188` | passed | Clean task-design branch; Tasks, Run and Environment are scaffolds. |
| `make check`; `make test` | Workspace based on `8b95188`, 2026-09-15T20:17:22+08:00 | passed | All static/dependency/policy/link checks and 90 deterministic tests passed. Includes private canaries, source mutation, symlinks, traversal, prompt selection, draft provenance, resource violations and evaluator failure versus wrong answer. |
| `agent-infra task validate/view/freeze` through `uv run --locked` | Same workspace | passed | Both checked-in examples parse; solver JSON excludes evaluator/source metadata; snapshot emits content fingerprints. |
| `make build`; `uv run --locked python scripts/ci/smoke_wheel.py` | Workspace after the 90-test run, before the final draft-review adjustment | passed | Python wheel/sdist and Web build succeeded; isolated wheel imports and CLI smoke passed. |
| `uv run --locked pytest tests/unit/tasks tests/unit/test_cli.py -q` | Workspace after draft review distinguishes native missing fields from research clarification | passed | 30 task/CLI tests passed. |
| Real authoring model, MCP injection, native evaluator equivalence and OS isolation | Same workspace | not_run | Their runtime integration is not yet implemented. Fixture checks do not establish these capabilities. |

## Open items and blockers

- The deterministic Tasks foundation is implemented and validated, but the full approved design is
  not complete. Automatic model-driven authoring, actual tool injection, native generation/evaluation
  adapters and end-to-end isolation need subsequent implementation and real-environment validation.
- TaskSection currently supports a documented subset of proposed fields. Native extensions are
  preserved, but unsupported semantics must be handled by explicit adapters before execution.

## Next steps

- Connect the authoring workflow and Environment/Agent ToolBinding, then validate a fixed native
  benchmark adapter against original workspace and evaluation output before claiming compatibility.

## Compatibility and rollback

- Additive task APIs and CLI; no migration of existing state or modification of source benchmarks.
