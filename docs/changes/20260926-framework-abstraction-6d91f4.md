---
record_version: 1
task_id: "20260926-framework-abstraction-6d91f4"
title: "Review framework simplicity and benchmark extension boundaries"
branch: "docs/framework-abstraction"
base_commit: "b7079f4c3226460639104186bddb38131dd6b216"
work_status: completed
updated_at: "2026-09-26T17:29:33+08:00"
pull_request: null
---

## Goal and acceptance

- Write a detailed Chinese architecture review named `0926-1717-xxx` explaining how stable
  interfaces let separately implemented adapters run and monitor different benchmarks.
- Audit current public contracts, execution, observations, results and module boundaries;
  distinguish delivered capabilities, limitations and proposed changes.
- Recommend a minimal extension surface, a Codex adapter-authoring workflow, concrete
  acceptance checks and an incremental simplification plan without changing native protocols.
- Documentation only; no runtime, API, dependency, governance or deployment changes.

## Changes

- Added [0926-1717 architecture review](../architecture/0926-1717-benchmark-abstraction-and-framework-review.md)
  with 12 sections covering the current SDK, five monitoring layers, module responsibilities,
  typed results and optional observations, 12 source-grounded gaps, Codex authoring guidance,
  conformance scenarios and a three-step migration proposal.
- Added a documentation-map entry. Project overview unchanged: no capability, milestone or
  approved roadmap changed.

## Decisions

- Use an isolated sibling worktree based on integrated local `main` at `b7079f4`.
- Read the separate TB-Science branch at `99c8450` as supplementary evidence only, not as
  integrated capability. The previous needs report at `da59eb4` informs scope without being merged.
- Extend the existing SDK/backend boundaries instead of proposing a second adapter framework.
- Keep native scoring, atomic units, visibility, clocks and retry rules intact. Separate common
  execution facts from benchmark-specific semantics; observation coverage may be partial.
- Reconcile the ASI-only trajectory finding with the unmerged TB generalization. Highlight
  result/backend coupling, private extension dependencies and separate resource-admission domains.
- Consult official Harbor, Inspect and OpenTelemetry documentation for narrow comparisons,
  without installing them or adopting their policies as repository requirements.
- Do not change the project overview for an unapproved architecture proposal.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Repository status, policy, task records and source inspection | `b7079f4`; supplementary `99c8450` | passed | Separate worktree created; other task branches and runtime state untouched. |
| Source-to-claim audit of public interfaces, runtime, adapters, read models and resource composition | `b7079f4`, with `99c8450` trajectory diff | passed | Static evidence only; distinguishes integrated code, unmerged changes, desired semantics and proposed fields. Existing runtime test cases were inspected, not rerun. |
| `python3 scripts/ci/check_repository.py` | Report SHA-256 `5661e3834eb90aa6a09acc43815503a66e47d8640b8aeb1bfbf7d9680d0f964f`, navigation update | passed | Policy mirrors and local Markdown file links pass. |
| Inline Python document structure audit | Same report SHA-256 | passed | Requested filename; 12 numbered sections; 13 consistent tables; balanced code fences; three official source links reviewed through browsing. Mermaid was reviewed as source, not browser-rendered. |
| `git diff --cached --check` and staged diff review | Final documentation workspace | passed | Documentation-only scope; no runtime/configuration changes, generated outputs or credentials included. |
| Model/Docker/GPU/benchmark execution | Documentation-only scope | not_run | No runtime behavior or protocol equivalence claimed. |

## Open items and blockers

- None for the requested architecture document. Implementation, adapter conformance tooling,
  shared admission and real-environment checks are proposals outside this task.

## Next steps

- None within the authorized documentation scope. Local task-branch review is ready;
  publishing, PR creation and merging were not requested.

## Compatibility and rollback

- Documentation only; no runtime compatibility or state migration impact. Revert the new report
  and navigation change if superseded. No publishing or merging requested.
