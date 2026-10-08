# Orbit status

- **Updated at:** 2026-10-08T19:00:00+08:00
- **Basis:** `main`
- **Stage:** R0–R2 validated here; R3 bench smoke-tested with oracle/empty only; R4 only as two daemons on one machine.
- **Blockers:** none.

## Available

- `pnpm verify` (Biome, tsc, boundaries, vitest, builds). Auto-started local daemon (127.0.0.1, token/cookie, sqlite); `orbit run / sweep / ps / show / logs /
  wait [-g] / cancel / note / resources / doctor / web / auth / notify / bench / node / data`.
- Resource leases with a queue (with reasons); use outside Orbit is respected (busy GPUs, measured CPU
  use, `MemAvailable`). Docker executor: code snapshot, CDI GPU mapping checked against the lease,
  timeouts; logs, metrics and outputs collected before cleanup. Process backend for native runners, with a labelling, GPU-limiting docker shim.
- Session linking; Web UI: runs, run detail, trial page, compare, resources, settings, bench; typed-confirmation deletion.
- Who holds each GPU (user, command, PID, container/Run, memory, runtime; else unknown) in Web and CLI.
- Pre-flight `orbit run|sweep --check` (data, output disk, image, placement); `--smoke '<cmd>'` gates submission.
- Data directory apart from `~/.orbit` (`orbit config data`, `ORBIT_DATA`), doctor disk warnings; logical folders (`--folder`, `mv`, `folders`, `export`).
- Auth profiles for Codex and Claude Code; notifications (Feishu, DingTalk, WeCom, Slack, webhook; `feishu-app` bot: `orbit feishu init` QR setup, pairing, read-only `/gpu` `/runs` `/show`, curve cards).
- Bench: solve + verify run per trial, valid-only means (OOM solves invalid); one JSON adapter protocol
  for built-ins and external executables (e.g. ResearchClawBench); per-task resources file; `bench usage`
  suggestions; `orbit-bench` skill; `bench rescore` re-verifies from saved solve outputs (history kept). Measured peak memory / CPU / GPU memory on every run. Adapter-declared
  metrics (`score` built in): per-task then over-task means, task-clustered 95% CI, paired Δ in compare.
- Multi-node: workers join by token; placement across nodes, code bundles by hash, named datasets,
  mirrored logs/metrics, proxied artifacts. Guide: [guides/multi-node.md](guides/multi-node.md).

## Main gaps

- ASI / TB-Science not checked against originals. R4 not run on two real machines; no bundle cache eviction.
- Per-user daemons on one machine (busy 7717 → free port) can lease the same free GPU at once; fix when needed with a shared per-GPU lock.
- Bench metrics: tests and fake adapters only; group notifications may fire between solve and verify. Untried: some auth kinds, real IM webhooks (the Feishu app was checked on a phone). No MCP server; no overcommit.

## Next priorities
1. Real Agent bench jobs (RCB first), Web `/bench`, R4 on two machines; review, merge.
2. Original-parity check on sampled ASI and TB-Science tasks.

## Records

[design.md](design.md) · [R0](tasks/20260929-ts-rewrite-r0.md) · [R1](tasks/20260930-r1-research-loop.md) · [R2](tasks/20260930-r2-auth-notify.md) ·
[R3](tasks/20260930-r3-bench.md) · [R4](tasks/20260930-r4-multinode.md) · [review](tasks/20261001-code-review.md) · [cpu](tasks/20261002-cpu-external-load.md) ·
[adapters](tasks/20261003-bench-adapter-protocol.md) · [resources](tasks/20261003-bench-resources-usage.md) · [validity](tasks/20261004-bench-validity-checks.md) · [web](tasks/20261004-web-jobs-trials-delete.md) · [metrics](tasks/20261005-bench-metrics.md) · [folders](tasks/20261005-data-dir-folders.md) · [gpu-procs](tasks/20261006-gpu-processes.md) · [preflight](tasks/20261008-preflight-smoke.md) · [rescore](tasks/20261008-bench-rescore.md) · [feishu-app](tasks/20261008-feishu-app.md) · [feishu-init](tasks/20261008-feishu-init.md)
