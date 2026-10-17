# Failed-run checkpoints and session continuation
branch: feat/run-resume · status: completed · updated: 2026-10-17

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
| `pnpm verify` | 352b574 | passed | Format, lint, types, boundaries, unit/integration tests and builds; Docker-capable shell |
| Checkpoint unit cases | 352b574 | passed | 8 tests; explicit Docker fakes and filesystem/session fixtures |
| Real Docker failure and restore | 352b574 | passed | 3 tests, no model calls: killed container, daemon restart, restored files, credential clearing, size rejection, successful-run exclusion and deletion |
| Real Codex CLI continuation | 352b574 | passed | Injected upstream errors, confirmed cleanup, offline restore without API requests, same native session and complete rollout prefix, new tool execution and another usable checkpoint; no benchmark score asserted |
| Ordinary Run native continuation | 927f58d | passed | Disposable two-stage fixture without a benchmark adapter: interrupted after the first file, restored offline without API calls, continued the same session and completed stage two while the first file's hash and mtime stayed unchanged |
| Real Claude Code continuation | 352b574 | not_run | Command construction is covered by unit tests only |

## Next / open issues
- Codex v0.162.1 emitted a state-database diagnostic while shutting down an interrupted resumed turn; both raw rollout copies and the subsequent checkpoint were verified intact. Live subprocesses still need to restart, as documented.
- Keep private benchmark configuration and experiment evidence outside the checkout.
- This policy covers supported local Docker Runs; process/service/remote recovery, automatic retries and application-specific progress restoration are not implemented by it.
