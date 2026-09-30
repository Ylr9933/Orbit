import { randomBytes } from "node:crypto";
import { closeSync, existsSync, openSync, readSync, statSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { type ServerType, serve } from "@hono/node-server";
import { AuthStore } from "../auth/index.ts";
import { BenchmarkRegistry } from "../bench/registry.ts";
import { BenchService } from "../bench/service.ts";
import { removeDaemonInfo, writeDaemonInfo } from "../config/daemon-info.ts";
import { ensureHome, type OrbitPaths } from "../config/paths.ts";
import { isTerminal } from "../contracts/index.ts";
import { Notifier, NotifyStore } from "../notify/index.ts";
import { probeNode } from "../resources/probe.ts";
import { AUTH_TEST_GROUP, RunService } from "../runs/service.ts";
import { Store } from "../store/index.ts";
import { createApp } from "./app.ts";

/** Last `n` lines of a text file (reads at most the final 16 KiB). */
function tail(file: string, n: number): string {
  try {
    const size = statSync(file).size;
    const len = Math.min(size, 16 * 1024);
    const buf = Buffer.alloc(len);
    const fd = openSync(file, "r");
    try {
      readSync(fd, buf, 0, len, size - len);
    } finally {
      closeSync(fd);
    }
    return buf.toString("utf8").trimEnd().split("\n").slice(-n).join("\n");
  } catch {
    return "";
  }
}

export interface StartedDaemon {
  url: string;
  token: string;
  server: ServerType;
  runs: RunService;
  stop(): Promise<void>;
}

/** Built Web UI: `dist/web` next to the bundled CLI, or `packages/web/dist` in development. */
function findWebDir(): string | null {
  const here = dirname(fileURLToPath(import.meta.url));
  const candidates = [join(here, "web"), join(here, "../../../web/dist")];
  return candidates.find((d) => existsSync(join(d, "index.html"))) ?? null;
}

export interface DaemonOptions {
  port?: number;
  tickMs?: number;
  /** Command running this orbit binary, for the process-run docker shim (default: detected). */
  shim?: string[];
}

/** `node [execArgv] <entry>` when this process is the orbit CLI (not e.g. a test runner). */
function detectShim(): string[] | undefined {
  const entry = process.argv[1];
  if (!entry || !/^(bin\.ts|cli\.mjs|orbit)$/.test(basename(entry))) return undefined;
  return [process.execPath, ...process.execArgv, entry];
}

/** Start the daemon on 127.0.0.1: open the store, recover runs, serve the API, publish endpoint + token. */
export async function startDaemon(
  paths: OrbitPaths,
  opts: DaemonOptions = {},
): Promise<StartedDaemon> {
  ensureHome(paths);
  const token = randomBytes(24).toString("hex");
  const store = new Store(paths.db);
  const auth = new AuthStore(paths.auth);
  const runs = new RunService({
    store,
    paths,
    auth,
    probe: () => probeNode(paths.home),
    tickMs: opts.tickMs,
    shim: opts.shim ?? detectShim(),
  });
  const benchmarks = new BenchmarkRegistry(paths.benchmarks);
  const bench = new BenchService({
    store,
    runs,
    registry: benchmarks,
    paths,
    auth,
    log: (msg) => console.error(`orbit ${msg}`),
  });
  let webUrl: string | undefined;
  const notifyStore = new NotifyStore(paths.notify);
  const notifier = new Notifier({
    store: notifyStore,
    groupRuns: (group) => store.listRuns({ group, limit: 10_000 }),
    logTail: (id) => runs.redactor().apply(tail(runs.dirs(id).log, 15)),
    log: (msg) => console.error(`orbit ${msg}`),
    webUrl: () => webUrl,
  });
  runs.on("change", ({ run, event }) => {
    // The terminal event is saved once, before cleanup; auth checks stay quiet.
    if (event?.kind !== run.state || !isTerminal(run.state) || run.spec.group === AUTH_TEST_GROUP)
      return;
    void notifier.onTerminal(run);
  });
  const app = createApp({
    token,
    startedAt: new Date().toISOString(),
    runs,
    auth,
    notifyStore,
    notifier,
    bench,
    benchmarks,
    webDir: findWebDir(),
  });

  const server = await new Promise<ServerType>((resolve, reject) => {
    const s = serve(
      { fetch: app.fetch, hostname: "127.0.0.1", port: opts.port ?? paths.port },
      () => resolve(s),
    );
    s.once("error", reject);
  }).catch((e) => {
    store.close();
    throw e;
  });
  const addr = server.address();
  const port = typeof addr === "object" && addr ? addr.port : (opts.port ?? paths.port);
  const url = `http://127.0.0.1:${port}`;
  webUrl = url;
  await runs.start();
  await bench.start();
  writeDaemonInfo(paths, { url, token, pid: process.pid });

  const stop = async () => {
    removeDaemonInfo(paths, process.pid);
    await runs.stop();
    await new Promise<void>((done) => {
      server.close(() => done());
      if ("closeAllConnections" in server) server.closeAllConnections();
    });
    store.close();
  };
  return { url, token, server, runs, stop };
}
