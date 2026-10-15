# Failed-run checkpoints and session continuation
branch: feat/run-resume · status: in_progress · updated: 2026-10-16

## Goal
Preserve a bounded local Docker filesystem checkpoint and native Agent session before failure cleanup, and restore them through the existing Run execution path.

## Changes
- Added opt-in bounded failure checkpoints, local restore API/CLI, benchmark submission support and Web visibility.
- Capture precedes hooks/verification and cleanup; restoration uses a new ordinary Run, preserves remaining execution time and keeps source evidence immutable.
- Restoring or active continuations prevent source deletion; deleting an unused source removes its checkpoint image.
- Process memory, services and external writable mounts require separate recovery semantics and are rejected explicitly.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | passed | Format, lint, types, boundaries, unit/integration tests and builds; Docker-capable shell |
| Checkpoint unit cases | working tree | passed | 8 tests; explicit Docker fakes and filesystem/session fixtures |
| Real Docker failure and restore | working tree | passed | 3 tests, no model calls: killed container, daemon restart, restored files, credential clearing, size rejection, successful-run exclusion and deletion |
| Real native Agent continuation | working tree | not_run | Requires an available requested model; session command generation is covered by unit tests only |

## Next / open issues
- Validate actual native Agent continuation after meaningful task progress and injected upstream failure with an available requested model.
- Keep private benchmark configuration and experiment evidence outside the checkout.
