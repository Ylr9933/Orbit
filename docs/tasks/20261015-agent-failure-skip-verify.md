# Skip verification when the Agent could not use its model
branch: fix/bench-agent-failure-skip-verify · status: completed · updated: 2026-10-15

## Goal
A solve whose Agent never reached or could not use its model must not become a valid zero, and should
not spend a verify run. Works for every adapter, not per benchmark.

## Changes
- `harness.agentErrorKind(text, code?)`: structured codes first (Codex `codex_error_info`, including
  `{ http_connection_failed: { http_status_code } }`; Claude Code assistant `error`), then text. Added
  `workspace routing discovery failed`, missing bearer, expired OAuth, Claude limit/overload/connection
  errors, model at capacity, 429 retry exhaustion, `waiting for network`.
- `sessions.runAgentFailure(agentDir, log?)`: tracks whether the last Codex turn completed; an
  incomplete turn counts only when the run log ends with `ERROR: Reconnecting...` (stopped mid-retry).
  Recovered errors and ordinary experiment failures still do not count.
- Bench: on such a failure the trial ends `invalid` with `verify skipped` and no verify run. After-phase
  verification and explicit rescore still score (score kept, invalid). Consolidation also turns
  `unknown` into `invalid` for these and reports `reclassified` (contract, CLI and Web confirm text).

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Targeted tests | working tree | passed | harness codes/texts, open-turn log tail, classify, consolidate without sources, daemon skip-verify + rescore (fake process adapter) |
| pnpm verify | working tree | passed | 200 Orbit, 11 Web, 5 script tests; 10 opt-in skipped. One earlier run had a flaky `snapshot.test.ts` failure that passed alone and on rerun |
| Stored sessions on this machine | working tree | passed | read-only replay of `runAgentFailure` over local run dirs: routing-failed, 401 and reconnect-at-timeout runs detected; no daemon state changed |

## Next / open issues
- Detection of an incomplete turn relies on Codex's stderr format; Claude Code has no equivalent yet.
- dsh / pi are host plugins only (no in-container harness), so they have no session rules.
- Existing jobs keep their marks until `orbit bench consolidate <job>` (preview, then `--apply`).
