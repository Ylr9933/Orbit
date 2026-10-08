# Orbit agent plugin

`skills/orbit/SKILL.md` teaches Codex and Claude Code how to estimate resources, submit runs and
sweeps, follow them and record conclusions with the `orbit` CLI. `skills/orbit-bench/SKILL.md`
teaches them to connect a new benchmark (adapter executable, per-task resources file) and to revise
task resources from measured runs. Both skills use `npx -y @zjunlp/orbit` when `orbit` is not on PATH.
Node.js 24.18+ (24.x), Git and Docker are required; see the repository README for GPU prerequisites.

## Claude Code

After the first npm release, with Claude Code already installed:

```bash
npx -y @zjunlp/orbit plugin install
```

Restart Claude Code to load `/orbit:orbit` and `/orbit:orbit-bench`. This uses Claude Code's own
marketplace and plugin commands and installs at user scope. It does not change Orbit's daemon,
credentials, shell profile or your global npm packages. Repeating the command is safe.

Manual installation from GitHub:

```bash
claude plugin marketplace add zjunlp/Orbit
claude plugin install orbit@orbit --scope user
```

For an unpublished local revision, run `pnpm orbit plugin install --source .` from the repository.
Update with `claude plugin marketplace update orbit && claude plugin update orbit@orbit`;
uninstall with `claude plugin uninstall orbit@orbit`. The marketplace may be removed separately
with `claude plugin marketplace remove orbit`.

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
