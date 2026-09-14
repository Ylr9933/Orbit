---
record_version: 1
task_id: "20260914-module-boundaries-812d9b"
title: "Design decoupled modules around Agent and Environment"
branch: "docs/agent-environment-modules"
base_commit: "c3155839567572fddd2dc8ccfc8f869b529d4716"
work_status: completed
updated_at: "2026-09-14T14:29:49+00:00"
pull_request: null
---

## Goal and acceptance

Write a Chinese architecture proposal identifying the project's functional modules, responsibilities, coarse interface boundaries, and development sequence. Treat Agent and Environment as the two core modules, with a supporting Web interface. Keep this iteration above method signatures, HTTP route schemas, database tables, and implementation details.

The user clarified that the current scaffold is provisional. Evaluate a better source organization rather than treating the existing directory tree as a constraint. Clearly distinguish proposed structure from the files and capabilities currently implemented.

## Changes

- Added the Chinese [module architecture proposal](../architecture/agent-environment-modules.md), covering eight functional modules, their public capabilities, import boundaries, both operating modes, a proposed source layout, development sequencing, and independence criteria.
- Added navigation from the [README](../../README.md) and [previous repository design](../architecture/repository-architecture.md), distinguishing the current scaffold from the proposed layout.
- Updated the [project overview](../project-status.md) to reflect the initial Git baseline and the new design proposal, without treating proposed capabilities as implemented.
- Preserved runtime code, scaffold directories, agent rules, build configuration, and historical task records.

## Decisions

- Propose independently testable Agent and Environment contracts, coordinated by Run, without forcing CLI agents into a shared decision loop.
- Separate environment lifecycle management from the narrower execution access granted to agents.
- Keep task parsing and evaluation as distinct interfaces within one task/benchmark module so each benchmark's native protocol stays together.
- Propose functional module directories, internal implementation boundaries, and a small shared contract layer. Keep one Python distribution and a small number of deployment processes initially.
- Retain both deployment modes, truthful trace-coverage boundaries, benchmark visibility and interaction rules, single-node main allocations per attempt, and cleanup-based resource release.
- Keep exact interfaces, source migration, and directory-rule changes for follow-up tasks. This proposal does not change the current development rules.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Inspect instructions, Git state, and design sources | Base commit `c3155839567572fddd2dc8ccfc8f869b529d4716` | passed | The working tree was clean on `main`; a task branch was created before editing. The local `main` and recorded `origin/main` both reference the initial commit. |
| Manual review of module ownership, interfaces, and independence criteria | Documentation snapshot defined below | passed | Checked responsibilities and dependencies against the source requirements, both operating modes, benchmark rules, resource ownership, and the user's provisional-layout clarification. Interface names describe capabilities; no executable API is claimed. |
| Python audit of Markdown fences, table structure, relative links, section order, and required task-record fields | Documentation snapshot below plus this task record | passed | The five task documents were checked. The new design has nine top-level sections. Mermaid relationships were reviewed as text; no rendered-browser check was run. |
| `git diff --check` and new-file checks using `git diff --no-index --check /dev/null <file>` | Documentation snapshot below plus this task record | passed | Removed Markdown hard-break trailing spaces flagged in the initial check; the repeated whitespace checks passed. For clean new files, no-index returned 1 for file differences with no whitespace diagnostics. |
| Compare file SHA-256 inventory with the starting workspace; inspect Git branch and diffs | Base commit plus the five task documents | passed | Only the new design, its record, README navigation, the prior-design note, and the project overview changed. No files were removed; existing source, configuration, agent rules, and historical records were unchanged. |
| Runtime or API tests | Architecture-only task | not_run | No implementation or executable API is being introduced. |

Documentation snapshot: `b82ed248df75614b01ebe420d8c4110decee47c4dfa1a4d6181a95944d59246c`. Reproduce from the repository root with the following command; the task record is excluded to avoid a self-referential digest:

```sh
sha256sum README.md docs/architecture/agent-environment-modules.md docs/architecture/repository-architecture.md docs/project-status.md | sha256sum
```

## Open items and blockers

- None within the authorized documentation scope. The proposal still requires design review before adoption; source migration and implementation are separate future work.

## Next steps

- Review the module boundaries and proposed source organization, then define the minimum Agent/Environment/Run contracts and supporting examples in a follow-up task.
- Publishing remains with the repository owner. Completion of this record does not imply pushing or merging the task branch.

## Compatibility and rollback

This task changes design documents only. The proposed layout does not migrate files or change runtime interfaces. If the proposal is adopted, directory migration and updates to affected development rules should be delivered as a separate coherent change. Publishing and merging remain outside this task.
