// Named datasets and model weights on this node: a name shared across the cluster, mapped to a path
// local to each node. Placement only picks nodes that have every dataset a run mounts; Orbit never
// copies data between nodes.
import { existsSync, readFileSync, statSync } from "node:fs";
import { Dataset, DatasetInput, type DatasetInput as DatasetInputT } from "../contracts/index.ts";
import { nowIso } from "../lib/ids.ts";
import { writePrivateJson } from "../lib/private-json.ts";

export class DatasetRegistry {
  private readonly file: string;

  constructor(file: string) {
    this.file = file;
  }

  private read(): Dataset[] {
    if (!existsSync(this.file)) return [];
    const raw = JSON.parse(readFileSync(this.file, "utf8")) as { datasets?: unknown[] };
    return (raw.datasets ?? []).map((d) => Dataset.parse(d));
  }

  private write(all: Dataset[]): void {
    writePrivateJson(this.file, { version: 1, datasets: all });
  }

  list(): Dataset[] {
    return this.read();
  }

  get(name: string): Dataset | null {
    return this.read().find((d) => d.name === name) ?? null;
  }

  /** Local path of `name`, or null when it is not registered here. */
  path(name: string): string | null {
    return this.get(name)?.path ?? null;
  }

  put(input: DatasetInputT): Dataset {
    const p = DatasetInput.parse(input);
    if (!statSync(p.path, { throwIfNoEntry: false }))
      throw new Error(`dataset path not found: ${p.path}`);
    const all = this.read();
    const old = all.find((d) => d.name === p.name);
    const d: Dataset = { ...p, createdAt: old?.createdAt ?? nowIso() };
    this.write(
      [...all.filter((x) => x.name !== p.name), d].sort((x, y) => x.name.localeCompare(y.name)),
    );
    return d;
  }

  remove(name: string): boolean {
    const all = this.read();
    const rest = all.filter((d) => d.name !== name);
    if (rest.length === all.length) return false;
    this.write(rest);
    return true;
  }
}
