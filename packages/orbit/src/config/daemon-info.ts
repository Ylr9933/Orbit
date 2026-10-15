import { readFileSync, rmSync } from "node:fs";
import { z } from "zod";
import { writePrivateJson } from "../lib/private-json.ts";
import type { OrbitPaths } from "./paths.ts";

export const DaemonInfo = z.object({
  url: z.string(),
  token: z.string(),
  pid: z.number().int(),
});
export type DaemonInfo = z.infer<typeof DaemonInfo>;

export function readDaemonInfo(paths: OrbitPaths): DaemonInfo | null {
  try {
    return DaemonInfo.parse(JSON.parse(readFileSync(paths.daemonFile, "utf8")));
  } catch {
    return null;
  }
}

export function writeDaemonInfo(paths: OrbitPaths, info: DaemonInfo): void {
  // Atomically and private: it holds the daemon token.
  writePrivateJson(paths.daemonFile, info, 0);
}

export function removeDaemonInfo(paths: OrbitPaths, pid: number): void {
  if (readDaemonInfo(paths)?.pid === pid) rmSync(paths.daemonFile, { force: true });
}
