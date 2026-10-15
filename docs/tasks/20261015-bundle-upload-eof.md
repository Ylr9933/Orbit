# Drain bundle uploads through EOF
branch: fix/merge-invalid-retries · status: completed · updated: 2026-10-15

## Goal
Prevent valid bundle uploads from failing with premature stream closure when tar reaches archive end markers before the input pipeline finishes.

## Changes
- Keep tar reading archive padding until EOF; retain compressed/unpacked byte limits, upload errors, hash validation and staging cleanup.
- Reproduce the race with real tar/gzip and delayed trailing padding, without process or stream fakes.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Regression before fix | edf1391 plus regression | failed | Expected failure: delayed padding reproduces the premature close reported by CI |
| Regression after fix | working tree | passed | All 16 bundle/cluster tests, including delayed padding, size limits, bad hashes and upload errors; real tar/gzip and temporary files |
| pnpm verify | working tree | passed | 366 Orbit, 26 Web and 5 script tests; 10 opt-in Docker checks skipped; format, types, boundaries and build passed |
| pnpm smoke:package | working tree | passed | Isolated installed CLI/npx, exports/types, real daemon/Web/assets/licenses; doctor passed 9 real checks |

## Next / open issues
- No remaining issues for this fix. The separately observed snapshot changedFiles flake remains outside this change.
