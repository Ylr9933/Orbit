# Orbit status

- **Updated at:** 2026-09-30T16:45:00+08:00
- **Basis:** branch `refactor/ts-rewrite` (proposed state if merged into `main`)
- **Stage:** R0 validated; R1 research loop and R2 auth + notifications validated on this machine;
  R3 bench implemented, smoke-tested with oracle/empty only. Not yet merged or run in CI.
- **Blockers:** none.

## Available

- `pnpm verify`: Biome, tsc, module boundaries (orbit + web), vitest, web + CLI build.
- Auto-started local daemon (127.0.0.1, token/cookie, sqlite); `orbit run / sweep / ps / show / logs /
  wait [-g] / cancel / note / resources / doctor / web / auth / notify / bench`.
- Resource leases with a queue (with reasons); external GPU use is respected.
- Docker executor: code snapshot, CDI GPU mapping checked against the lease, timeouts; logs, metrics
  and outputs collected before cleanup. Process backend for native runners, with a docker shim that
  labels child containers, limits GPUs to the lease and injects agent auth.
- Session linking; Web UI: runs, run detail, compare, resources, settings, bench jobs / matrix / compare.
- Auth profiles (login / api-key / relay) for Codex and Claude Code; notifications (Feishu, DingTalk,
  WeCom, Slack, webhook).
- Bench: trials = solve run + separate verify run; execution / evaluation / cleanup kept apart; only
  valid scores in means (all-valid and paired). Harbor adapter (TB-Science) and ASI native wrapper.
  Guide: [guides/bench-adapter.md](guides/bench-adapter.md). Agent skill: `plugin/skills/orbit/SKILL.md`.

## Main gaps

- Bench not yet run with real Agents (Codex / Claude Code); parity with the original pipelines on
  sampled Agent results not checked. Bench Web pages not yet tried in a browser.
- Group notifications may fire between a trial's solve and verify runs. Untried: some auth kinds, real
  IM webhook delivery. No MCP server. CI not run.

## Next priorities

1. User testing of R3 (real Agent bench jobs, Web `/bench`), then review and merge; run CI.
2. Original-parity check on sampled ASI and TB-Science tasks.

## Records

[design.md](design.md) · [R0](tasks/20260929-ts-rewrite-r0.md) · [R1](tasks/20260930-r1-research-loop.md) ·
[R2](tasks/20260930-r2-auth-notify.md) · [R3](tasks/20260930-r3-bench.md)
