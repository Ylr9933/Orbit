# PAST-Bench adapter (BM03)

This optional package maps one pinned PAST-Bench v2 family to one atomic
`paired_sequence`. PAST-Bench remains responsible for manifest generation, episode order,
fresh sessions, history anchors, persistence on/off, grading and aggregation. Agent Infra
queues the complete pair, supervises the outer process, and archives native evidence.

The default request is a model-free engineering profile. It uses the pinned native manifest,
state branch primitives and aggregation functions, but does not run an Agent and is never an
official score. Native mode supports the upstream local runtimes `hermes`, `hermes-plus`,
`nanobot` and `zeroclaw`. It deliberately does not enable the Docker sandbox in this version;
install the selected upstream Agent package from the same pinned checkout before use.

Credentials are referenced by an absolute owner-only file. The path is frozen in the plan, while
the secret content is read only inside the supervised runner and is not written to the plan,
command journal, logs or Records. Native mode without a judge credential remains
`protocol=review_required`.

```bash
agent-infra benchmark inspect --config adapters/past-bench/adapters.toml \
  --source /path/to/PAST-Bench/self-evolve-tasks-v2/memory_ability/SM01_preference_adoption \
  past-bench
agent-infra benchmark plan --config adapters/past-bench/adapters.toml \
  --source /path/to/PAST-Bench/self-evolve-tasks-v2/memory_ability/SM01_preference_adoption \
  --request adapters/past-bench/request.json --output /private/past-plan.json past-bench
```

Continue with the standard `benchmark check`, `prepare`, `run`, `status`, `events` and
`artifacts` commands. See the BM03 operation guide for native parameters and evidence limits.
