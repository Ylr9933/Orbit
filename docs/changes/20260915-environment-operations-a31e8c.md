---
record_version: 1
task_id: "20260915-environment-operations-a31e8c"
title: "Answer environment automation, cluster setup, trace, and execution-mode questions"
branch: "docs/environment-operation-design"
base_commit: "362a7ae25500d741c1e7dee33c5eec3ea30b83b1"
work_status: completed
updated_at: "2026-09-15T10:49:17+08:00"
pull_request: null
---

## Goal and acceptance

Record and answer the user's four pre-development questions in Chinese: natural-language environment preparation, Ray resource coordination and beginner-friendly cluster initialization, trace persistence including tool results, and host-agent versus container-agent execution. Inspect ASI-Bench and primary technical documentation. Distinguish existing architectural coverage, new proposals, and unverified implementation requirements.

## Changes

- Added the Chinese [environment and operations Q&A](../architecture/environment-operations-qa.md), recording all four questions, existing coverage, proposed workflows, module ownership, and acceptance evidence needed from implementation.
- Linked the Q&A from the README and module proposal; updated the project overview's design outcomes, gaps, and priorities without advancing any implementation milestone.
- Preserved code, configuration, prior task records, and development rules.

## Decisions

- Retain the eight top-level modules and assign new preparation and operational workflows within those boundaries.
- Treat ASI-Bench as `apexin-ai/ASI-Bench` for this investigation, explicitly stating that identification in the document.
- Use a new branch based on the existing, locally unmerged module-design work; preserve its task record.
- Generate a deterministic, editable environment recipe before building; separate preparation validation and bounded repair from formal execution.
- Distinguish hardware, authorized capacity, logical allocations, and measured usage. Plan independent node services, local occupancy checks, and repeatable onboarding tools.
- Retain normalized events alongside native traces and tool output artifacts, with explicit capture coverage and durable archival boundaries.
- Support both external MCP-mediated execution and container-managed agents. For ASI-Bench, preserve the native protocol and validate actual resource mapping and provenance before claiming compatibility.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Read rules, project status, task history, Git state, and design sources | Base commit `362a7ae` | passed | Clean task branch before changes; created a dedicated follow-up branch. |
| Primary-source investigation and manual design consistency review | Documentation snapshot below; ASI-Bench `a797bf69683400bed0f38c4add507bb3d404b833` | passed | Read Ray, Docker, NVIDIA, and MCP official documentation; read ASI-Bench's pinned guide, README, and relevant Docker execution code. Verified the `--gpus all` integration concern directly in `os_sandbox.py`; retained source links and separated observations from recommendations. No runtime compatibility is inferred from this review. |
| Python Markdown/link/scope audit and `git diff --check`, including no-index whitespace checks for new documents | Documentation snapshot below plus this task record | passed | Checked five task files, relative links, fences, table widths, seven Q&A sections, and expected change scope. No source/configuration files changed. Diagrams were reviewed as text, not rendered in a browser. |
| Real Docker, Ray, Agent, or benchmark execution | Documentation task | not_run | No installation or runtime implementation is authorized or claimed in this task. |

Documentation snapshot: `b6fb3c2d36a7a30f4955c3e112cb4a787a9c1ee44fddfa54f2aea45a97d564c7`. Reproduce from the repository root; the task record is excluded to avoid a self-referential digest:

```sh
sha256sum README.md docs/architecture/agent-environment-modules.md docs/architecture/environment-operations-qa.md docs/project-status.md | sha256sum
```

## Open items and blockers

- None for this documentation task. The proposed installation UX, real resource enforcement, Agent capture coverage, and ASI-Bench compatibility remain implementation acceptance items.

## Next steps

- Review the proposed operational defaults, then implement minimum contracts and a Local single-node prototype before extending to two-node Ray execution. Develop natural-language preparation against the same deterministic preparation interface.
- Publishing and merging remain with the repository owner; this completed record does not imply integration into `main`.

## Compatibility and rollback

Documentation only. No runtime behavior, deployment, dependencies, or branch rules change. Publishing and merging remain outside this task; this branch depends on the preceding module-design branch.
