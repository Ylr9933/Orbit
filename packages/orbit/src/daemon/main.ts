import type { OrbitPaths } from "../config/paths.ts";
import { VERSION } from "../lib/version.ts";
import { startDaemon } from "./server.ts";

export async function runDaemon(paths: OrbitPaths, port?: number): Promise<void> {
  const d = await startDaemon(paths, port);
  console.log(`orbit daemon ${VERSION} listening on ${d.url} (pid ${process.pid})`);
  const shutdown = () => void d.stop().then(() => process.exit(0));
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
}
