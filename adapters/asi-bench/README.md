# ASI-Bench adapter

This independent adapter runs one already-materialized public `seed31415`
instance through the pinned native ASI-Bench runner, then calls ASI-Bench's
`BenchFlow` scorer on the persisted attempt. Agent Infra schedules the process,
captures evidence, and owns only the outer process group. ASI-Bench remains the
authority for instance semantics, prompt levels, result layout, gates, and scores.

The engineering profile `asi-bench` admits the model-free `fixture` agent, one task,
one prompt level, `--sandbox none`, no retries, and no external tools. It proves
the native produce/score boundary without spending model or GPU resources. It is
not a leaderboard profile.

The additional `asi-bench-codex-os` profile admits ASI-Bench's native
`codex_cli` agent in its `--sandbox os` Docker container. It requests the
pinned upstream OS defaults (4 CPU, 8 GiB, no GPU) and one public seed31415
instance. The host needs Docker, its image-build dependencies, and the current
user's private `~/.codex/auth.json`. The native task image installs Codex; this
adapter does not inject a host Codex binary. The profile is not a seed42 or
official-submission implementation.

Use `request-codex-os.json` and `capabilities-codex-os.json` for this profile,
after changing `tasks_dir` to the pinned checkout's `tasks/` directory. The
`candidate.model` and exact compatibility declaration must agree. If a local
HTTP(S) proxy is needed, set `proxy_url` and, for a loopback proxy, also set
`docker_network=host` in request parameters. These values are frozen in the
plan; no proxy credentials are supported.

The Codex profile copies result-referenced JSONL, stderr, native or derived
trajectory, and any available model-call file into a bounded `evidence/`
artifact. `evidence/index.json` states which files are complete, absent,
invalid, or truncated. It also records the Codex thread ID and turn/usage
evidence found in the JSONL. A task-owned Docker CLI shim labels the native
container and samples Docker stats; identity, limits, and samples are separate
from the outer host process's resource accounting. Sampling may be incomplete,
which is reported rather than silently treated as full coverage. The Web
benchmark page links a run and attempt to the native instance, prompt, Codex
session, trajectory steps, and Docker sample. It displays a bounded projection;
the raw evidence stays in Records.

Local public scores always carry `official: false`. Official `seed42` evaluation
is external: run with ASI-Bench's required Docker OS sandbox, build and inspect a
native submission bundle, then use ASI-Bench's authenticated submission flow.
This adapter never reads private references, uploads a bundle, or turns a local
score into an official score.

Install this directory in an isolated Python 3.12 environment together with the
repository root. Enable it through an operator-reviewed allowlist:

```bash
agent-infra benchmark adapters --config adapters/asi-bench/adapters.toml
agent-infra benchmark inspect --config adapters/asi-bench/adapters.toml \
  --source /path/to/instances/math.task__seed31415 asi-bench
```

Discover an unchanged public instance directory, then use `request.json` after
replacing `tasks_dir` with the matching pinned ASI-Bench checkout. The standard
`benchmark plan`, `benchmark check`, `benchmark prepare`, and `benchmark run`
commands are the execution path. Native execution requires both explicit
`--allow-host-process` and `--allow-native-runtime` acknowledgement flags.

For `seed42`, `python -m agent_infra_asi_bench.bundle --results-dir RESULTS
--output-dir BUNDLE` validates native seed/provenance rules and creates an
unarchived local bundle. It performs no authentication, browser action, or upload.
