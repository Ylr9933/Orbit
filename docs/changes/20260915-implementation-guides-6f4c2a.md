---
record_version: 1
task_id: "20260915-implementation-guides-6f4c2a"
title: "Explain the Agent and Resources implementations"
branch: "docs/implementation-guides"
base_commit: "99dbd1ad23a30b8dabaac4529e166bc20fd506ce"
work_status: completed
updated_at: "2026-09-15T19:19:58+08:00"
pull_request: null
---

## Goal and acceptance

- Add two Chinese maintainer guides that explain the current Agent and Resources designs, object
  relationships, code paths, failure behavior and extension points.
- Clearly distinguish implemented behavior from planned Environment, Run, Records, Docker and Ray
  integrations.
- Add the implementation-guide category to repository documentation routing and keep the root Agent
  policies synchronized.

## Changes

- Added detailed Agent and Resources implementation walkthroughs under `docs/implementation/`.
- Added the new documentation category and reading links to the documentation map.
- Added the same placement rule to `AGENTS.md` and `CLAUDE.md`.
- Corrected stale post-merge status text in the project overview, S1 reading entry and Agent
  architecture document without changing their design conclusions.

## Decisions

- Implementation guides explain how current source code works and should be updated with material
  code-path changes. Architecture documents remain authoritative for intended future design, while
  reference documents remain the location for stable exact API definitions.
- The guides use Chinese for maintainer readability while code symbols and provider-native terms
  retain their actual spelling.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make check` | Workspace at 2026-09-15T19:19:58+08:00 based on `99dbd1a` | passed | Ruff, formatting, dependency rules, mypy, Web checks, policy mirroring and local Markdown links passed. |
| Source-to-guide review | Same workspace | passed | Guide claims were checked against Agent and Resources contracts, adapters, bootstrap wiring and unit tests; planned runtime paths are explicitly labeled. |

## Open items and blockers

- None.

## Next steps

- None for the approved documentation scope.

## Compatibility and rollback

- Documentation-only change; no product interface, dependency, configuration or persistent data is
  changed. Reverting the task commit removes the new guides and routing entries.
