# agent-infra-tb-science

Independent SDK 1.0 adapter for the pinned single-CPU, separate-verifier TB-Science profile.
Install the reusable `agent-infra-harbor` runtime alongside this wheel; explicitly enable
`adapters.toml`. Native Codex (explicit model, exact CLI version, host auth.json or worker API key),
Oracle and Nop are supported by the CPU single-step profile. Full-suite execution and
leaderboard claims require separate evidence. Run the offline suite audit with
`python -m agent_infra_tb_science --source TASKS --request request-codex.json --output AUDIT`.
The audit reports every rejected task; batch prepare never silently skips one.

[Installation and commands](../../docs/operations/tb-science-native-trial.md)
· [Implementation and extension boundaries](../../docs/implementation/benchmark-harbor.md)
