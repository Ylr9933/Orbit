# Orbit status

- **Updated at:** 2026-09-30T11:50:00+08:00
- **Basis:** branch `refactor/ts-rewrite` (proposed state if merged into `main`)
- **Stage:** R0 validated; R1 single-node research loop implemented and validated on this machine
  (Codex and Claude Code). Not yet merged or run in CI.

## Available

- `pnpm verify`: Biome, tsc, module boundaries (orbit + web), vitest, web + CLI build.
- Local daemon (127.0.0.1, token/cookie auth, sqlite store) started automatically by the CLI.
- `orbit run / sweep / ps / show / logs / wait [-g] / cancel / note / resources / doctor / web`.
- Resource leases with a queue (queued runs show the reason); external GPU use is respected.
- Docker executor: code snapshot (commit + uncommitted changes), CDI GPU mapping checked against the
  lease, host user, timeouts; logs, metrics and outputs collected before cleanup, also on failure.
- Session linking for Claude Code and Codex (including nested agents), shown in the Web UI.
- Web UI: runs, run detail (timeline, logs, metrics, artifacts, diff, session, events), compare with
  seed aggregation, resources.
- `plugin/skills/orbit/SKILL.md` for Codex and Claude Code.

## Main gaps

- No MCP server, notifications or auth profiles (R2); no named dataset registry (mount paths with `-m`).
- `claude plugin install` from the marketplace manifest not tried end to end; CI not run (branch not pushed).

## Next priorities

1. Review and merge `refactor/ts-rewrite`; run CI.
2. R2: auth profiles for Codex / Claude Code inside containers; completion/failure notifications.

## Blockers

- None.

## Records

- [docs/design.md](design.md)
- [tasks/20260929-ts-rewrite-r0.md](tasks/20260929-ts-rewrite-r0.md)
- [tasks/20260930-r1-research-loop.md](tasks/20260930-r1-research-loop.md)
