import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it, vi } from "vitest";
import { handle } from "../src/bench/adapter.ts";
import { findHarborTasks, harborAdapter } from "../src/bench/harbor.ts";
import { BenchmarkRegistry } from "../src/bench/registry.ts";
import { type AdapterRequest, Benchmark } from "../src/contracts/index.ts";

vi.mock("node:fs", async (original) => {
  const fs = await original<typeof import("node:fs")>();
  return { ...fs, readFileSync: vi.fn(fs.readFileSync), readdirSync: vi.fn(fs.readdirSync) };
});

const homes: string[] = [];
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  for (const home of homes.splice(0)) rmSync(home, { recursive: true, force: true });
});
const fixture = () => {
  const home = mkdtempSync(join(tmpdir(), "orbit-lookups-"));
  homes.push(home);
  return home;
};
const task = (
  dir: string,
  toml = '[environment]\ndocker_image = "fixture"\n[verifier]\nenvironment_mode = "separate"\n',
) => {
  mkdirSync(join(dir, "tests"), { recursive: true });
  writeFileSync(join(dir, "task.toml"), toml);
  writeFileSync(join(dir, "instruction.md"), "fixture instruction");
  writeFileSync(join(dir, "tests/test.sh"), "true");
};
const request = (root: string, id: string): AdapterRequest => ({
  protocol: 1,
  op: "solve",
  benchmark: { name: "fixture", path: root, config: {} },
  trial: {
    id: "trial",
    task: id,
    seed: 1,
    method: { name: "empty", agent: "empty" },
    options: {},
    staging: join(root, "staging"),
    hostNetwork: false,
  },
});

it.each(["tasks", "."])(
  "resolves a flat Harbor task directly under %s without reading siblings",
  (layout) => {
    const root = fixture();
    const base = join(root, layout);
    task(join(base, "wanted"));
    for (let i = 0; i < 40; i++) task(join(base, `sibling-${i}`), "[broken");
    vi.mocked(readFileSync).mockClear();
    vi.mocked(readdirSync).mockClear();
    const req = request(root, "wanted");
    expect(handle(harborAdapter, req)).toMatchObject({
      spec: { image: "fixture", command: ["true"] },
    });
    expect(
      vi
        .mocked(readFileSync)
        .mock.calls.map(([file]) => String(file))
        .filter((f) => f.endsWith("task.toml")),
    ).toEqual([join(base, "wanted/task.toml")]);
    expect(vi.mocked(readdirSync).mock.calls.map(([file]) => String(file))).not.toContain(base);
    vi.mocked(readFileSync).mockClear();
    handle(harborAdapter, {
      ...req,
      op: "verify",
      solve: { run: {} as never, output: join(root, "output") },
    });
    expect(
      vi
        .mocked(readFileSync)
        .mock.calls.map(([file]) => String(file))
        .filter((f) => f.endsWith("task.toml")),
    ).toEqual([join(base, "wanted/task.toml")]);
  },
);

it("preserves single-root, nested, duplicate, hidden and depth-limited task ids", () => {
  const root = fixture();
  for (const name of [
    "group/unique",
    "a/duplicate",
    "b/duplicate",
    "flat",
    ".hidden",
    "a/b/c/d/deep",
  ])
    task(join(root, name));
  task(join(root, "flat/nested"));
  expect(findHarborTasks(root).map((t) => t.id)).toEqual([
    "a/duplicate",
    "b/duplicate",
    "flat",
    "unique",
  ]);
  for (const id of ["a/duplicate", "b/duplicate", "flat", "unique"])
    expect(handle(harborAdapter, request(root, id))).toMatchObject({ spec: { command: ["true"] } });
  for (const id of [
    "duplicate",
    "group/unique",
    ".hidden",
    "deep",
    "flat/nested",
    "../flat",
    "/flat",
  ])
    expect(() => handle(harborAdapter, request(root, id))).toThrow(`task not found: ${id}`);
  task(root);
  const id = root.split("/").at(-1) as string;
  expect(findHarborTasks(root).map((t) => t.id)).toEqual([id]);
  expect(handle(harborAdapter, request(root, id))).toMatchObject({ spec: { command: ["true"] } });
  expect(() => handle(harborAdapter, request(root, "flat"))).toThrow("task not found: flat");
});

it("keeps unsupported and malformed task errors", () => {
  const root = fixture();
  task(join(root, "bad"), "[broken");
  task(join(root, "unsupported"), '[environment]\ndocker_image = "fixture"\ngpu_types = ["x"]\n');
  for (const t of findHarborTasks(root))
    expect(() => handle(harborAdapter, request(root, t.id))).toThrow(
      `task ${t.id} is not supported: ${t.reason}`,
    );
});

it("caches parsed registry entries and refreshes on edits, replacement, removal and writes", () => {
  const home = fixture();
  const file = join(home, "benchmarks.json");
  const registry = new BenchmarkRegistry(file);
  expect(registry.get("fixture")).toBeNull();
  registry.put({ name: "fixture", path: home, adapter: "asi", config: { python: "python" } });
  const parse = vi.spyOn(Benchmark, "parse");
  vi.mocked(readFileSync).mockClear();
  const first = registry.get("fixture");
  for (let i = 0; i < 20; i++) expect(registry.get("fixture")).toEqual(first);
  expect(parse).toHaveBeenCalledTimes(1);
  expect(readFileSync).toHaveBeenCalledTimes(1);
  if (!first) throw new Error("fixture benchmark missing");
  first.config.python = "mutated";
  registry.list().splice(0);
  expect(registry.get("fixture")?.config.python).toBe("python");
  const doc = { benchmarks: [{ ...first, config: {}, python: "legacy-python" }] };
  writeFileSync(file, JSON.stringify(doc));
  utimesSync(file, 1_800_000_000, 1_800_000_000);
  expect(registry.get("fixture")?.config.python).toBe("legacy-python");
  writeFileSync(`${file}.new`, JSON.stringify({ benchmarks: [] }));
  utimesSync(`${file}.new`, 1_800_000_000, 1_800_000_000);
  renameSync(`${file}.new`, file);
  expect(registry.list()).toEqual([]);
  rmSync(file);
  expect(registry.list()).toEqual([]);
  registry.put({ name: "fixture", path: home, adapter: "harbor" });
  expect(registry.get("fixture")?.adapter).toBe("harbor");
  expect(registry.remove("fixture")).toBe(true);
  expect(registry.get("fixture")).toBeNull();
  expect(registry.remove("fixture")).toBe(false);
  writeFileSync(file, "bad JSON");
  expect(() => registry.list()).toThrow();
});
