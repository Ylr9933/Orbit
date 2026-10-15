# Security hardening
branch: fix/opt3-security · status: completed · updated: 2026-10-15

## Goal
Close the browser-login, artifact-read, live-log, state-permission, webhook-input and bundle-upload gaps in optimization batch 3.

## Changes
- Bearer-only, single-use 30-second login codes for browser launch; token links remain usable for terminal copy/paste. Reject normalized network-path redirects.
- Serve verified output file descriptors in daemon and worker, closing on completion, cancellation and HEAD; redact live log windows and defer polling when trailing bytes are withheld.
- Create private state directories/database files; tighten only named existing Orbit paths at startup and warn in doctor when still insecure.
- Add webhook URL stdin input and argv warning; normalize container paths before reserved/duplicate checks; bound compressed and unpacked bundle streams.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Focused regressions | working tree based on ea85a98 | passed | Temporary files; explicit CLI/run-service/probe doubles; covers expiry/reuse, redirects, fd lifetime, split secrets, permissions, normalized paths and upload limits |
| HTTP login and startup permissions | working tree | passed | Real HTTP/SQLite in a temporary daemon home; Docker/GPU commands use explicit PATH doubles |
| `pnpm verify` | working tree | passed | 309 Orbit + 13 Web + 5 script tests; 10 opt-in Docker/GPU tests skipped; format/lint/types/boundaries/build pass |
| Snapshot regression during verification | working tree | failed | Once omitted a tracked changed file under load; unmodified test passed alone (3/3), then full verify passed |
| Real browser / Docker / GPU / webhook services | working tree | not_run | Browser launch uses a CLI double; live Docker/GPU and external services excluded by batch instructions |

## Next / open issues
Runner commits the reviewed working tree using `/tmp/orbit-opt-commit.txt`. Manual browser launch remains an operator check; existing group/ACL access to the named private state paths is intentionally revoked.
