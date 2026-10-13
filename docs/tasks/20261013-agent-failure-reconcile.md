# Reconcile terminal Agent failures before consolidation
branch: fix/bench-agent-error-reconcile · status: completed · updated: 2026-10-13

## Goal
Prevent model routing failures from becoming valid zero scores and let valid retries replace historically misclassified trials.

## Changes
- Recognize routing-discovery timeouts and revoked OAuth credentials as Agent setup failures.
- Consolidation rereads terminal Agent errors for failed solves and corrects local outcome/history validity before applying the existing replacement guard. Raw scores are retained.
- Reload job state after asynchronous session reads; recheck terminal state, ownership and cleanup before mutation. Preview remains read-only; genuinely valid outcomes and recovered errors remain protected.
- CLI/Web explain the recheck; the typed API contract is unchanged.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Targeted tests | working tree | passed | 14 consolidation/session tests; explicit fixtures with real store and HTTP paths |
| pnpm verify | working tree | passed | 194 Orbit, 11 Web and 5 script tests; 10 opt-in checks skipped; types, boundaries and builds passed |
| Stored session integration | 8911aba | passed | Daemon preview recognized terminal routing errors; apply adopted valid retries and preserved unrelated trials |

## Next / open issues
- Error classification remains conservative and message-based; unknown errors are not blanket-reclassified.
