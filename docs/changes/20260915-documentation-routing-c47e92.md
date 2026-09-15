---
record_version: 1
task_id: "20260915-documentation-routing-c47e92"
title: "Clarify documentation routing and assess development readiness"
branch: "docs/documentation-routing"
base_commit: "35dd21d8a0967aae4788798a3b18ec3c1a8a7b39"
work_status: completed
updated_at: "2026-09-15T11:22:07+08:00"
pull_request: null
---

## Goal and acceptance

Give agents without conversation history a concise documentation map in both policy files, document routing in the docs index, and assess whether the repository is ready for collaborative AI-assisted development. Keep additional rules focused and distinguish policy from executable enforcement.

## Changes

- Updated both root policy files with identical documentation routing and focused task/interface/runtime-test boundaries.
- Filled [the documentation index](../README.md) with all eight directory purposes, placement examples, and current reading links.
- Added [the readiness assessment](../development/development-readiness.md), linked the docs index from README, and updated project status to prioritize executable S0 foundations.

## Decisions

- Keep AGENTS.md as the canonical policy and CLAUDE.md as an identical mirror.
- Keep current document paths; explain historical placement instead of moving unrelated documents.
- Preserve the pre-existing, unstaged deletion of `docs/development/.gitkeep`; exclude it from this governance commit.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Read instructions, Git state, status, task history, and architecture | Base `35dd21d` plus prior `.gitkeep` deletion | passed | Both policy files were identical; only one pre-existing deletion was present. |
| Python file-size inventory | Same starting workspace | passed | Dependency/build manifests, CODEOWNERS, PR template, docs index, source, tests, scripts, and workflow scaffold have no implementation content. Hosting settings were not inspected. |
| Python document/policy/scope audit; Git whitespace checks | Documentation snapshot below plus this task record | passed | Verified identical policy files, all eight documentation directories covered, relative links, table widths, fences, and seven-file task scope. Preserved the pre-existing deletion separately. |
| Runtime tests | Governance/documentation task | not_run | No runtime implementation. |

Documentation snapshot: `abda9c15f5122af9b72db6de7983017ae53839127b338e2695273b63dfc50cc0`. Reproduce from the repository root; the record is excluded to avoid self-reference:

```sh
sha256sum AGENTS.md CLAUDE.md README.md docs/README.md docs/development/development-readiness.md docs/project-status.md | sha256sum
```

## Open items and blockers

- None for this task. Working build/test/CI tooling, interface ownership, and verified remote protection remain setup work.

## Next steps

- Start executable S0 tooling and contributor setup, then minimum contracts and integration checks before broad parallel module development.

## Compatibility and rollback

Only governance and documentation change. No toolchain, CI workflow, branch protection, or runtime is installed or modified. Revert both policy mirrors together if reverting the policy change. Publishing and merging remain outside this task.
