# Cross-adapter timeout classification
branch: fix/bench-timeout-classification · status: completed · updated: 2026-10-09

## Goal
Integrate zjunlp/Orbit PR #1, audit the remaining bench adapters, fix shared false
execution timeouts, and synchronize the local checkout and XuehaiWang/orbit.

## Changes
- PR #1 merged as `dcfd36f`; local `main` fast-forwarded.
- Harbor/TB-Science and ResearchClawBench use Orbit's direct Agent command and do
  not classify execution by searching logs. ASI uses its native runner, guarded by PR #1.
- Shared Docker/process watchers disarm execution deadlines before collecting
  evidence or final usage. Recovery only arms deadlines for still-running tasks;
  daemon shutdown clears its timers. Cleanup and lease release keep their existing order.
- Bench classification and usage statistics share the scheduler-reason match,
  so unrelated errors containing timeout do not discard scores or inflate timeout counts.
- Add real Docker/process checks for successful/nonzero exits crossing the deadline
  during deliberately delayed collection, plus genuine timeouts. Logs include timeout
  warnings. Docker IO and processes are real; only collection latency is injected.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| PR #1 CI and local `pnpm verify` | `4c6e032` | passed | All required checks and builds |
| New delayed-collection regressions before fix | `dcfd36f` + tests | failed (expected) | Real Docker exits 0 and 7 both mislabeled timeout; teardown also exposed an async measurement race, handled by waiting for measurements in the fixture |
| Recovery regressions before fix | `dcfd36f` + tests | failed (expected) | All four fake-executor recovery cases reproduced the false timeout |
| `pnpm verify` | `dcfd36f` + patch | passed | 189 tests; 10 opt-in execution tests skipped here; format/lint, types, boundaries and builds passed |
| `ORBIT_E2E=1` Docker/process suite | `dcfd36f` + patch | passed | 10 checks, including 4 delayed-collection regressions, 2 genuine timeouts, failure evidence and cancellation; all leases released and containers removed; CPU only |
| Recovery checks | `dcfd36f` + patch | passed | 4 explicit fake-executor cases: Docker/process, exits 0/7, recovery after deadline |
| GPU/model/scorer benchmark execution | — | not_run | No GPU or model behavior changed; timeout lifecycle checked with real CPU Docker/process runs |

## Next / open issues
- Verified branch: `fix/bench-timeout-classification`; authorized integration targets:
  zjunlp/Orbit `main`, local `main`, and XuehaiWang/orbit `main`.
- ASI users still need a compatible registered source checkout; no npm release or
  model/scorer rerun is part of this change.
