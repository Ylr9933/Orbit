---
record_version: 1
task_id: "20260928-web-evidence-review-3fa821"
title: "Surface benchmark evaluation health and evidence-linked research reviews"
branch: "feat/benchmark-review-20260928"
base_commit: "55f5c31"
work_status: in_progress
updated_at: "2026-09-28T22:16:53.043185+08:00"
pull_request: null
---

## Goal and acceptance

- Show saved scores, evaluation anomalies and actual terminal evidence separately without rescoring or altering original runs.
- Import version-bound authored reviews into existing batch/task pages, with validated evidence links and a readable/downloadable full report.
- Validate nested failures, terminal ambiguity, missing evidence, stale reviews, ownership and browser navigation; check real 60-task results read-only.
- Integrate all outstanding local branches and publish to both remotes as explicitly authorized.

## Changes

- Integrated the previous offline review with the existing Web improvements; implementation underway.

## Decisions

- Reuse Workspace metadata and Records; no extra execution path, model runs or dependencies. Review prose is authored analysis, distinct from machine-record facts.
- Keep original metrics and aggregation unchanged. Unavailable evidence is unknown, not healthy.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git inventory and remote fetch | 55f5c31 | passed | Clean original checkout; both remotes fetched; review clone imported; isolated sibling worktree. |
| Implementation checks | None | not_run | In progress. |

## Open items and blockers

- Implementation, tests, real report import and publication outstanding.

## Next steps

- Implement health projection and review storage/view; validate and integrate.

## Compatibility and rollback

- Additive read models and console metadata only; preserve original scores and artifacts. Revert through a task branch and rebuild Web to roll back.
