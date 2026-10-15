import * as fs from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterAll, afterEach, expect, it, vi } from "vitest";
import {
  ensureHome,
  orbitPaths,
  privateStateCheck,
  tightenPrivateState,
} from "../src/config/paths.ts";
import { runDoctor } from "../src/daemon/doctor.ts";
import { Store } from "../src/store/index.ts";

vi.mock("node:fs", async (original) => {
  const fs = await original<typeof import("node:fs")>();
  return { ...fs, lstatSync: vi.fn(fs.lstatSync), fchmodSync: vi.fn(fs.fchmodSync) };
});

// Doctor tool probes are explicit doubles; permission checks use real temporary files.
vi.mock("../src/lib/exec.ts", () => ({
  exec: vi.fn(async () => ({ code: 0, stdout: "fixture", stderr: "" })),
}));
vi.mock("../src/harness/index.ts", () => ({ hostCli: vi.fn(async () => null) }));

const root = fs.mkdtempSync(join(tmpdir(), "orbit-private-state-"));
const fixture = (name: string) =>
  orbitPaths({ ORBIT_HOME: join(root, name, "home"), ORBIT_DATA: join(root, name, "data") });
const mode = (path: string) => fs.statSync(path).mode & 0o777;
afterEach(() => {
  vi.mocked(fs.lstatSync).mockReset();
  vi.mocked(fs.fchmodSync).mockReset();
  vi.restoreAllMocks();
});
afterAll(() => fs.rmSync(root, { recursive: true, force: true }));

it("creates private directories and SQLite files regardless of the usual umask", () => {
  const paths = fixture("new");
  ensureHome(paths);
  for (const path of [
    paths.home,
    paths.data,
    paths.runs,
    paths.tmp,
    paths.bench,
    dirname(paths.bundles),
    paths.bundles,
  ])
    expect(mode(path), path).toBe(0o700);
  const store = new Store(paths.db);
  try {
    store.db.exec("CREATE TABLE fixture (id INTEGER)");
    for (const path of [paths.db, `${paths.db}-wal`, `${paths.db}-shm`])
      expect(mode(path), path).toBe(0o600);
    expect(privateStateCheck(paths).warn).toBe(false);
  } finally {
    store.close();
  }
});

it("tightens only named paths, logs changes once and exposes insecure modes in doctor", async () => {
  const paths = fixture("existing");
  ensureHome(paths);
  const dirs = [
    paths.home,
    paths.runs,
    paths.tmp,
    paths.bench,
    dirname(paths.bundles),
    paths.bundles,
  ];
  for (const path of [...dirs, paths.data]) fs.chmodSync(path, 0o775);
  const files = [paths.db, `${paths.db}-wal`, `${paths.db}-shm`];
  for (const path of files) {
    fs.writeFileSync(path, "fixture");
    fs.chmodSync(path, 0o644);
  }
  const runDir = join(paths.runs, "existing-run");
  fs.mkdirSync(runDir);
  fs.chmodSync(runDir, 0o775);
  const artifact = join(runDir, "artifact");
  fs.writeFileSync(artifact, "fixture");
  fs.chmodSync(artifact, 0o664);
  const before = (await runDoctor(paths)).checks.find((c) => c.name === "private state");
  expect(before).toMatchObject({ ok: true, warn: true });
  for (const path of [...dirs, ...files]) expect(before?.detail).toContain(path);
  const log = vi.fn();
  tightenPrivateState(paths, log);
  for (const path of dirs) expect(mode(path), path).toBe(0o700);
  for (const path of files) expect(mode(path), path).toBe(0o600);
  expect([mode(paths.data), mode(runDir), mode(artifact)]).toEqual([0o775, 0o775, 0o664]);
  expect(log).toHaveBeenCalledTimes(dirs.length + files.length);
  tightenPrivateState(paths, log);
  expect(log).toHaveBeenCalledTimes(dirs.length + files.length);
  expect(privateStateCheck(paths).warn).toBe(false);
});

it("does not follow symlinks or chmod another owner's paths", async () => {
  const paths = fixture("ownership");
  ensureHome(paths);
  const outside = join(root, "other-file");
  fs.writeFileSync(outside, "fixture");
  fs.chmodSync(outside, 0o644);
  fs.symlinkSync(outside, paths.db);
  fs.chmodSync(paths.runs, 0o775);
  const { lstatSync: lstat } = await vi.importActual<typeof fs>("node:fs");
  vi.mocked(fs.lstatSync).mockImplementation(((path: fs.PathLike) => {
    const st = lstat(path);
    if (path === paths.runs) st.uid = (process.getuid?.() ?? 0) + 1;
    return st;
  }) as typeof fs.lstatSync);
  const log = vi.fn();
  tightenPrivateState(paths, log);
  expect(mode(outside)).toBe(0o644);
  expect(mode(paths.runs)).toBe(0o775);
  expect(privateStateCheck(paths)).toMatchObject({
    warn: true,
    detail: expect.stringContaining("owned by another user"),
  });
  expect(log).toHaveBeenCalledWith(expect.stringContaining("skipped"));
});

it("continues after EPERM and leaves a doctor warning", () => {
  const paths = fixture("denied");
  ensureHome(paths);
  fs.chmodSync(paths.home, 0o775);
  vi.mocked(fs.fchmodSync).mockImplementationOnce(() => {
    throw Object.assign(new Error("fixture denial"), { code: "EPERM" });
  });
  const log = vi.fn();
  expect(() => tightenPrivateState(paths, log)).not.toThrow();
  expect(mode(paths.home)).toBe(0o775);
  expect(log).toHaveBeenCalledWith(expect.stringContaining("EPERM"));
  expect(privateStateCheck(paths)).toMatchObject({
    warn: true,
    detail: expect.stringContaining(paths.home),
  });
});
