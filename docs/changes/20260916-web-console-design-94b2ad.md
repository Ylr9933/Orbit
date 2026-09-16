---
record_version: 1
task_id: "20260916-web-console-design-94b2ad"
title: "Design the research Web console and its integration boundaries"
branch: "docs/web-console-design"
base_commit: "c6acc18bb297db3a2a7b09d2319174c3b0ebb5fd"
work_status: completed
updated_at: "2026-09-16T20:40:06+08:00"
pull_request: null
---

## Goal and acceptance

- Produce a Chinese proposal covering project progress, live host resources, Tasks, Agents, Runs, Records, artifacts, and evaluation.
- Specify navigation, key interactions, module ownership, proposed APIs, realtime behavior, permission boundaries, implementation phases, and acceptance criteria.
- Distinguish delivered Python capabilities from missing backend services and proposed UI behavior. No application implementation is in scope.

## Changes

- Added `docs/architecture/web-console-design.md` and its navigation entry. Includes pages, resource freshness, project milestones, proposed API families, authorization, realtime gaps and W0-W3 delivery criteria.

## Decisions

- Organize the console around Project -> Task revision -> Run -> Attempt, with independent module views.
- Keep scientific milestones separate from execution status and benchmark scores.
- Build authenticated read paths and resource monitoring before enabling remote execution controls.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Source and documentation inspection | c6acc18 | passed | Reviewed Web starter, HTTP scaffold, Records contracts, Run collection path, monitor entry point and prior task record. |
| `python3 scripts/ci/check_repository.py` and `git diff --check` | Documentation workspace based on c6acc18 | passed | Local links, policy mirrors and whitespace checked before commit. |

## Open items and blockers

- None for the documentation scope; runtime and backend gaps will be listed in the proposal.

## Next steps

- Implement the user-requested simple console as a separate feature task based on this proposal.

## Compatibility and rollback

- Documentation only. No new dependencies, runtime contracts or deployment changes. Revert this documentation commit to remove the proposal.
