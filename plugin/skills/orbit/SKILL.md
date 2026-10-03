---
name: orbit
description: Run experiments (training, evaluation, sweeps, any GPU job) in isolated Docker containers with Orbit, and read back their logs, metrics and outputs. Use whenever you would otherwise run a long or GPU job directly on the host, launch several seeds or hyperparameter settings, or need to check, compare or explain earlier experiment runs.
---

# Orbit: run and record experiments

Orbit runs your command in a Docker container on a snapshot of the current git repository, under a
GPU/CPU/memory lease, and keeps logs, metrics, outputs, the code diff and a link to this session.
You keep planning, editing and analysing; Orbit only executes and records. The human reviews the
runs in the Web UI (`orbit web`).

Use `orbit` instead of running experiments directly on the host, `nohup`, `tmux` or `docker run`.
Short checks (imports, a unit test, `--help`) can still run on the host.

## 1. Estimate resources before submitting

Pick the smallest request that fits; runs that cannot get resources **wait in the queue**, they do not fail.

| Flag | How to estimate |
| --- | --- |
| `--gpus N` | 0 for CPU-only work. 1 unless the code actually uses multiple GPUs (DDP, `device_map`, tensor parallel). |
| `--gpu-mem GB` | Minimum memory per GPU. Rough guide: fp16/bf16 inference ≈ 2 × params(B) GB + activations; full fine-tuning with Adam ≈ 16–20 × params(B) GB unless sharded/LoRA. |
| `--cpus N` | Data loader workers + 1–2. Default 4. |
| `--mem GB` | Host RAM: dataset held in memory + model loading peak (≈ weights size) + headroom. Default 16. |
| `--timeout MIN` | Set one for anything that could hang. |

Run `orbit resources` first to see free GPUs, their memory, active leases and the queue, on this
machine and on any worker nodes. State the estimate and its reasoning briefly to the user.

With worker nodes (`orbit node ls`), Orbit places each run on any node that fits: do not pick a node
yourself unless the user asks (`--node <name>`). Runs that mount a host path (`-m`) stay on this
machine; use `-d <dataset>` for data that should be usable on every node. Logs, metrics and
`orbit show` work the same for remote runs; `orbit show` names the node.

## 2. Submit

```bash
# one run; the repository at the current directory is snapshotted into /workspace
orbit run --image pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime --gpus 1 --mem 32 \
  -n baseline -- python train.py --lr 3e-4

# a sweep: one run per combination; {key} is substituted in the command
orbit sweep --image python:3.12-slim --gpus 1 -g lr-sweep \
  -p lr=1e-4,3e-4 -p seed=1,2,3 -- python train.py --lr {lr} --seed {seed}
```

- Put all options **before** `--`; everything after `--` is the command inside the container.
- Add `--json` (before `--`) to get machine-readable output with run ids.
- `--dockerfile path/Dockerfile` builds a project image instead of `--image` (cached by content).
- Uncommitted changes and untracked files are included in the snapshot, so you do not need to commit first. Large data and weights are not copied: prefer a registered dataset, `-d <name>` (mounted read-only at `/data/<name>`; see `orbit data ls`), or mount a host path with `-m /host/path:/data` (read-only; add `:rw` only if needed).
- `-e KEY=VALUE` for non-secret environment variables, `--pass-env VAR` for secrets; `--no-network` for offline runs; `-t key=value` for tags.
- Use `-g <group>` for runs that belong together (sweeps, ablations) so they can be compared.

## 3. Inside the container

| Path / variable | Use |
| --- | --- |
| `/workspace` | Code snapshot (writable copy; the host repo is not affected). Working directory. |
| `$ORBIT_METRICS` | Append one JSON object per line, e.g. `{"step": 100, "train/loss": 0.31, "eval/acc": 0.82}`. Use `step`; group keys with `/`. These become the curves in the Web UI. |
| `$ORBIT_OUTPUT` | Write results, predictions, plots and small checkpoints here. Kept after the run. |
| `$ORBIT_RUN_ID` | The run id. |

Print progress to stdout/stderr with `flush=True`; logs are kept in full, including for failed runs.
When the code you are writing has no metrics logging, add a few lines that write to `$ORBIT_METRICS`
if the variable is set.

## 4. Follow, wait and inspect

