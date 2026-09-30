# Orbit status

- **Updated at:** 2026-09-30T10:30:00+08:00
- **Basis:** branch `refactor/ts-rewrite` (proposed state if merged into `main`)
- **Stage:** R0 skeleton — implemented and validated on the branch; not yet merged

## Available

- TypeScript workspace (Node 24, pnpm); `pnpm verify` runs Biome, tsc, the boundary check,
  vitest and the tsdown build.
- Local daemon on 127.0.0.1 with token auth; the CLI starts it automatically.
- `orbit resources [--json]`: real GPUs (nvidia-smi, busy when external use exceeds 1 GiB), CPU,
  memory, disk.
- `orbit doctor [--json]`: node, git, docker, nvidia-smi.

## Main gaps (R1: single-node research loop)

- No sqlite store, leases, queue, Docker executor, code snapshot, records or Web UI yet.
- No plugin/skill for Codex or Claude Code yet.

## Next priorities

1. R1: store + resource leases + Docker executor + `orbit run / ps / logs / wait / cancel`.
2. R1: code snapshot, metrics/artifact collection, and a Codex/Claude Code skill.
3. R1: minimal Web review (runs, diff, curves, logs).

## Blockers

- None.

## Records

- [docs/design.md](design.md)
- [tasks/20260929-ts-rewrite-r0.md](tasks/20260929-ts-rewrite-r0.md)
