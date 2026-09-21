---
record_version: 1
task_id: "20260921-codex-host-sessions-8d7a4e"
title: "Bind and capture local interactive Codex sessions for research projects"
branch: "feat/codex-host-session-capture"
base_commit: "e974a5d"
work_status: completed
updated_at: "2026-09-21T21:42:43+08:00"
pull_request: null
---

## Goal and acceptance

- Discover local Codex sessions by project workspace metadata without reading conversation bodies during discovery.
- Explicitly bind a session to one project, import its original transcript into project-linked Records, and resume incrementally without duplicates.
- Provide a notification-driven sync entrypoint for subsequent completed turns, while preserving privacy and partial-capture semantics.
- Validate parser, path ownership, binding, replay, and CLI behavior with synthetic transcripts. No real model call is required.

## Changes

- Added local interactive Codex metadata discovery, explicit project binding, private raw-line preservation, normalized Records events and independent host-session Run/Attempt.
- Added resumable, idempotent CLI sync and a Codex `agent-turn-complete` notify entrypoint for already-bound sessions.
- Added database migration, synthetic rollout tests, command reference, and project status/navigation updates.

## Decisions

- Interactive rollout JSONL has a different structure from `codex exec --json`; it needs a separate versioned normalizer.
- A project-bound host session gets its own Records Run/Attempt so capture can begin before a Docker experiment exists.
- Workspace matching only suggests candidates; the user selects a real thread ID, and one thread cannot be rebound to another project.

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | Task-branch workspace before final session-lookup optimization | passed | 308 non-integration tests, import boundaries, type/lint, docs links, wheel and Web builds. |
| `pytest -q tests/unit/projects/test_codex_sessions.py tests/unit/projects/test_compilation.py tests/unit/projects/test_iteration.py tests/unit/projects/test_research.py` | Task-branch workspace after session-lookup optimization | passed | 58 tests; project ownership, incomplete JSONL tail, cursors, de-duplication and database migration. |
| CLI subprocess smoke (`init → discover → bind → sync`) | Task-branch workspace after session-lookup optimization | passed | Synthetic local rollout: one discovered, one imported, zero reimported. |
| Ruff, mypy, documentation-link checker, `git diff --check` | Task-branch workspace after session-lookup optimization | passed | No reported errors. |
| Local Codex metadata inspection | Task-branch workspace after implementation | passed | 803 session headers readable; no personal transcript bodies imported. |
| Real Codex notification callback | Task-branch workspace after implementation | not_run | Requires user-level notify configuration and a new real model turn; synthetic callback was tested. |

## Open items and blockers

- No blocker for the approved implementation. Real notification delivery and future Codex rollout schema changes need field validation after user opt-in.

## Next steps

- Merge this stacked task branch after review of its GPU prerequisite commits; then bind a chosen project session and optionally configure user-level Codex notify.

## Compatibility and rollback

- Additive project-store and Records data. Existing explicit `research import-trace` remains available. Removing the new CLI path stops new capture; retained Records remain readable.