```bash
orbit ps                    # active runs (queued with the reason, running)
orbit ps -a -g lr-sweep     # everything in a group
orbit wait <id>... | -g lr-sweep   # blocks; exit code 1 if any run did not succeed
orbit logs <id> --tail 4000 # end of the log; -f to follow
orbit show <id>             # state, exit code, resources, code snapshot, last metric values
orbit cancel <id>...
```

Prefer `orbit wait` over polling. For long runs, you can continue other work and check back.
When a run fails, read `orbit logs <id> --tail 8000` before changing anything; the evidence is kept.

## 5. Run an agent inside a container

When the experiment itself needs Codex or Claude Code (agent benchmarks, agent-driven data work), use a
profile the human has set up; never pass keys yourself.

```bash
orbit auth list                              # names, agent, kind; secrets are never shown
orbit auth test <profile>                    # small real run: checks that the agent answers
orbit run --image python:3.12-slim --auth <profile> -n agent-try -- \
  codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox "task…"
orbit run --image python:3.12-slim --auth <profile> -- claude -p --dangerously-skip-permissions "task…"
```

The host's CLI is mounted read-only and put on `PATH`; the container is the sandbox. If no profile
fits, ask the human to add one (`orbit auth add`). Completion and failure notifications are sent to
the targets in `orbit notify list`; a group sends one summary when its last run ends.

## 6. Benchmarks

To evaluate a method on a registered benchmark, use `orbit bench`, not hand-written loops of runs:

```bash
orbit bench ls && orbit bench tasks <benchmark>          # unsupported tasks show the reason
orbit bench run <benchmark> -t <task> -m oracle -m empty -m mine=codex,auth=<profile>,model=<m> -n try
orbit bench show <job>                                   # per-method means, matrix, issues
orbit bench compare <job> <job>...                       # all-valid and paired means
```

Each trial is a solve run plus a separate verify run. Only `valid` trials count; read the issues of
`invalid` ones (environment or scorer failures, unusable model) instead of treating them as zeros.
Run `oracle` and `empty` first on a new benchmark or task set: oracle should score full, empty zero.

To add a benchmark Orbit does not know, write an adapter executable (any language; do not modify or
rebuild Orbit) and register it with `orbit bench add <name> <checkout> --adapter /abs/adapter.py
[-c key=value] [--pass-env JUDGE_KEY]`. Orbit runs `<adapter> tasks|solve|verify|score` in the checkout
with one JSON request on stdin and expects one JSON reply on stdout (non-zero exit + stderr on error):

- `tasks` → `{"tasks": [{"id", "title", "supported", "reason", "tags"}]}`
- `solve` (request has `trial.method`, `trial.task`, `trial.staging`) → `{"spec": run}`; for `codex` /
  `claude-code` methods give `"agentTask": {"instruction": "..."}` instead of `command` — Orbit builds the
  Agent CLI command, auth and bundle. Never write Agent CLI flags, `auth`, `passEnv` or `name` yourself.
- `verify` (request adds `solve.output`, the solve run's output dir) → `{"spec": run}`
- `score` (request adds `verify.output`) → `{"score", "maxScore", "invalid", "issues"}`; `invalid` only
  when the grader itself failed; "produced nothing" is a valid 0.

`run` uses `orbit run` fields (`image`/`dockerfile`, `resources`, `mounts`, `env`, `workdir`, `collect`,
`timeoutMin`, `backend: "process"`). Follow `docs/guides/bench-adapter.md` in the Orbit repository;
`examples/bench-adapters/researchclawbench/` is a complete example. Check with `-m empty` and compare a
sample against the benchmark's own scorer before real runs.

## 7. Record conclusions

After analysing a run or a group, attach a short note so the human sees it next to the results:

```bash
orbit note <id> "lr=3e-4 converges ~2x faster than 1e-4; seed std 0.01. Next: try warmup."
```

Tell the user the run ids and `orbit web <id>` for review.

## Rules

- Do not start experiment containers with `docker` directly, and do not stop containers or processes that Orbit or other users own; use `orbit cancel`.
- Do not request all GPUs "just in case". Do not work around the queue.
- Never put secrets in commands, tags or notes; pass them by name with `--pass-env VAR` (read from the daemon environment, never stored); `-e` values are stored with the run.
