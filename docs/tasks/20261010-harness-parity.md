# Agent harness parity with Harbor, benchmark versions
branch: feat/harness-parity (on feat/harbor-sidecars) · status: completed · updated: 2026-10-10

## Goal
Run Claude Code / Codex on Harbor tasks the way Harbor's built-in agents do (so TB-Science
scores can be compared with the public board), and record which benchmark version a job used.

## Changes
- claude-code: `--effort` from the method (was silently ignored); `IS_SANDBOX=1` (Harbor tasks run
  as root, where Claude Code otherwise refuses `--dangerously-skip-permissions`);
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`; relay profiles with a model pin the tier aliases and
  the subagent model to it unless the profile sets them.
- `BenchJob.source`: commit, `git describe --tags --always --dirty` and tracked changes of the
  benchmark checkout at submit; shown by `orbit bench show`.
- Remaining difference, documented in design §6: Harbor's codex adds `--enable unified_exec --json`.

## Validation
| Check | Revision | Result | Notes |
| --- | --- | --- | --- |
| Claude Code as root in a container (host binary 2.1.289) | working tree | passed | without `IS_SANDBOX`: "cannot be used with root/sudo privileges"; with it: reaches auth ("Not logged in") |
| `pnpm verify` | working tree | passed | 183 tests |
| Official `harbor run -a oracle -e docker` (harbor `09f5b964`) vs Orbit oracle on TB-Science compose tasks | b85707f | passed | protein-active-learning, inverse-lithography, longitudinal-clinical-agent: reward 1.0 under both |

## Next / open issues
- Oracle-level parity only. A paired real Agent run (Orbit vs official `harbor run`, same model) needs API credits; not run.
- Whether to enable codex `unified_exec` for Harbor-parity jobs is the user's call.
