# R4: multi-node placement

`refactor/ts-rewrite` · base `edd7fff` (R3) · completed (pending user testing; not validated on two real machines) · 2026-10-01T00:20:00+08:00

## Goal

Acceptance (design §10): one Agent schedules two machines / 8 GPUs. Design §8: a daemon on every
machine; the Agent's node is the primary; workers join by token (Tailscale or direct); code snapshots
travel by content hash and are cached; datasets are name → local path and never moved; logs and
metrics flow back; large artifacts stay on their node; no Ray.

## Changes

- `cluster/`: node registry and expose config (`nodes.json`, `cluster.json`, 0600), `NodeClient`,
  the worker API under `/cluster/v1` (bearer cluster token, separate from the daemon token), and
  `ClusterService` (heartbeat, bundle upload, dispatch, mirror sync of state / events / log /
  metrics, cancel forwarding, artifact proxy, listener).
- `runs/placement.ts` + `runs/service.ts`: placement local first, then online workers by name;
  per-node queue reasons; predicted leases for dispatched runs; `remote` / `origin` on Run; worker-side
  `submitRemote`; recovery re-dispatches unconfirmed runs. `runs` does not import `cluster`.
- `workspace/bundle.ts` (tree hash, tar pack / verified receive, cache `cache/bundles/<hash>`),
  `workspace/datasets.ts` (named datasets). Mount = `source` or `dataset`.
- Store migration 3: `remote_sync`. Paths: `ORBIT_NODE`, `ORBIT_GPUS`. Probe filters GPUs.
- API: `cluster/nodes`, `cluster/expose`, `cluster/token[/rotate]`, `datasets`; `/ledger.nodes`.
- CLI: `orbit node ls|add|rm|expose|token`, `orbit data ls|add|rm`, `orbit run --node`, `-d/--dataset`;
  `resources` / `ps` / `show` show nodes. Web: worker node table on Resources, node on run Overview,
  dataset mounts.
- Bench runs and `auth test` are pinned to the local node. Boundaries: cluster may use workspace and records.
- Docs: design §2–§5, §8, §10; [guides/multi-node.md](../guides/multi-node.md); README; skill.

## Validation

| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | d64c274 + docs/format fix | passed | orbit 72 passed / 3 skipped (Docker E2E opt-in), web 6 passed |
| `test/cluster.test.ts` | d64c274 | passed | tree hash, tar round trip and hash mismatch, placement rules, predicted leases, env, listen/dataset parsing, token check, dataset registry |
| `test/cluster.daemon.test.ts` | d64c274 | passed | two in-process daemons, fake `docker` on PATH: token auth, node add, rejection reasons, snapshot bundle transfer, dispatch, mirrored failure, node removal |
| Same-host emulation: 2 daemons, GPUs 0,1 / 2,3, real Docker + GPUs | d64c274 | passed | 6-run 1-GPU sweep spread 2+2 with 2 queued (reasons per node), all succeeded; remote runs got a worker GPU matching the lease and the worker's copy of a same-name dataset; logs/metrics mirrored; artifacts list and file read through the primary; remote cancel removed the container; worker daemon stopped mid-run → node offline, restarted → run completed, mirrored log byte-identical; no containers left; daemons stopped by pid |
| Two real machines over Tailscale / LAN | — | not_run | only one machine available; emulation shares Docker, filesystem and clock |
| Web pages in a browser | — | not_run | typecheck and build only |

## Next / open issues

- Validate on two real machines (8 GPUs), including network loss and a worker reboot.
- No bundle cache eviction; mirrors of an offline worker stay in their state until it returns or is
  removed; mirrored logs may be re-fetched after a worker restart; plain HTTP (use Tailscale / SSH tunnel).
- `passEnv` on a worker comes from the worker daemon's environment and is not checked at placement.
