# Agent Development Rules

These rules apply to code, tests, configuration, documentation, and changes to this file. Use them together with the user's approved task scope and any applicable directory-level `AGENTS.md` files.

## 1. Start and resume from evidence

Read in this order:

1. This file and any applicable directory-level instructions.
2. [Project status](docs/project-status.md).
3. The relevant task record in `docs/changes/`.
4. The relevant [repository architecture](docs/architecture/repository-architecture.md), other design documents, and actual code.

Before editing, inspect the repository root, current branch, working tree, staged changes, and relevant recent commits. When Git is available, start with `git status --short --branch` and inspect the relevant diffs. Identify the task's goal, boundaries, and acceptance criteria.

When resuming, reconcile the task record with the actual files, commits, and PR state. Preserve prior user decisions and authorization. Do not rely on conversation memory alone or treat a stale record as proof that work is complete.

## 2. Protect `main` and isolate work

- Never create or edit project files, make direct commits, or push directly on `main`. This includes documentation, progress records, configuration, and `AGENTS.md` itself.
- Before making changes in a Git repository, create or switch to a non-`main` task branch. Examples: `feat/agent-codex`, `fix/run-cancellation`, and `docs/agent-workflow`. Create a task branch before editing from a detached HEAD as well.
- Use a separate worktree for each concurrent editing task. Different developers should use their own clones. Keep linked worktrees beside the main checkout, outside the project's source tree.
- Treat `main` as read-only for development. An authorized PR merge may advance it after the required review and checks; this does not authorize direct development on `main`.
- Verify the branch and review the full staged diff before committing or publishing. Stage only files belonging to the task.
- Preserve existing work. Do not overwrite, reset, clean, stash, or include another person's changes merely to obtain a clean workspace. Investigate overlapping changes and isolate your task where possible.
- Do not rewrite shared branch history, force-push `main`, or bypass required checks or reviews. Branch protection must be configured on the hosting platform; this document and CODEOWNERS alone do not enforce it.
- Give concurrent worktrees separate local configuration, writable state, ports, and service namespaces. Filesystem isolation does not allocate shared GPUs or other execution resources.

### Before Git initialization

If the directory is not yet a Git repository, an explicitly requested documentation or bootstrap task may prepare its files. Record that Git is not initialized and leave branch, commit, and PR fields null. Do not claim that any change is committed, protected, or merged.

Initialize Git only when that work is within the authorized scope. Start an authorized initialization on a non-`main` branch such as `bootstrap/repository`; establish the first `main` baseline through the agreed bootstrap procedure. This is a one-time setup procedure, not an exception for modifying an existing `main` branch. Never assume that `main`, `origin`, or a PR service already exists.

## 3. Work autonomously within the approved scope

The normal workflow is:

`Read context -> isolate the task -> implement -> validate -> update records -> commit and prepare review -> merge when authorized -> verify integration`

Proceed with implementation, relevant tests, fixes, and appropriate task-branch checkpoints within the approved scope. Publishing branches, opening PRs, and merging must follow the user's established authorization and repository review rules. Do not ask again for authorization already given.

If review or additional authorization is needed for a later action, first finish the authorized work and produce a concrete, reviewable result. Missing remote configuration or a pending review does not prevent independent implementation and validation.

Keep unrelated refactoring, formatting sweeps, directory moves, and dependency upgrades separate. Changes to this policy, CI requirements, or branch protection must be explicitly requested governance work; never weaken them to make an unrelated task pass.

## 4. Respect the implementation boundaries

- Product code belongs in `src/agent_infra/` and `src/web/`. Use the designated `docs/`, `tests/`, `deploy/`, `configs/`, `examples/`, and `scripts/` directories for their documented purposes.
- Follow the architecture's import direction. Domain rules remain independent; application code depends on contracts and ports; adapters implement ports; concrete dependencies are assembled in `bootstrap/`.
- Keep HTTP, MCP, CLI, and Worker entrypoints thin. Do not expose Ray handles, Docker clients, or database sessions through public contracts.
- Extend existing modules and interfaces before introducing alternatives. Avoid duplicate managers, DTOs, state machines, and execution paths.
- Update consumers, relevant tests, examples, and documentation when a public contract changes. Edit generated files through their source definitions and regenerate them. Maintain dependency declarations and their lockfiles together.
- Preserve benchmark visibility, budgets, evaluation, and aggregation rules. Keep execution outcomes, scores, and cleanup status distinct. Resource release must reflect actual process and container cleanup.
- Keep secrets, credentials, large datasets, model weights, runtime logs, and generated task artifacts out of versioned project records. Use non-sensitive references and concise evidence.

## 5. Validate the actual change

Check that tools, configuration, and commands are implemented before using them. Empty files, directory scaffolding, proposed commands, and design documents are not evidence of working capabilities.

Use checks appropriate to the change: document structure and links for documentation; relevant unit, contract, integration, or end-to-end checks for implementation. Real Agent, Docker, GPU, and multi-node Ray behavior requires the corresponding real-environment evidence when it is part of the acceptance criteria.

Record the actual command or manual check, the tested revision or identifiable workspace snapshot, the result, and any necessary evidence. Distinguish `passed`, `failed`, and `not_run`; explain skipped checks and their impact. Never report a planned check as executed, or a fake-backed check as real-environment validation.

Resolve required failed checks before declaring the work complete. If required acceptance checks cannot run, retain an incomplete or blocked status unless the user has explicitly revised the acceptance scope. Once relevant checks pass, repeat or broaden them only when subsequent changes or unresolved concerns justify it.

