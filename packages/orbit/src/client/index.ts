import type { z } from "zod";
import { type DaemonInfo, readDaemonInfo } from "../config/daemon-info.ts";
import type { OrbitPaths } from "../config/paths.ts";
import { API_PREFIX, DoctorReport, Health, NodeResources } from "../contracts/index.ts";

export class OrbitClient {
  readonly info: DaemonInfo;

  constructor(info: DaemonInfo) {
    this.info = info;
  }

  private async get<T extends z.ZodType>(path: string, schema: T): Promise<z.infer<T>> {
    const res = await fetch(`${this.info.url}${API_PREFIX}${path}`, {
      headers: { authorization: `Bearer ${this.info.token}` },
      signal: AbortSignal.timeout(30_000),
    });
    const body: unknown = await res.json();
    if (!res.ok) {
      const msg = (body as { error?: string }).error ?? res.statusText;
      throw new Error(`daemon ${path}: ${res.status} ${msg}`);
    }
    return schema.parse(body);
  }

  health() {
    return this.get("/health", Health);
  }
  resources() {
    return this.get("/resources", NodeResources);
  }
  doctor() {
    return this.get("/doctor", DoctorReport);
  }
}

/** Return a client for a live daemon, or null when none is reachable. */
export async function tryConnect(paths: OrbitPaths): Promise<OrbitClient | null> {
  const info = readDaemonInfo(paths);
  if (!info) return null;
  const client = new OrbitClient(info);
  try {
    await client.health();
    return client;
  } catch {
    return null;
  }
}
