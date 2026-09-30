#!/usr/bin/env node
// Composition root for the `orbit` executable: the CLI talks to the daemon over HTTP,
// `orbit daemon` runs the daemon in this same binary, and `__docker-shim` is the `docker` that
// process runs see (kept light: it loads nothing else).
const [, , first, ...rest] = process.argv;

if (first === "__docker-shim") {
  const { shimMain } = await import("./runs/shim.ts");
  shimMain(rest[0] ?? "", rest.slice(1));
} else {
  const { createProgram } = await import("./cli/program.ts");
  const { runDaemon } = await import("./daemon/main.ts");
  createProgram({ runDaemon })
    .parseAsync()
    .catch((e: unknown) => {
      console.error(`orbit: ${e instanceof Error ? e.message : String(e)}`);
      process.exit(1);
    });
}
