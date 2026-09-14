---
record_version: 1
task_id: "20260914-agent-workflow-a6892f"
title: "Define agent development rules and initialize persistent progress records"
branch: null
base_commit: null
work_status: completed
updated_at: "2026-09-14T12:07:47+00:00"
pull_request: null
---

## Goal and acceptance

Write the user-approved development workflow in English in [AGENTS.md](../../AGENTS.md). Define the agreed combination of a concise project overview and one record per significant task.

Acceptance requires explicit protection against direct development on `main`, actionable task and integration rules, fixed record fields, honest validation requirements, and clear separation of work completion from Git integration. Initialize the overview and this task record using actual workspace evidence.

This is an explicitly authorized documentation task before Git initialization. Git metadata is null because no local Git repository, branch, commit, or PR exists. No Git initialization or integration is included in this task.

## Changes

- Populate the previously empty root `AGENTS.md` with the approved English rules.
- Add [project-status.md](../project-status.md) as a concise overview of the current workspace, explicitly labeled as pre-Git.
- Add this task record as the initial example of the required format.
- Preserve existing implementation placeholders, architecture documents, and the source image.

## Decisions

- Keep current project status in one replaceable overview, with per-task records for recovery and durable history. Daily and global activity logs are not separately maintained.
- Carry each significant change, its finalized record, and any necessary overview update in the same PR once Git is established.
- Determine integration from Git/PR history rather than a manually duplicated merged flag or a self-referential commit SHA.
- Allow explicitly requested pre-Git documentation work while requiring honest null metadata. Future Git initialization is a separately authorized bootstrap task on a non-`main` branch.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Inspect Git state and existing instruction files | Pre-edit workspace on 2026-09-14 | passed | `git status --short --branch` confirmed that this directory is not a Git repository; root `AGENTS.md` was empty. |
| Python 3 checks for Markdown structure, relative links, required record fields, and timezone-aware timestamps | Documentation workspace; policy and overview hashes below | passed | All seven relative links resolved; code fences, tables, metadata, task ID, and required record sections were checked. The embedded task template's heading spacing was also checked. |
| SHA-256 comparison against the pre-edit workspace inventory | Inventory captured at 2026-09-14T12:03:10+00:00 | passed | All 97 other pre-existing files were preserved. Only `AGENTS.md` changed; the overview and this record were added. Git was not initialized. |
| Manual review against the approved workflow and the architecture | Final English rules and initial progress documents | passed | Checked branch protection, authorization boundaries, persistence format, overview update rules, handoff, and truthful pre-Git status. |
| Application build and runtime tests | Documentation-only change | not_run | The corresponding tooling and implementation are empty placeholders; runtime validation is outside this task's acceptance scope. |

Validated document snapshots (SHA-256):

- `AGENTS.md`: `0beafe7dfaa4be7cdddba48bdf9aa75253a98a73eefd01890769db5c11c6df2b`.
- `docs/project-status.md`: `1df48d18ec52a4029d1f4849f65089ead5f7ad539bac30df1f16cb57778c9cc2`.

## Open items and blockers

None for the authorized documentation task. Git setup and application implementation remain separate project work, as described in the overview.

## Next steps

None for this task. Git integration has not occurred; do not treat the completed work status as a merge result.

## Compatibility and rollback

This change establishes development conventions without altering runtime code, APIs, dependencies, or deployment behavior. Git/PR protection still requires future repository setup. Revisions to these rules should be explicit governance tasks. Once versioned, any rollback must use a task branch and preserve this record as historical evidence.
