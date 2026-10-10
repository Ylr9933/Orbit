# Harbor shared verifier mode (after phase)
branch: feat/harbor-shared-verifier (on feat/harness-parity) · status: completed · updated: 2026-10-10

## Goal
Support Harbor's default `environment_mode = "shared"`, which almost every Harbor-registry dataset
uses: the verifier runs in the Agent's own, still running container once the Agent is done, and sees
its files and processes.

## Changes
- Contract: `RunSpec.after` (`AfterPhase`: command, timeout, env, passEnv, copy, network, collect),
  `Run.after` (`AfterStatus`), `RunSpec.mkdirs`.
- Runs: a phase script keeps the container after the command (own session via `setsid`, exit code in
  `/orbit/phases/main.exit`); a timeout stops only the command's session; then collect, copy files in,
  switch the network, `docker exec -d` the phase (output and exit code in `/orbit/phases/`, secrets
  by env-file), wait its timeout, collect `output/after/`, stop. All state is in files, so a daemon
  restart resumes either phase. Cancel stops the container (phase `skipped` / `error`).
- Bench: a solve run with an after phase is scored from itself (no verify run); classification uses
  `Run.after` (not run / timeout → invalid); such trials cannot be rescored.
- Harbor: shared tasks get an after phase with Harbor's verifier command (`chmod +x`, run
  `/tests/test.sh`, output to `/logs/verifier/test-stdout.txt`), `[verifier.env]`, timeout and
  verifier-phase network; every solve run creates `/logs/{agent,verifier,artifacts}` like Harbor's mounts.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| `pnpm verify` | working tree | passed | 185 tests |
| Real Docker: separate-mode regression (`e-ve`, `separate-verifier-environment`, TB-Science `variable-star-vetting` oracle) | working tree | passed | all reward 1 with `mkdirs` in place |
| Real Docker: after phase sees files and a server the command left; tests hidden during the command; grader secret passed and redacted; network off | working tree | passed | `after-ok` |
| Real Docker: command timeout stops its session, after phase still runs; after-phase timeout; cancel during the phase | working tree | passed | states `failed (timeout)` + after `succeeded`; after `timeout`; `cancelled` + after `error`, nothing left |
| Real Docker: daemon restart during the command and during the after phase | working tree | passed | both resumed to `succeeded` with the phase output |
| Real Docker: harbor/examples shared tasks (oracle, empty) | working tree | passed | verifier-mode-matrix `shared-default` and network-policy-matrix (`e`, `e-default`, `e-a-diff`, `e-a-diff-v-match`, `e-v-diff`, `e-a-v-same`, `hello-workdir`): oracle 1, empty 0; `*-allow-agent-host` 0 as Harbor expects without `--allow-agent-host` |
| Real Docker: `hello-world`, `hello-alpine` | working tree | failed | verifier timed out (120 s) doing `apt-get` / downloading uv over this host's slow network; environment, not Orbit |

## Next / open issues
- After-phase resource use counts in the solve run's usage (same container).
- Multi-step tasks and `[[verifier.collect]]` stay unsupported.
