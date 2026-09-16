---
record_version: 1
task_id: "20260916-records-architecture-7e4a91"
title: "Design the Records architecture for trace analysis and Agentic RL"
branch: "docs/records-architecture"
base_commit: "f3a9ae3ffd3810ff878de3d4088cf7ab00514032"
work_status: completed
updated_at: "2026-09-16T14:23:43+08:00"
pull_request: null
---

## Goal and acceptance

- Define a detailed Records architecture that covers native and normalized Agent traces, environment execution, artifacts, evaluation, host and container execution, querying, retention, and failure handling.
- Preserve enough immutable evidence and lineage to derive future trajectory-analysis, SFT, preference-learning, and Agentic-RL datasets without coupling the runtime schema to one Agent or training framework.
- Explain how the proposed design can replace the current minimal `LocalRunJournal` incrementally.
- Keep this task at the architecture level; implementation is outside the approved scope.

## Changes

- Added a Records architecture proposal under `docs/architecture/`.
- The proposal defines the data layers, core entities, canonical event envelope, storage model, public interfaces, security boundaries, RL-oriented derived views, and an incremental implementation sequence.
- Updated the documentation map so a new contributor can locate the Records design.

## Decisions

- Treat provider-native data, canonical observable events, and training-oriented trajectory views as three distinct layers.
- Keep raw evidence immutable and derive versioned episode/step views instead of forcing all Agents into a lossy common trace format at ingestion time.
- Use Attempt as the default rollout boundary while keeping step segmentation and reward assignment versioned and replaceable.
- Keep credentials and hidden evaluation material outside ordinary trace storage, with explicit access and retention policies for private records.
- Recommend SQLite plus filesystem content-addressed blobs as the first local backend while keeping backend details behind the Records public API.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `python3 scripts/ci/check_repository.py` | `docs/records-architecture` workspace at 2026-09-16T14:23:43+08:00 | passed | Policy mirrors and local Markdown file links passed. Remote URLs and anchors are outside this check. |
| `git diff --check` | `docs/records-architecture` workspace at 2026-09-16T14:23:43+08:00 | passed | No whitespace errors were reported. |
| Manual architecture review against current Records, Run, Agent, and Environment source | `f3a9ae3` plus this documentation workspace | passed | Confirmed that implemented behavior is described as current and the proposed contracts remain marked as future work. No runtime or real-environment validation applies to this documentation-only task. |

## Open items and blockers

- None for the approved documentation scope. The proposed public contracts and storage choices require review as part of a separate implementation task.

## Next steps

- Review the proposal, then create a separate implementation task for R0 Records contracts and R1 local storage.

## Compatibility and rollback

- This task changes documentation only and does not change runtime behavior or public Python APIs.
- The proposal includes a compatibility path for existing per-run `events.jsonl` and `result.json` records. Reverting the documentation commit removes the proposal without affecting stored runs.
