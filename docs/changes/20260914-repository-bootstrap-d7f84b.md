---
record_version: 1
task_id: "20260914-repository-bootstrap-d7f84b"
title: "Prepare the ignore policy, README, and local repository foundation"
branch: "bootstrap/repository"
base_commit: null
work_status: completed
updated_at: "2026-09-14T12:20:18+00:00"
pull_request: null
---

## Goal and acceptance

Fill [.gitignore](../../.gitignore) and [README.md](../../README.md) for the initial repository. Ignore local environments, private configuration, caches, runtime data, and build output while keeping project source, schema snapshots, dependency locks, documentation, and small fixtures trackable. Describe planned capabilities and the actual scaffold stage accurately, with working documentation links.

The original request included Git initialization and remote publication. Local Git initialization on `bootstrap/repository` and configuration of `origin` were completed before the user took over uploading. The revised task covers local preparation; remote publication is owned by the user. There is no starting commit, so `base_commit` is null.

## Changes

- Add scoped ignore rules for the Python/Web monorepo, preserving sanitized environment templates and selected shared editor configuration.
- Add the English project README with goals, operating modes, source layout, documentation entrypoints, contribution workflow, roadmap, and an explicit scaffold status.
- Update [project status](../project-status.md) to reflect the local Git setup and the new repository entry documents.
- Repair two source links in the repository architecture document to match the existing locations of the requirements document and source image.
- Preserve the existing scaffold, agent rules, historical task record, and user-authored `CLAUDE.md`.

## Decisions

- Root-anchor runtime output directories so similarly named directories inside task fixtures and native examples remain trackable.
- Avoid blanket exclusions for JSON, YAML, logs, generated source, schemas, and model-file extensions; local datasets and model outputs belong in the ignored runtime/data directories.
- Preserve `.env.example` and explicit example/template variants, dependency lockfiles, and shared configuration.
- Keep setup and feature claims aligned with empty implementation files. No runtime install or start command is presented as available.
- Continue the approved per-task record and concise overview model from [the workflow setup](20260914-agent-workflow-a6892f.md).

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Inspect current branch and file contents | Initial workspace on `bootstrap/repository` | passed | Git has no commits; `.gitignore` and `README.md` were empty. The configured remote matches the user-provided repository. |
| `git check-ignore --no-index --quiet` on representative paths and `git check-ignore --no-index --stdin` on the existing inventory | Final local ignore policy; SHA-256 below | passed | All 68 exclusion cases and 47 retention cases matched expectations. All 102 existing project files remain trackable. Synthetic path checks did not create files. |
| Python 3 checks for Markdown structure, relative links, record metadata, and source-inventory hashes | Final local documentation | passed | Twenty relative links resolved. Four planned existing files changed, one task record was added, and 97 other pre-existing files were preserved. |
| `git diff --no-index --check /dev/null` for each of `.gitignore` and `README.md` | Final local files; SHA-256 below | passed | No whitespace diagnostics. Exit code 1 represents the file additions in no-index mode. |
| Manual README review against the architecture and current scaffold | Final English README | passed | Planned capabilities are labeled; empty build/configuration files and pending license selection are described accurately. No unimplemented setup command is presented as usable. |
| Application build and runtime tests | Documentation and ignore-policy task | not_run | Implementation and build configuration remain placeholders; runtime testing is outside this task's acceptance scope. |

Validated document snapshots (SHA-256):

- `.gitignore`: `2256d1ee969b56ecc530e33227e8969a05c4e5aa34fe9ed81b2448a0d07798b4`.
- `README.md`: `910c145f54c60d0a61a04c3d2c972557d10f75907299cee18bed3a36dce3cc7c`.

## Open items and blockers

None for the revised local documentation task. Remote publication is owned by the user and is not claimed as completed here.

## Next steps

None for the local file changes. The repository owner handles committing and uploading the initial baseline; no commit, PR, or push was produced by this revised task.

## Compatibility and rollback

There are no runtime or public API changes. `.gitignore` affects discovery of untracked files; it does not remove already tracked content. Future local data should be placed in the designated ignored directories. Once versioned, adjust or revert the policy through a task branch, preserving this record as history.
