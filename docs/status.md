# Orbit status

- **Updated at:** 2026-10-01T00:20:00+08:00
- **Basis:** branch `refactor/ts-rewrite` (proposed state if merged into `main`)
- **Stage:** R0–R2 validated on this machine; R3 bench smoke-tested with oracle/empty only; R4 multi-node
  validated only as two daemons on one machine. Not yet merged or run in CI.
- **Blockers:** none.

## Available

- `pnpm verify`: Biome, tsc, module boundaries (orbit + web), vitest, web + CLI build.
- Auto-started local daemon (127.0.0.1, token/cookie, sqlite); `orbit run / sweep / ps / show / logs /
  wait [-g] / cancel / note / resources / doctor / web / auth / notify / bench / node / data`.
- Resource leases with a queue (with reasons); external GPU use is respected. Docker executor: code
  snapshot, CDI GPU mapping checked against the lease, timeouts; logs, metrics and outputs collected
  before cleanup. Process backend for native runners, with a labelling, GPU-limiting docker shim.
- Session linking; Web UI: runs, run detail, compare, resources, settings, bench jobs / matrix / compare.
- Auth profiles (login / api-key / relay) for Codex and Claude Code; notifications (Feishu, DingTalk,
  WeCom, Slack, webhook).
- Bench: solve run + separate verify run per trial; only valid scores in means. Harbor adapter
  (TB-Science), ASI native wrapper. Guide: [guides/bench-adapter.md](guides/bench-adapter.md).
- Multi-node: workers join by token; placement across nodes, code bundles by hash, named datasets,
  mirrored logs/metrics, proxied artifacts. Guide: [guides/multi-node.md](guides/multi-node.md).

## Main gaps

- Bench not run with real Agents or checked against the originals. R4 not run on two real machines;
  no bundle cache eviction. Web bench / node pages not tried in a browser.
- Group notifications may fire between solve and verify. Untried: some auth kinds, real IM webhooks.
  No MCP server. CI not run.

## Next priorities

1. User testing of R3 (real Agent bench jobs, Web `/bench`) and R4 on two machines; review, merge, CI.
2. Original-parity check on sampled ASI and TB-Science tasks.

## Records

[design.md](design.md) · [R0](tasks/20260929-ts-rewrite-r0.md) · [R1](tasks/20260930-r1-research-loop.md) ·
[R2](tasks/20260930-r2-auth-notify.md) · [R3](tasks/20260930-r3-bench.md) · [R4](tasks/20260930-r4-multinode.md)
