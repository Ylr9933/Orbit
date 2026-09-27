---
record_version: 1
task_id: "20260927-local-branch-integration-2b8c9e"
title: "Integrate local documentation, TB-Science Codex and Benchmark Web branches"
branch: "integrate/local-branches-20260927"
base_commit: "b7079f4c3226460639104186bddb38131dd6b216"
work_status: completed
updated_at: "2026-09-27T20:02:46+08:00"
pull_request: null
---

## Goal and acceptance

- Merge all four local branches not yet in `main`, resolve overlap, validate the combined code, and synchronize `main` to `origin` and `zjunlpgit` without changing unrelated active workloads.
- Keep the TB-Science Codex scoring acceptance explicitly incomplete: its approved model budget ended after solving and archival but before verifier execution.

## Changes

- Integrated `docs/research-user-needs`, `docs/framework-abstraction`, `feat/tb-science-codex`, and `feat/benchmark-web-workspace` on this task branch.
- Resolved the overlapping Benchmark page by keeping the workspace screen; preserved TB-Science's generic trajectory support in the shared Records reader.
- Fixed workspace filtering of archived Harbor ATIF tool calls. When present and within the existing read limit, the workspace reads the original ATIF from the Run's own Records artifact. The bounded derived view remains the fallback.
- Reconciled `docs/project-status.md` with the delivered Web workspace and limited TB-Science evidence.

## Decisions

- The user's explicit instruction covers integrating the TB-Science branch. Its task record remains `in_progress`; integration does not imply scored model acceptance or full-suite compatibility.
- The research and architecture reports describe their historical `b7079f4` source snapshot and remain unchanged as evidence of those reviews.
- No live benchmark process, ASI batch, or runtime state was changed during integration.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Fetch both remotes and inspect worktrees/branches | `b7079f4` remote baseline, four clean local branches | passed | Both remotes started at the same baseline; exactly four local branches were unmerged. |
| `make verify` | Merge commit `72191cc` before ATIF filter fix | passed | 417 tests, 33 deselected; lint, types, import boundaries, docs links, Python/Web builds. Log `/tmp/infra-integration-20260927-verify.log`. |
| Focused archived evidence/workspace tests | ATIF filter fix on integration branch | passed | 10 tests; raw ATIF with a clipped derived view retains `tool_call` name and ID. |
| Read-only real TB archive through workspace | Run `0909b736dfab4555ad0346e5600a548a` | passed | One task registered; 137 ATIF steps readable, 131 tool-call steps filterable. No model, Docker, verifier, or state mutation. |
| `make check` | Final integration source and overview | passed | Ruff, mypy, import direction, Web typecheck and documentation links; log `/tmp/infra-integration-20260927-final-check.log`. |
| Optional Harbor adapter tests | `99c8450` source | passed | 17 focused tests on the source branch, including proxy/IP, bundle, auth and evidence boundaries; no integration change to those files. |
| Real TB Codex scoring | Prior approved trial | failed | Watchdog cancelled before verifier; native score and full result coverage absent. A new model budget is required for another trial. |

## Open items and blockers

- TB-Science real Codex scoring and full-suite native execution remain outside the validated outcome.

## Next steps

- None for the authorized local integration. A separate task can complete TB native scoring under a new explicit model budget.

## Compatibility and rollback

- The Web workspace adds read-only Records access and its own metadata; existing run/evidence contracts remain. Reverting the integration merge restores the prior source. Stored annotations and archived benchmark results are not deleted.
