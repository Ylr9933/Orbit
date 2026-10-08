# Orbit

Run coding agents' experiments in isolated Docker containers with GPU / CPU / memory leases.
Keep code snapshots, logs, metrics, outputs and agent sessions for review in the bundled local Web UI.

Requires Linux, Node.js 24.18+ (24.x), Git and Docker usable without sudo. GPU runs also need NVIDIA
drivers and the NVIDIA Container Toolkit or CDI. No pnpm or source checkout is needed.

```bash
npx -y @zjunlp/orbit doctor
```

Install the CLI permanently with `npm install -g @zjunlp/orbit`, then use `orbit` instead of
`npx -y @zjunlp/orbit`. The daemon starts automatically on the first command that needs it.

Install the Claude Code plugin (Claude Code must already be installed):

```bash
npx -y @zjunlp/orbit plugin install
```

Restart Claude Code to load `/orbit:orbit` and `/orbit:orbit-bench`. The skills use `npx` when no
global `orbit` command is available. The plugin comes from the `zjunlp/Orbit` GitHub marketplace.

```bash
npx -y @zjunlp/orbit run --image python:3.12-slim -- python -c 'print("hello")'
npx -y @zjunlp/orbit ps -a
npx -y @zjunlp/orbit web
```

[Usage and configuration](https://github.com/zjunlp/Orbit#readme) ·
[Chinese guide](https://github.com/zjunlp/Orbit/blob/main/README.zh-CN.md) ·
[Validation limits](https://github.com/zjunlp/Orbit/blob/main/docs/status.md)

MIT © ZJUNLP
