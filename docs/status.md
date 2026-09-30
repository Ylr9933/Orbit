# Orbit status

- **Updated at:** 2026-09-30T15:40:00+08:00
- **Basis:** branch `refactor/ts-rewrite` (proposed state if merged into `main`)
- **Stage:** R0 validated; R1 single-node research loop and R2 auth profiles + notifications implemented
  and validated on this machine (Codex and Claude Code). Not yet merged or run in CI.
- **Blockers:** none.

## Available

- `pnpm verify`: Biome, tsc, module boundaries (orbit + web), vitest, web + CLI build.
- Auto-started local daemon (127.0.0.1, token/cookie, sqlite); `orbit run / sweep / ps / show / logs /
  wait [-g] / cancel / note / resources / doctor / web / auth / notify`.
- Resource leases with a queue (with reasons); external GPU use is respected.
- Docker executor: code snapshot (commit + uncommitted changes), CDI GPU mapping checked against the
  lease, host user, timeouts; logs, metrics and outputs collected before cleanup, also on failure.
- Session linking for Claude Code and Codex (incl. nested agents). Web UI: runs, run detail (timeline,
  logs, metrics, artifacts, diff, session, events), compare with seed aggregation, resources, settings.
- Auth profiles (login / api-key / relay) for Codex and Claude Code in containers: host CLIs mounted
  read-only, secrets via env-file, redacted logs, `orbit auth test`. Notifications (Feishu, DingTalk,
  WeCom, Slack, webhook) per run and per group; Web Settings page and browser notifications.
- `plugin/skills/orbit/SKILL.md` for Codex and Claude Code.

## Main gaps

- Untried for lack of credentials: Codex api-key/relay, Claude Code login/api-key in containers; real
  IM webhook delivery. No MCP server, dataset registry (use `-m`) or bench (R3).
- `claude plugin install` from the marketplace manifest not tried end to end; CI not run.

## Next priorities

1. Review and merge `refactor/ts-rewrite`; run CI.
2. R3: bench (ASI wrapper, TB-Science Harbor format) on the same runs and leases.

## Records

[design.md](design.md) · [R0](tasks/20260929-ts-rewrite-r0.md) · [R1](tasks/20260930-r1-research-loop.md) ·
[R2](tasks/20260930-r2-auth-notify.md)
