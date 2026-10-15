# ResearchClawBench adapter

An Orbit bench adapter for [ResearchClawBench](https://github.com/InternScience/ResearchClawBench)
(protocol: [design §7](../../../docs/design.md#7-刷榜bench)). It uses the benchmark checkout as is:
the original instruction template for the Agent and the original `evaluation.score.score_run` for the
judge.

```bash
# judge credentials from the daemon environment (or -c dotenv=1 to read evaluation/.env)
orbit bench add rcb /path/to/ResearchClawBench \
  --adapter /path/to/examples/bench-adapters/researchclawbench/adapter.py \
  --resources /path/to/ResearchClawBench/orbit/resources.json \
  --pass-env OPENAI_API_KEY --pass-env OPENAI_BASE_URL --pass-env SCORER_MODEL
orbit bench tasks rcb
orbit bench run rcb -t Astronomy_000 -m empty -n smoke
orbit bench run rcb -t Astronomy_000 -m gpt=codex,auth=<profile>,model=<model>,bundle=/path/to/skills-bundle
```

- **Solve**: a container from `rcb-solve/Dockerfile` (Ubuntu 22.04, the system Python 3.10 the RCB venvs
  were made from). The workspace is `/task`: `data/` and `related_work/` read-only, `code/`, `outputs/`,
  `report/` writable, collected into the solve run's output when it ends. `<path>/.venv-rcb-*` are
  mounted read-only at their host paths, so skills that name them work unchanged.
- **Verify**: a host process in `<path>/.venv` running `judge.py`, which links the collected files into a
  workspace in its own output and calls `score_run` (`_score.json` is kept there).
- **Score**: `total_score` (0–100; about 50 matches the paper), the mean over `attempts`. No report is a
  valid 0; a failed judge call or a judge error makes the trial invalid. Metrics: `score` (the total, in
  pts, with the paper level 50 as reference line), `matched` (trials scoring at least 50) and, with
  `attempts` > 1, `judgeSpread` (sample std of the judge totals). There is no reference
  solution, so `oracle` is refused.

Settings (`-c KEY=VALUE`) are listed at the top of `adapter.py`. Per-task solve resources come from
the resources file (`--resources`; see the bench adapter guide); `-c cpus/memGB/gpus/timeoutMin` only
set the adapter's own defaults for tasks the file does not cover.

## Adapter tests

From the Orbit repository root:

```bash
python3 -B -m unittest discover -s examples/bench-adapters/researchclawbench
```

The tests use temporary fixtures and the system Python, including errors on later judge attempts.
They also run under `pnpm verify`; no benchmark checkout, model API or containers are needed.
