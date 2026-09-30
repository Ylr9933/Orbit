import { spawn } from "node:child_process";
import { openSync } from "node:fs";
import { Command } from "commander";
import { type OrbitClient, tryConnect } from "../client/index.ts";
import { ensureHome, type OrbitPaths, orbitPaths } from "../config/paths.ts";
import { VERSION } from "../lib/version.ts";
import { printDoctor, printResources } from "./format.ts";

export interface ProgramDeps {
  /** Run the daemon in the foreground; provided by the composition root (src/bin.ts). */
  runDaemon(paths: OrbitPaths, port?: number): Promise<void>;
}

/** Connect to the local daemon, starting a detached one when none is running. */
async function connect(p: OrbitPaths): Promise<OrbitClient> {
  const existing = await tryConnect(p);
  if (existing) return existing;
  ensureHome(p);
  const log = openSync(p.daemonLog, "a");
  const entry = process.argv[1];
  if (!entry) throw new Error("cannot locate the orbit entrypoint to start the daemon");
  const child = spawn(process.execPath, [...process.execArgv, entry, "daemon"], {
    detached: true,
    stdio: ["ignore", log, log],
    env: process.env,
  });
  child.unref();
  for (let i = 0; i < 50; i++) {
    await new Promise((r) => setTimeout(r, 100));
    const client = await tryConnect(p);
    if (client) return client;
  }
  throw new Error(`daemon did not start; see ${p.daemonLog}`);
}

export function createProgram(deps: ProgramDeps, paths: OrbitPaths = orbitPaths()): Command {
  const program = new Command()
    .name("orbit")
    .description("Run, isolate and record experiments for Codex / Claude Code")
    .version(VERSION);

  program
    .command("daemon")
    .description("run the node daemon in the foreground")
    .option("-p, --port <port>", "listen port on 127.0.0.1", (v) => Number.parseInt(v, 10))
    .action((opts: { port?: number }) => deps.runDaemon(paths, opts.port));

  program
    .command("resources")
    .description("show GPUs, CPU, memory and disk on this node")
    .option("--json", "print JSON")
    .action(async (opts: { json?: boolean }) => {
      const r = await (await connect(paths)).resources();
      if (opts.json) console.log(JSON.stringify(r, null, 2));
      else printResources(r);
    });

  program
    .command("doctor")
    .description("check docker, nvidia-smi, git and node")
    .option("--json", "print JSON")
    .action(async (opts: { json?: boolean }) => {
      const r = await (await connect(paths)).doctor();
      if (opts.json) console.log(JSON.stringify(r, null, 2));
      else printDoctor(r);
      if (!r.ok) process.exitCode = 1;
    });

  return program;
}
