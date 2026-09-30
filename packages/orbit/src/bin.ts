#!/usr/bin/env node
// Composition root for the `orbit` executable: the CLI talks to the daemon over HTTP,
// and `orbit daemon` runs the daemon in this same binary.
import { createProgram } from "./cli/program.ts";
import { runDaemon } from "./daemon/main.ts";

createProgram({ runDaemon })
  .parseAsync()
  .catch((e: unknown) => {
    console.error(`orbit: ${e instanceof Error ? e.message : String(e)}`);
    process.exit(1);
  });
