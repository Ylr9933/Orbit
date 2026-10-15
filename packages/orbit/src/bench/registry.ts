// Registered benchmark checkouts in one JSON file written only by the daemon. Entries hold paths
// and non-secret settings; `passEnv` names variables read from the daemon environment at launch.
import { chmodSync, readFileSync, renameSync, statSync, writeFileSync } from "node:fs";
import {
  Benchmark,
  BenchmarkInput,
  type BenchmarkInput as BenchmarkInputT,
} from "../contracts/index.ts";
import { nowIso } from "../lib/ids.ts";

/** Entries written before adapter settings moved into `config` (asi `python`, `instances`). */
function upgrade(v: unknown): unknown {
  if (!v || typeof v !== "object") return v;
  const { python, instances, ...rest } = v as Record<string, unknown> & { config?: object };
  const old = Object.entries({ python, instances }).filter(([, x]) => typeof x === "string");
  return old.length ? { ...rest, config: { ...Object.fromEntries(old), ...rest.config } } : rest;
}

export class BenchmarkRegistry {
  private readonly file: string;
  private cached: { version: string; benchmarks: Benchmark[] } | null = null;

  constructor(file: string) {
    this.file = file;
  }

  private read(): Benchmark[] {
    const stat = statSync(this.file, { bigint: true, throwIfNoEntry: false });
    if (!stat) {
      this.cached = null;
      return [];
    }
    const version = `${stat.mtimeNs}:${stat.ctimeNs}:${stat.ino}:${stat.size}`;
    if (this.cached?.version === version) return this.cached.benchmarks;
    const raw = JSON.parse(readFileSync(this.file, "utf8")) as { benchmarks?: unknown[] };
    const benchmarks = (raw.benchmarks ?? []).map((b) => Benchmark.parse(upgrade(b)));
    this.cached = { version, benchmarks };
    return benchmarks;
  }

  private write(all: Benchmark[]): void {
    const tmp = `${this.file}.${process.pid}.tmp`;
    writeFileSync(tmp, `${JSON.stringify({ version: 1, benchmarks: all }, null, 2)}\n`, {
      mode: 0o600,
    });
    chmodSync(tmp, 0o600);
    renameSync(tmp, this.file);
    this.cached = null;
  }

  list(): Benchmark[] {
    return structuredClone(this.read());
  }

  get(name: string): Benchmark | null {
    return structuredClone(this.read().find((b) => b.name === name) ?? null);
  }

  put(input: BenchmarkInputT): Benchmark {
    const p = BenchmarkInput.parse(input);
    const all = this.read();
    const old = all.find((b) => b.name === p.name);
    const now = nowIso();
    const b: Benchmark = { ...p, createdAt: old?.createdAt ?? now, updatedAt: now };
    this.write(
      [...all.filter((x) => x.name !== p.name), b].sort((x, y) => x.name.localeCompare(y.name)),
    );
    return b;
  }

  remove(name: string): boolean {
    const all = this.read();
    const rest = all.filter((b) => b.name !== name);
    if (rest.length === all.length) return false;
    this.write(rest);
    return true;
  }
}
