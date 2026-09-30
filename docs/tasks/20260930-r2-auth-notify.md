# R2: agent auth profiles and notifications

`refactor/ts-rewrite` · base `654bb86` (R1) · completed · 2026-09-30T15:40:00+08:00

## Goal

Acceptance (design §10): login / API key / relay profiles work for Codex and Claude Code inside run
containers; completion and failure notifications. Secrets stay out of argv, logs, records and git.

## Changes

- `auth/`: `AuthStore` (`~/.orbit/auth.json`, 0600, atomic writes). Public views carry only a masked
  hint. Codex logins are parsed and their tokens are known for redaction.
- `harness/`: finds the host Codex (npm vendor dir) and Claude Code binaries and mounts them read-only.
  - Writes `CODEX_HOME` / `CLAUDE_CONFIG_DIR` under `/orbit/agent`.
  - Maps each harness/kind to files and env (design §6).
  - After a run: writes back a refreshed Codex login, then deletes the credential files.
- `lib/redact.ts`: a `Redactor` for strings and streams, safe across chunk boundaries.
  - Run logs and failure reasons are redacted with every stored secret.
- `executor/docker.ts`:
  - Secret env goes through a 0600 `--env-file`, removed after `docker run`.
  - Network is `bridge | host | none`.
  - Redacting log follower.
- `runs/service.ts`:
  - `RunSpec.auth` / `hostNetwork` are validated at submit.
  - A `harness` event records the CLI version and profile; an `auth` event is added on write-back.
  - `testAuth` submits a real run in group `auth-test`.
- `notify/`: targets in `~/.orbit/notify.json` (Feishu, DingTalk, WeCom, Slack, webhook).
  - Ungrouped runs notify by result; cancelled runs do not.
  - A group sends one summary when its last run ends; `auth-test` is quiet.
  - Failure messages include a redacted 15-line log tail and a link to the run.
  - Send errors only reach the daemon log.
- API and CLI:
  - API routes: `auth`, `notify`.
  - CLI: `orbit auth add|list|rm|test` and `orbit notify add|list|rm|test`; `run/sweep --auth`, `--host-network`.
  - `auth add` sources: `--key-stdin`, `--key-env`, `--from`, `--from-env` (also reads Claude settings env), or `codex login --device-auth` into a temporary home.
  - `doctor` shows the host agent versions.
- Web:
  - Settings page: agent versions, profiles with Test/Delete, notification targets with Send test/Delete, and a browser-notification toggle. Secrets are never entered in the UI.
  - Overview shows the network mode and the agent auth profile.
  - Browser notifications fire while the page is open.
- Docs: design §3/§5/§6, README, SKILL.md §5, status.

## Validation

Real checks ran on this machine against a throwaway daemon (`ORBIT_HOME=/tmp/orbit-r2/home`,
`ORBIT_PORT=7792`) and a local webhook receiver on 127.0.0.1:18999. Revision: working tree on `654bb86`,
committed unchanged as this R2 commit.

| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | R2 working tree | passed | root 5, orbit 39 + 3 skipped, web 6 tests; boundaries with `notify` |
| `orbit doctor` | R2 working tree | passed | codex-cli 0.159.2, Claude Code 2.1.285 found |
| Claude Code relay: `auth add --from-env`, `auth test` | R2 working tree | passed | the agent answered `ORBIT_AUTH_OK` in about 7 s |
| Redaction in a run printing the relay token | R2 working tree | passed | the log shows `tok=[redacted]`; PATH prefixed with `/opt/orbit/claude`; harness event recorded |
| Codex login: `auth add --from ~/.codex/auth.json --host-network -e HTTPS_PROXY…`, `auth test` | R2 working tree | passed | about 30 s; approval never, sandbox danger-full-access; credential files removed after the run |
| Secret leak scan | R2 working tree | passed | 0 token matches in 320 files (runs, db, daemon log); `auth.json` 0600; tmp dir empty; no `orbit.run` containers left |
| Notifications: `notify test`; single succeeded run; single failed run; sweep of 3 runs (2 failed) | R2 working tree | passed | webhook + Feishu payloads received; failed message has a redacted tail; the group sent exactly one summary per target |
| Web Settings and run Overview (headless Chromium screenshots) | R2 working tree | passed | profiles and targets listed with masked hints; no console errors |
| Codex api-key, Codex relay, Claude Code login and api-key in a container | — | not_run | no credentials of these kinds available; covered by unit tests of the file/env mapping only |
| Real Feishu / DingTalk / WeCom / Slack delivery | — | not_run | only the local receiver; body error codes are handled per the vendors' documented format |
| CI | — | not_run | no CI run on this branch |

## Next / open issues

- A codex login copied with `--from` shares its refresh token with the source. When one side refreshes, the other may need to log in again. `auth add` without `--from` logs in separately. Concurrent runs with the same login profile can race on refresh; the last write-back wins.
- `docker inspect` of a running container shows the secret env; only local docker users can see this.
- `codex exec` inside the container logs `failed to refresh available models: request timed out`, but the run still works.
- The Web UI cannot add profiles or targets, by design.
- Next: review and merge `refactor/ts-rewrite`; R3 (bench).
