# ASI-Bench adapter (BM02-B)

This independent adapter runs one already-materialized public `seed31415`
instance through the pinned native ASI-Bench runner, then calls ASI-Bench's
`BenchFlow` scorer on the persisted attempt. Agent Infra schedules the process,
captures evidence, and owns only the outer process group. ASI-Bench remains the
authority for instance semantics, prompt levels, result layout, gates, and scores.

The initial engineering profile admits the model-free `fixture` agent, one task,
one prompt level, `--sandbox none`, no retries, and no external tools. It proves
the native produce/score boundary without spending model or GPU resources. It is
not a leaderboard profile.

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
