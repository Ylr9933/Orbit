# Retain completed invalid retry attempts
branch: fix/bench-retain-invalid-retries · status: completed · updated: 2026-10-15

## Goal
Allow explicit consolidation of a failed retry into a target with no valid current or historical result, retaining its evidence and validity.

## Changes
- Extend existing replaceFailed semantics to retain invalid retries whose solve ended as succeeded or failed. Lost solves remain excluded.
- Preserve all validity, compatibility, cleanup, ownership and duplicate-slot guards; invalid attempts cannot overwrite valid current or historical scores.
- Clarify the existing contract, CLI help, client comment and Web confirmation. No new state or API field.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| pnpm verify | working tree | passed | 198 Orbit, 11 Web and 5 script tests; 10 opt-in tests skipped; checks and builds passed |
| Live daemon integration | working tree | passed | Preview and apply through the HTTP API; matrix, untouched trials, invalid outcomes, run ownership and retained artifacts verified; no file leftovers |

## Next / open issues
- Temporary integration daemon stopped after validation; original daemon entrypoint restored. Changes remain on the task branch, separate from concurrent work in the primary checkout.
