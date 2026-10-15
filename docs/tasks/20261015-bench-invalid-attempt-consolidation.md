# Retain completed invalid retry attempts
branch: fix/bench-retain-invalid-retries · status: completed · updated: 2026-10-15

## Goal
Allow explicit consolidation of a failed retry into a target with no valid current or historical result, retaining its evidence and validity.

## Changes
- Extend existing replaceFailed semantics to retain invalid retries whose solve ended as succeeded or failed. Lost and cancelled solves remain excluded.
- Preserve all validity, compatibility, cleanup, ownership and duplicate-slot guards; invalid attempts cannot overwrite valid current or historical scores.
- Clarify the existing contract, CLI help, client comment and Web confirmation. No new state or API field.
- Integrate the original branch into the current split planner and Web merge dialog; retain preview digests, newly invalid evidence guards and main's module boundaries.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Consolidation regressions | integrated working tree | passed | 46 tests; explicit completed-record fixtures with real store, HTTP and filesystem paths; valid results/history protected, lost/cancelled solves rejected |
| pnpm verify | integrated working tree | passed | 365 Orbit, 26 Web and 5 script tests; 10 opt-in checks skipped; formatting, types, boundaries and builds passed |
| pnpm smoke:package | integrated working tree | passed | Isolated installed CLI/npx, exports/types, real daemon HTTP, Web/assets/licenses; doctor passed 9 real prerequisite checks |
| Docker/GPU/model experiment | — | not_run | Completed-record consolidation only; no executor, authentication or Agent CLI changes |

## Next / open issues
- No remaining issues for this change.
