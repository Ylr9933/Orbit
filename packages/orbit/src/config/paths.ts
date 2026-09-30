import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const DEFAULT_PORT = 7717;

export interface OrbitPaths {
  home: string;
  /** JSON `{ url, token, pid }` written by the running daemon (0600). */
  daemonFile: string;
  daemonLog: string;
}

export function orbitPaths(env: NodeJS.ProcessEnv = process.env): OrbitPaths {
  const home = env.ORBIT_HOME || join(homedir(), ".orbit");
  return {
    home,
    daemonFile: join(home, "daemon.json"),
    daemonLog: join(home, "daemon.log"),
  };
}

export function ensureHome(paths: OrbitPaths): void {
  mkdirSync(paths.home, { recursive: true, mode: 0o700 });
}
