---
record_version: 1
task_id: "20260928-asi-b3-consolidate-retry-8c7d4e"
title: "Consolidate the scored ASI-Bench b3 retry into the 60-task runtime batch"
branch: "chore/asi-b3-consolidate-retry-20260928"
base_commit: "906b2f73c4922455f33cb2011b399640ef39b3ae"
work_status: completed
updated_at: "2026-09-28T14:36:01+08:00"
pull_request: null
---

## Goal and acceptance

- Replace the failed `computer_science.causal_attention__seed31415` Run in the existing 60-member local batch with its completed, valid, separately executed retry, while keeping the other 59 scored Runs unchanged.
- Remove the failed Run's control, Records, lease, workspace and native-job data from the active batch; retain the retry's score, artifact, native Codex trace, resource evidence and provenance.
- Make the original batch directory and its Web registration show 60 finished, 60 valid scored tasks and zero failed tasks. Verify every score and artifact remains readable. Report the 60-task arithmetic mean as a local public score, not an official ASI suite score.

## Changes

- Replaced the failed Run's control row, Records run/attempt/events/stream/artifact, lease, workspace and native job with the successful retry under the existing ignored 60-member batch directory. The frozen batch manifest, execution plans and other 59 Run IDs/results were unchanged.
- Copied and hash-verified the retry's content-addressed blobs; removed old Run-only blobs and the failed Run's runtime files. Regenerated the existing `summary.json` and `SUMMARY.md` with 60 valid scores and no extra runtime annotation.
- Preserved the standalone successful retry directory because its captured native evidence contains absolute workspace references. Deleted the task-owned temporary rollback copy containing the old failed Run after validating the active directory.
- Removed the standalone one-member retry's Web workspace registration; the existing 60-member registration remains visible without an extra retry batch.

## Decisions

- The user explicitly authorized removal of the earlier failed runtime record and incorporation of the scored retry. Preserve the [earlier task record](20260928-asi-causal-attention-retry-4e61c2.md) and [original 59/60 outcome record](20260927-asi-b3-resume-35-6d51b9.md) as historical facts; do not rewrite them as if the retry were the first attempt.
- Stage and validate a complete copy before replacing the active runtime directory. Keep the standalone retry directory as source provenance because native evidence contains absolute references to its workspace. The user requested that the 60-task view carry no extra retry label; historical context remains in task records.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Read original and retry batch summaries | Source runtime at 2026-09-28 14:27 +08:00 | passed | Original: 59 scored, one failed. Retry Run `ee52851be95f4c84b374bdbbc08c3383`: completed, valid, local public score 100.0, cleanup complete. |
| Staged transplant and full readback | Staged runtime snapshot at 2026-09-28 14:31 +08:00 | passed | `benchmark batch status`: 60/60 finished and scored, zero failed; retry Run has local public score 100.0. Other 59 summary rows are identical. 1,192 artifact members read and SHA-256 checked; all 1,273 retained blobs hash-verified. |
| SQLite integrity, foreign keys, lease and files | Staged and final runtime snapshots | passed | `integrity_check=ok` and zero foreign-key errors for control, Records and lease databases; 60 Records runs/attempts/artifacts/streams and 60 released leases; failed Run absent, replacement workspace/native job present. |
| Final `benchmark batch status` | Active directory at 2026-09-28 14:33 +08:00 | passed | 60/60 finished, 60 scored, zero failed/cancelled. Arithmetic mean of all 60 finite `local_public_score` values: **35.43277818088395**. `official_score=null`. |
| Benchmark Web workspace read and evidence | Active directory at 2026-09-28 14:33 +08:00 | passed | Existing registration `batch-689dfc5adaa2220de3ca` reads 60 Runs and 60 scored; replacement logs, 18 evidence files and first trajectory page are readable. Direct unauthenticated HTTP returned expected 401; an authenticated browser request was not run. |
| Task-owned rollback cleanup | Active directory after final readback | passed | Old failed Run absent from active summary and state; temporary rollback copy deleted. Standalone successful retry remains as source provenance. |
| Web registration consolidation | Personal Web state at 2026-09-28 14:36 +08:00 | passed | Removed only source registration `batch-d30c391796c63c32f064` after checking its exact retry path. Existing `batch-689dfc5adaa2220de3ca` remains and reads 60 scored Runs. |

## Open items and blockers

- None for the requested consolidation. This arithmetic mean is based on local public per-task scores, not an official ASI leaderboard submission.

## Next steps

- None within this task.

## Compatibility and rollback

- The frozen 60-member manifest and execution plans remain byte-for-byte unchanged; the causal-attention operation ID now resolves to retry Run `ee52851be95f4c84b374bdbbc08c3383`. The active runtime directory and personal Web state are ignored by Git, so Git alone cannot restore their previous contents. The failed raw Run was deleted as authorized; the historical task records document the prior failure. The standalone retry can be registered in Web again from its retained directory if needed. Product code and benchmark protocol did not change.
