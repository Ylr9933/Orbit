# Orbit status

- **Updated at:** 2026-10-04T14:10:00+08:00
- **Basis:** branch `refactor/ts-rewrite` (proposed state if merged into `main`)
- **Stage:** R0–R2 validated on this machine; R3 bench smoke-tested with oracle/empty only; R4 multi-node
  validated only as two daemons on one machine. Review fixes applied. Not merged; CI runs `pnpm verify`.
- **Blockers:** none.

## Available

- `pnpm verify`: Biome, tsc, module boundaries (orbit + web), vitest, web + CLI build.
- Auto-started local daemon (127.0.0.1, token/cookie, sqlite); `orbit run / sweep / ps / show / logs /
  wait [-g] / cancel / note / resources / doctor / web / auth / notify / bench / node / data`.
- Resource leases with a queue (with reasons); use outside Orbit is respected (busy GPUs, measured CPU
  use, `MemAvailable`). Docker executor: code snapshot, CDI GPU mapping checked against the lease,
  timeouts; logs, metrics and outputs collected before cleanup. Process backend for native runners, with a labelling, GPU-limiting docker shim.
- Session linking; Web UI: runs (with bench job / trial rows), run detail, trial page (report, grader,
  session), compare, resources, settings, bench. Typed-confirmation deletion of runs and jobs.
- Auth profiles (login / api-key / relay) for Codex and Claude Code; notifications (Feishu, DingTalk,
  WeCom, Slack, webhook).
- Bench: solve + verify run per trial, valid-only means (OOM solves invalid); one JSON adapter protocol
  for built-ins and external executables (e.g. ResearchClawBench); per-task resources file; `bench usage`
  suggestions; `orbit-bench` skill. Measured peak memory / CPU / GPU memory on every run.
- Multi-node: workers join by token; placement across nodes, code bundles by hash, named datasets,
  mirrored logs/metrics, proxied artifacts. Guide: [guides/multi-node.md](guides/multi-node.md).

## Main gaps
- ASI / TB-Science not checked against originals. R4 not run on two real machines; no bundle cache eviction.
- Group notifications may fire between solve and verify; Harbor has no model-error invalidation.
  Untried: some auth kinds, real IM webhooks. No MCP server. Resource requests = limits (no overcommit).

## Next priorities
1. Real Agent bench jobs (RCB first), Web `/bench`, R4 on two machines; review, merge.
2. Original-parity check on sampled ASI and TB-Science tasks.

## Records

[design.md](design.md) · [R0](tasks/20260929-ts-rewrite-r0.md) · [R1](tasks/20260930-r1-research-loop.md) · [R2](tasks/20260930-r2-auth-notify.md) ·
[R3](tasks/20260930-r3-bench.md) · [R4](tasks/20260930-r4-multinode.md) · [review](tasks/20261001-code-review.md) · [cpu](tasks/20261002-cpu-external-load.md) ·
[adapters](tasks/20261003-bench-adapter-protocol.md) · [resources](tasks/20261003-bench-resources-usage.md) · [web](tasks/20261004-web-jobs-trials-delete.md)
