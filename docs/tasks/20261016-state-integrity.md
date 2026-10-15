# State and data integrity
branch: fix/opt1-state-integrity · status: completed · updated: 2026-10-15

## Goal
Prevent uncommitted notifications, duplicate daemons, partial bench writes and unintended evidence loss.

## Changes
- Store savepoints and commit callbacks; newer database rejection; startup trial cleanup reconciliation.
- Process-owned daemon and CLI spawn locks, including stale owner recovery; port fallback retained.
- Atomic job submission; adapter process-group deadlines; staging failures logged; failed exports skipped.
- Consolidation preview digests carried by CLI/Web; newly invalid trials retain their evidence until a later call.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Focused regressions | batch commit | passed | SQLite, process locks, local HTTP, adapter descendants, fault injection and consolidation |
| pnpm verify | batch commit | passed | Format/lint, types, boundaries, tests and both builds; offline Docker/GPU fixtures; snapshot test passed without retry |
| Real Docker/GPU/services | batch commit | not_run | Excluded by batch scope; temporary homes and explicit offline command fixtures only |

## Next / open issues
Manual Web interaction remains untested; API/CLI preview matching is covered. No live daemon or data migration performed.
