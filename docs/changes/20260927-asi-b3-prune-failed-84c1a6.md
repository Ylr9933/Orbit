---
record_version: 1
task_id: "20260927-asi-b3-prune-failed-84c1a6"
title: "Remove failed ASI-Bench b3 runtime records while retaining scored results"
branch: "chore/asi-b3-prune-failed-20260927"
base_commit: "bd65d72bb7dc481affa09721473d0cb47595bf6c"
work_status: completed
updated_at: "2026-09-27T20:44:42+08:00"
pull_request: null
---

## Goal and acceptance

- Remove the 35 failed runtime records from the completed local 60-task ASI-Bench b3 batch, keeping the 25 scored runs, their scores, raw evidence and Records readable.
- Present the retained data explicitly as a scored subset of an original 60-attempt batch, not as a 25/25 success claim for the original batch.
- Limit changes to this task-owned runtime directory and this task record; do not disturb other ASI, TB or service workloads.

## Changes

- Replaced only `benchmark/asibench/b3-gpt-6-sol-codex01571-20260926` with a validated 25-run scored subset. The other 35 Run commands, attempt/event/stream/artifact records, leases, workspaces, native job directories, execution plans and unreferenced content-addressed blobs were removed.
- Rebuilt the valid 25-member batch manifest and summary. Added `SELECTION.md` in the ignored runtime directory to state that the original batch attempted 60 tasks and that this retained subset is not the original success rate or an official suite score.
- Removed obsolete 60-task submission/worker/launcher reports from the retained directory. Project source code and other benchmark runtime directories were unchanged.

## Decisions

- The batch manifest is immutable by design. This authorized data cleanup will produce a new subset manifest and digest, while recording the original attempt count and digest separately. The filtered batch is for analysis, not an official suite score or resumed execution.
- Build and validate the retained subset before replacing the original runtime directory. Remove the old directory after successful replacement so failed raw records are not retained as a second archive.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Source-state inventory | Completed original batch | passed | 60 finished runs; 25 scored, 35 failed with `native prediction absent`; no active workers found. |
| Stage scored subset, compare original score/artifact IDs, and read all retained artifacts | Original digest `sha256:6b3a90825313a303627724bbcee15515ca86c1547f369e0f12b59e95d0c39086` versus staged subset | passed | All 25 scores and artifact IDs matched; 511 artifact members read successfully. SQLite integrity/foreign-key checks passed. |
| Hash all retained content-addressed blobs | Staged subset | passed | 545 blobs, 20,588,170 bytes, matched their SHA-256 digests. |
| Replace the original directory, delete the old copy, and recheck | Final runtime path | passed | 25 control runs, 25 Records runs/attempts/artifacts/streams, 25 released leases, 25 workspaces/native jobs and 25 execution plans; 35 failed items absent. No old copy remains. |
| `agent-infra benchmark batch status --directory ...` | Final runtime path | passed | `total=25`, `finished=25`, `scored=25`, `failed=0`, `cancelled=0`; all visible evaluations are scored. This is the retained subset only. |
| Other workloads | Existing ASI/TB/service paths | passed | No other runtime directory or process was modified. |

## Open items and blockers

- None for the requested cleanup. The original 35 failed records were deliberately removed; no local rollback copy was retained.

## Next steps

- None within this task. Use `SELECTION.md` when interpreting the 25-run subset.

## Compatibility and rollback

- Original batch membership and digest changed to `sha256:ee59f141a54cd04f99946e64c2b6b01bd35caddaf9360f8a79257c6d94633a32` in this local runtime artifact. The retained 25 scored results remain addressable by their original Run IDs. The deleted 35 cannot be restored without an external backup, and any Web registration tied to the prior digest must be registered again.
