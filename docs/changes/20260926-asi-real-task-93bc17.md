---
record_version: 1
task_id: "20260926-asi-real-task-93bc17"
title: "Run a real ASI task through Infra into a local benchmark directory"
branch: "test/asi-real-task"
base_commit: "d513263"
work_status: completed
updated_at: "2026-09-26T06:18:21.958784+00:00"
pull_request: null
---

## Goal and acceptance

- Run one public ASI seed31415 task using native Codex/Docker through Infra; store results and raw evidence under benchmark/asibench.
- Verify native outcome, evidence coverage, container resources and cleanup. No official leaderboard claim.

## Changes

- Ignore benchmark/asibench runtime output in Git; trial directory: `benchmark/asibench/trial-20260926-141103`.

- Exported Records to local results/ and wrote RESULT.md and trajectory.md; project overview unchanged because this repeats an existing capability.

## Decisions

- Reuse user-approved gpt-5.6-sol, local single 4 CPU/8 GiB container, zero GPU; initially one CLI invocation with 300-second timeout. Upper authorization remains three CLI launches/ten minutes cumulative model execution.
- Leave unrelated Docker workloads untouched; isolated state, task-labeled cleanup.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| docker info and existing container listing | d513263 | passed | Daemon available; three unrelated service containers identified. |

| Infra benchmark plan/check/prepare/run + worker/status | d513263 installed adapter wheel and isolated state | passed | Real run b51011ffac6949889f213218ff1b3ff1, attempt attempt_16bb700ce30249878c708925763ef242; b1 only, completed/scored/valid, local public score 17.6, official_score null. One Codex launch, native execution about 299 seconds, outer about 324 seconds. |
| Records export and BenchmarkConsole trajectory | Same run | passed | 17 files exported with size/SHA256 verification; 19,703-byte raw JSONL, 29 trajectory steps, 14 native tool calls, 147 Docker usage samples. Independent model_calls file unavailable upstream, labeled explicitly. |
| Docker inspect, final container listing and benchmark queue | Same run | passed | 4 CPU/8 GiB/no GPU; task container gone, unrelated services retained, owned lease released with cleanup confirmed. |
| Git ignore, Markdown links and final diff | Final task workspace | passed | Runtime artifacts excluded; only ignore rule and concise record committed. |

## Open items and blockers

- None for this single-task trial. b2–b4, full suite and official submission were not run.

## Next steps

- User can read benchmark/asibench/trial-20260926-141103/RESULT.md and trajectory.md. No automatic retry or further model call. Task branch remains unmerged/unpushed.

## Compatibility and rollback

- No runtime code changes. Existing state untouched. Runtime directory stays untracked; revert Git ignore and task record if needed.
