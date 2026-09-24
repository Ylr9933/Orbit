---
record_version: 1
task_id: "20260924-current-framework-ray-6f8c2a"
title: "Document the current framework and Ray multi-node role"
branch: "docs/current-framework-ray"
base_commit: "00d8b0908036928280ff39a7c288c3371944b33d"
work_status: completed
updated_at: "2026-09-24T15:01:22+08:00"
pull_request: null
---

## Goal and acceptance

- Preserve a detailed Chinese explanation of the current Agent Infra framework, the present
  single-node execution path, Ray's intended responsibilities, and whether implementation has
  departed from the original development sequence.
- Clearly separate implemented behavior from planned Ray/Worker/multi-node behavior, link the
  relevant code and authoritative documents, and make the document discoverable from the
  documentation map.
- Correct directly related stale wording that still claimed the repository could not start Docker.

## Changes

- Added `docs/architecture/current-framework-and-ray-role.md` with the current runtime structure,
  module boundaries, local Run sequence, Ray responsibilities and exclusions, deviation assessment,
  multi-node risks, and a staged validation proposal.
- Added the new architecture explanation to `docs/README.md`.
- Updated stale status wording in `docs/architecture/resource-management.md` to distinguish the
  implemented local Docker path from the unimplemented Ray/multi-node path.

## Decisions

- Keep Ray optional for single-node deployments and describe it as a future multi-node scheduling
  and dispatch backend rather than a replacement for Docker enforcement, host observation, Records,
  or application recovery.
- Treat the current implementation as a documented prioritization of the original local-first
  development sequence. Web and benchmark work advanced before S3, but the core multi-node target
  and backend boundaries remain.
- Do not update `docs/project-status.md` because this documentation task adds no product capability
  and changes no milestone status.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Manual content and final diff review | Workspace at `2026-09-24T15:01:22+08:00` based on `00d8b09` | passed | Checked implemented/planned distinctions, navigation placement, task scope, and the complete documentation diff; no runtime capability is claimed. |
| `uv run --locked python scripts/ci/check_repository.py` | Same workspace | passed | Policy mirrors and all local Markdown file links passed. |
| `git diff --check` | Same workspace | passed | No whitespace errors. |

## Open items and blockers

- None.

## Next steps

- None for the authorized documentation scope. The branch can be reviewed and merged when desired.

## Compatibility and rollback

- Documentation-only change; it does not add Ray, start services, change persistent state, or alter
  runtime interfaces. Reverting the task commit removes the new explanation and restores the prior
  wording.
