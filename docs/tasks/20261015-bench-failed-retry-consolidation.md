# Explicit consolidation of failed attempts
branch: fix/bench-failed-retry-consolidation · status: completed · updated: 2026-10-15

## Goal
Consolidate successful replacement solves when earlier failed attempts still carry valid scores, and retain retry verification failures without changing validity.

## Changes
- Add an opt-in replaceFailed contract, CLI flag and Web control. Default consolidation remains conservative.
- Permit a valid retry with a successful solve to replace a failed solve even when its earlier score was valid. Successful valid target solves remain protected.
- Retain an invalid retry only when its solve succeeded and the target has no valid current or historical score. Preserve the outcome, run IDs and artifacts.
- Reject pruning with this mode and duplicate source slots. Keep preview read-only and all existing compatibility, terminal-state, cleanup and ownership checks.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Consolidation tests | working tree | passed | 11 tests with explicit terminal-record fixtures and real HTTP paths |
| pnpm verify | working tree | passed | 197 Orbit, 11 Web and 5 script tests; 10 opt-in tests skipped; formatting, types, boundaries and builds passed |
| Daemon integration | 40bdf4b | passed | Read-only preview, apply, unchanged unrelated slots, retained artifacts and source ownership verified through the live daemon |

## Next / open issues
- This operation does not reclassify historical evaluation validity or diagnose network stalls.
