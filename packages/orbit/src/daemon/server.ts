import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { type ServerType, serve } from "@hono/node-server";
import { removeDaemonInfo, writeDaemonInfo } from "../config/daemon-info.ts";
import { ensureHome, type OrbitPaths } from "../config/paths.ts";
import { probeNode } from "../resources/probe.ts";
import { RunService } from "../runs/service.ts";
import { Store } from "../store/index.ts";
import { createApp } from "./app.ts";

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
}

/** Start the daemon on 127.0.0.1: open the store, recover runs, serve the API, publish endpoint + token. */
export async function startDaemon(
  paths: OrbitPaths,
  opts: DaemonOptions = {},
): Promise<StartedDaemon> {
  ensureHome(paths);
  const token = randomBytes(24).toString("hex");
  const store = new Store(paths.db);
  const runs = new RunService({
    store,
    paths,
    probe: () => probeNode(paths.home),
    tickMs: opts.tickMs,
  });
  const app = createApp({ token, startedAt: new Date().toISOString(), runs, webDir: findWebDir() });

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
  await runs.start();
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
