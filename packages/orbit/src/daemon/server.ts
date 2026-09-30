import { randomBytes } from "node:crypto";
import { type ServerType, serve } from "@hono/node-server";
import { removeDaemonInfo, writeDaemonInfo } from "../config/daemon-info.ts";
import { DEFAULT_PORT, ensureHome, type OrbitPaths } from "../config/paths.ts";
import { createApp } from "./app.ts";

export interface StartedDaemon {
  url: string;
  server: ServerType;
  stop(): Promise<void>;
}

/** Start the daemon HTTP server on 127.0.0.1 and publish its endpoint and token. */
export function startDaemon(paths: OrbitPaths, port = DEFAULT_PORT): Promise<StartedDaemon> {
  ensureHome(paths);
  const token = randomBytes(24).toString("hex");
  const app = createApp({ token, diskPath: paths.home, startedAt: new Date().toISOString() });

  return new Promise((resolve, reject) => {
    const server = serve({ fetch: app.fetch, hostname: "127.0.0.1", port }, (info) => {
      const url = `http://127.0.0.1:${info.port}`;
      writeDaemonInfo(paths, { url, token, pid: process.pid });
      const stop = () =>
        new Promise<void>((done) => {
          removeDaemonInfo(paths, process.pid);
          server.close(() => done());
        });
      resolve({ url, server, stop });
    });
    server.once("error", reject);
  });
}
