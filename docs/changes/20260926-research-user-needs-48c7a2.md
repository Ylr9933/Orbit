---
record_version: 1
task_id: "20260926-research-user-needs-48c7a2"
title: "Research practical scientific-agent needs and compare current infra"
branch: "docs/research-user-needs"
base_commit: "b7079f4c3226460639104186bddb38131dd6b216"
work_status: completed
updated_at: "2026-09-26T17:12:07+08:00"
pull_request: null
---

## Goal and acceptance

- Produce a detailed Chinese needs study grounded in public GitHub issues, community discussions,
  scientific practice, official documentation and the current implementation.
- Cover diverse research workflows; distinguish user reports, project claims, verified local
  implementation, inference and proposed work. Do not treat issue counts as prevalence.
- Recommend a minimal practical scope, prioritized gaps, reuse options and measurable acceptance
  criteria. Verify source links and local documentation links.
- Documentation only: no runtime, resource allocation, product API or governance changes.

## Changes

- Added `docs/product/scientific-agent-needs-2026-09.md`, a detailed Chinese study with 38
  individually linked sources, 22 needs, audience/workflow distinctions, current-source gap
  analysis, reuse comparisons, four proposed delivery packages and practical trial criteria.
- Linked the report from `docs/README.md`. The project overview remains unchanged: this task
  delivers research and recommendations, not a new runtime capability or approved roadmap.

## Decisions

- Base the audit on integrated local `main` at `b7079f4`, in a separate sibling worktree.
  Preserve uncommitted TB-Science work and other worktrees; exclude their features from the baseline.
- Do not change the project overview solely for proposed priorities or research findings.
- Use official OpenAI documentation for Codex capability facts; the user's requested broader
  community research also requires original forum posts and upstream issue reports.
- Treat forums/issues as qualitative demand signals and distinguish project claims from
  demonstrated adoption. Preserve issue closure reasons and research sampling limitations.
- Reconcile historical findings: the Records crash-tail issue has a fix and regression case;
  terminal log draining and failure-artifact paths still warrant work on the audited baseline.
  These are source inspections, not new real-Docker reproductions.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git status, branches, worktrees, recent commits and docs/source inspection | `b7079f4` | passed | Independent documentation branch created from main; existing edits preserved. |
| Public source review and report/source reconciliation | Report SHA-256 `7e029ca5a9776692bcada18bf0a7e21e095bdc46042e3d4d88537fb29c6eab14` on `b7079f4` | passed | Reviewed original community pages, papers, tools and official docs; independently fetched public GitHub API metadata for all eight issue entries. Conclusions separate inference, current source, historical evidence and proposals. |
| `python3 scripts/ci/check_repository.py` and `git diff --cached --check` | Same report and navigation snapshot, 2026-09-26 | passed | Policy mirrors and local Markdown file links pass; final staged whitespace check passes after removing Markdown hard-break spaces caught on first staging. Used the available `python3` executable. |
| Inline Python source-index/anchor audit | Same report SHA-256 | passed | 38 unique source IDs and URLs; 22 unique needs; all source anchors resolve; fences balanced. External contents were reviewed through browsing/API, not inferred from URL syntax. |
| Runtime/model/Docker/GPU experiments | Documentation-only scope | not_run | No new runtime capability or real-environment acceptance is claimed. |

## Open items and blockers

- None for the documentation scope. Product implementation, user interviews and real-environment
  acceptance remain recommendations, not uncompleted actions within this request.

## Next steps

- None within the authorized research task. The local documentation branch is ready for review;
  publishing, PR creation and integration were not requested.

## Compatibility and rollback

- Documentation only; no API, state or deployment impact. Revert report and navigation changes
  if superseded. Publishing and integration are outside this research request.
