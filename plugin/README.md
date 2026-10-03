# Orbit agent plugin

`skills/orbit/SKILL.md` teaches Codex and Claude Code how to estimate resources, submit runs and
sweeps, follow them and record conclusions with the `orbit` CLI. `skills/orbit-bench/SKILL.md`
teaches them to connect a new benchmark (adapter executable, per-task resources file) and to revise
task resources from measured runs. The `orbit` command must be on the agent's `PATH`.

## Claude Code

```bash
claude plugin marketplace add /path/to/orbit   # the repository root (.claude-plugin/marketplace.json)
claude plugin install orbit@orbit
```

Or copy/symlink `skills/orbit` and `skills/orbit-bench` to `~/.claude/skills/` (all projects) or
`<project>/.claude/skills/` (one project).

## Codex

Copy or symlink `skills/orbit` and `skills/orbit-bench` to `~/.agents/skills/` (all projects) or
`<project>/.agents/skills/` (one project). If your Codex version does not load skills, add one
line to the project's `AGENTS.md`: `Run experiments with Orbit; follow .agents/skills/orbit/SKILL.md.`

The `orbit` CLI talks to the local daemon over `127.0.0.1`. Codex's default `workspace-write` sandbox
blocks network access, so allow network for Codex (e.g. `-s danger-full-access`, or
`sandbox_workspace_write.network_access = true`) when it should submit runs.

## Session linking

`orbit run` records which agent session submitted it (Claude Code via `CLAUDE_CODE_SESSION_ID`,
Codex via `CODEX_THREAD_ID` or the parent process, or `ORBIT_AGENT=<harness>:<session-id>`), and the
Web UI shows that transcript next to the run.
