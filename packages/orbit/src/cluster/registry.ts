// Cluster configuration files, written only by the daemon (0600): the worker nodes this node places
// runs on (with their tokens), and this node's own listener for a primary.
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { nowIso } from "../lib/ids.ts";
import { writePrivateJson } from "../lib/private-json.ts";

export interface NodeEntry {
  name: string;
  url: string;
  /** The worker's cluster token; never returned by the API. */
  token: string;
  addedAt: string;
}

export interface ExposeConfig {
  /** `host:port` to listen on for a primary, or null when not exposed. */
  listen: string | null;
  token: string;
}

function readJson<T>(file: string, fallback: T): T {
  if (!existsSync(file)) return fallback;
  return JSON.parse(readFileSync(file, "utf8")) as T;
}

export class NodeRegistry {
  private readonly file: string;

  constructor(file: string) {
    this.file = file;
  }

  list(): NodeEntry[] {
    return readJson<{ nodes?: NodeEntry[] }>(this.file, {}).nodes ?? [];
  }

  get(name: string): NodeEntry | null {
    return this.list().find((n) => n.name === name) ?? null;
  }

  put(entry: Omit<NodeEntry, "addedAt">): NodeEntry {
    const all = this.list();
    const old = all.find((n) => n.name === entry.name);
    const e: NodeEntry = { ...entry, addedAt: old?.addedAt ?? nowIso() };
    const nodes = [...all.filter((n) => n.name !== e.name), e].sort((a, b) =>
      a.name.localeCompare(b.name),
    );
    writePrivateJson(this.file, { version: 1, nodes });
    return e;
  }

  remove(name: string): boolean {
    const all = this.list();
    const rest = all.filter((n) => n.name !== name);
    if (rest.length === all.length) return false;
    writePrivateJson(this.file, { version: 1, nodes: rest });
    return true;
  }
}

/** This node's listener config; the token is created on first use and kept until rotated. */
export class ExposeStore {
  private readonly file: string;

  constructor(file: string) {
    this.file = file;
  }

  read(): ExposeConfig {
    const c = readJson<Partial<ExposeConfig>>(this.file, {});
    if (c.token) return { listen: c.listen ?? null, token: c.token };
    const fresh = { listen: c.listen ?? null, token: newToken() };
    writePrivateJson(this.file, { version: 1, ...fresh });
    return fresh;
  }

  setListen(listen: string | null): ExposeConfig {
    const c = { ...this.read(), listen };
    writePrivateJson(this.file, { version: 1, ...c });
    return c;
  }

  rotate(): ExposeConfig {
    const c = { ...this.read(), token: newToken() };
    writePrivateJson(this.file, { version: 1, ...c });
    return c;
  }
}

const newToken = () => `orbit-node-${randomBytes(24).toString("hex")}`;

/** `host:port` -> parts; IPv6 hosts may be bracketed (`[::1]:7718`). */
export function parseListen(listen: string): { host: string; port: number } {
  const m = /^(?:\[([^\]]+)\]|([^:]+)):(\d{1,5})$/.exec(listen.trim());
  const port = Number(m?.[3]);
  if (!m || port < 1 || port > 65535) throw new Error(`listen must be HOST:PORT, got ${listen}`);
  return { host: (m[1] ?? m[2]) as string, port };
}