Before delivery, inspect the final diff for unrelated changes, unintended files, sensitive data, and inconsistencies between implementation and documentation.

## 6. Persist current progress and task history

Maintain two complementary documents:

| Location | Purpose | Update model |
| --- | --- | --- |
| `docs/project-status.md` | A concise view of the project's current capabilities, stage, gaps, and next priorities | Replace outdated conclusions; do not append a running history |
| `docs/changes/<task-id>.md` | Recoverable task context, decisions, evidence, and final results | Update during development; preserve as history after integration |

Do not maintain a second manual global activity log or daily log with the same content. Daily reports or release summaries can be derived from task records and Git/PR history when needed. Keep detailed architecture decisions in `docs/adr/` and reference them from task records.

### Project status format and meaning

Keep `docs/project-status.md` approximately one page. Include:

- **Updated at:** an ISO 8601 timestamp with timezone; this is the document update time, not a claimed merge time.
- **Basis:** normally the version of the document on `main`; explicitly identify a pre-Git workspace when applicable.
- **Current stage and stage overview:** use the architecture's S0-S4 milestones.
- **Available capabilities or outcomes:** what has actually been delivered and, where applicable, validated.
- **Main gaps:** what remains before the current stage can be accepted.
- **Next priorities:** the most important one to three next outcomes.
- **Project-level blockers:** issues affecting overall progress, separate from completion status.
- **Related records:** a small number of links to relevant task records or decisions.

Stage status must be `not_started`, `in_progress`, or `accepted`. `in_progress` means some relevant work has been integrated but the stage's acceptance criteria remain unmet. `accepted` requires evidence for those criteria. Before Git initialization, label these as workspace outcomes. Do not invent completion percentages or equate an empty module directory with a working feature.

Once Git exists, the `main` version describes integrated project facts. An update on a task branch proposes the status that will hold if its PR is merged. Do not mark another unmerged branch's feature as available. Next priorities may describe future work, but the overview must not become a live roster of every agent, session, and branch.

Update the overview when a delivered capability, milestone, major gap, priority, or project-level blocker changes. Ordinary progress within a task and minor fixes usually do not require an overview update.

### Task records: granularity and lifecycle

Use one record per independently reviewable and mergeable significant task, not per day, conversation, session, or individual commit. A task spanning several days or sessions keeps the same ID. Split a large initiative into records for its independently delivered changes and link the related task IDs.

Records are required for new capabilities, substantive bug fixes, public contract or state changes, dependency or deployment changes, and important architecture or governance work. Pure spelling or formatting corrections may rely on the PR description alone.

Use a stable, collision-resistant ID such as `YYYYMMDD-short-description-unique-suffix`. Its date is an identifier component, not an inferred completion or merge date. Avoid shared sequential counters.

Create the record when a significant task starts. Update it after meaningful milestones, when blocked, before pausing or handing off, and before delivery. Save enough context for another session to continue; make appropriate task-branch checkpoint commits when useful. Do not record every shell command or copy entire conversations.

Use the following format. All fields and sections are required; use null or `None` with an explanation when information does not exist. Replace placeholders with actual facts.

```markdown
---
record_version: 1
task_id: "YYYYMMDD-short-description-unique-suffix"
title: "A concise description of the task"
branch: "feat/task-name"
base_commit: "<starting commit SHA>"
work_status: in_progress
updated_at: "<ISO 8601 timestamp with timezone>"
pull_request: null
---

## Goal and acceptance

- The problem, scope, and conditions for completion.

## Changes

- The actual behavior changed and the relevant modules or files.

## Decisions

- Necessary decisions and reasons; link related tasks or ADRs.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| <actual check> | <commit or workspace snapshot> | passed / failed / not_run | <evidence or reason> |

## Open items and blockers

- Remaining acceptance items or blockers; write None when there are none.

## Next steps

- A concrete next action, or None when the authorized work is complete.

## Compatibility and rollback

- Interface, configuration, data, or deployment impact and any necessary rollback approach.
```

`work_status` must be `planned`, `in_progress`, `blocked`, or `completed`. It describes work against the approved scope and required validation, not Git integration. A `completed` record does not imply that its branch has been merged.

Keep Git integration facts in Git/PR history. Do not require the final merge SHA to be embedded in the record carried by that same commit. Reference the tested code commit or a reproducible snapshot instead; do not fabricate a future SHA or merge timestamp.

### Integrate records with their changes

- Include a significant change and its finalized task record in the same branch and PR. Include the overview update in that PR when the overall project state changes.
- Before merging, reconcile overview edits with the latest target branch. Modify only relevant conclusions and preserve other integrated outcomes. Resolve conflicts semantically; do not choose one entire version just to remove a conflict.
- Verify that the final code, required record, and applicable overview update reached the intended `main` branch before reporting integration as complete. Do not edit `main` afterward to add a missing log entry; use a follow-up task branch and PR if a correction is needed.
- Preserve integrated task records as historical evidence. Later fixes, reversions, or replacements get new records linking the original; update the overview to reflect the corrected current state. Do not rewrite history to imply an earlier outcome was different.
- Leave unfinished work in its task branch with an up-to-date record. Do not label it complete merely because the session is ending.

## 7. Report a verifiable handoff

At delivery or handoff, report:

- What was completed and the important files or modules changed.
- What was validated, the results, and material limitations.
- The branch, commit, or PR when available, and the actual integration state.
- The task record location and whether the project overview changed.
- Remaining work, blockers, and the next action when applicable.

Keep implementation completion, successful validation, and merging into `main` distinct. Report unavailable Git metadata honestly during bootstrap. Communicate with the user in their preferred language.
