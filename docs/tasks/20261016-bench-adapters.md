# Bench and adapter correctness
branch: fix/opt2-bench-adapters · status: completed · updated: 2026-10-15

## Goal
Keep benchmark model paths, credentials, judge errors, failure classification and timeouts consistent; reject malformed API queries and wait for large groups.

## Changes
- PostTrainBench uses each method's collected model path; only native gets dotenv and the full checkout. ResearchClawBench reports errors from every judge attempt.
- Shared Agent failure eligibility and issue formatting across progression, scoring and consolidation; preserve OOM/service issues and recovered-turn guards.
- Resolve solve timeout before adapter planning and enforce CLI > task > default > adapter precedence; Harbor verifier modes share command/output capture.
- Group wait requests 10000 runs; invalid file escapes and unsafe query integers return 400; benchmark route reuses parsed input.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Adapter Python unittests | working tree | passed | 10 tests; system Python and temporary fixtures; included in Vitest |
| Targeted TypeScript regressions | working tree | passed | Adapter planning, Agent classification/consolidation, verifier capture, CLI and local HTTP; explicit execution fakes |
| pnpm verify | working tree | passed | 267 Orbit, 12 Web and 5 script tests; 10 opt-in skipped; types, boundaries and builds passed; snapshot passed without retry; existing lint/build warnings remain |
| Real Docker/GPU/Agent integrations | working tree | not_run | Excluded by batch scope; offline command fixtures and temporary homes only |

## Next / open issues
Ready for runner review and commit. No live installation or stored runs changed; real benchmark smoke checks remain an operator check. ASI uses the resolved timeout for both the runner and solve Run, without the previous extra 15 minutes.
