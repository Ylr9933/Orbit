import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { acquireProcessLock } from "../src/lib/lock.ts";

const homes: string[] = [];
afterEach(() => {
  for (const h of homes.splice(0)) rmSync(h, { recursive: true, force: true });
});
function file() {
  const dir = mkdtempSync(join(tmpdir(), "orbit-lock-"));
  homes.push(dir);
  return join(dir, "daemon.lock");
}

it("names the live owner and releases only its own lock", () => {
  const path = file();
  const release = acquireProcessLock(path);
  expect(statSync(path).mode & 0o777).toBe(0o600);
  expect(() => acquireProcessLock(path)).toThrow(`running process PID ${process.pid}`);
  release();
  const next = acquireProcessLock(path);
  release();
  expect(existsSync(path)).toBe(true);
  next();
  expect(existsSync(path)).toBe(false);
});

it.each([2147483647, process.pid])(
  "takes over a dead or reused PID (%i), including an abandoned reclaimer",
  (pid) => {
    const path = file();
    const stale = JSON.stringify({ pid, start: "previous-process-start", nonce: "stale" });
    writeFileSync(path, stale);
    writeFileSync(`${path}.reclaim`, stale);
    const release = acquireProcessLock(path);
    expect(JSON.parse(readFileSync(path, "utf8")).pid).toBe(process.pid);
    expect(existsSync(`${path}.reclaim`)).toBe(false);
    release();
  },
);

it("admits only one process when several reclaim the same stale lock", async () => {
  const path = file();
  writeFileSync(path, JSON.stringify({ pid: 2147483647, start: "gone", nonce: "stale" }));
  const script = `
    import { acquireProcessLock } from ${JSON.stringify(new URL("../src/lib/lock.ts", import.meta.url).href)};
    try {
      const release = acquireProcessLock(process.argv[1]);
      process.on('message', () => { release(); process.disconnect(); });
      process.send(true);
    } catch { process.send(false); process.disconnect(); }
  `;
  const children = Array.from({ length: 6 }, () =>
    spawn(process.execPath, ["--input-type=module", "-e", script, path], {
      stdio: ["ignore", "ignore", "pipe", "ipc"],
    }),
  );
  const closed = children.map(
    (c) => new Promise<void>((resolve) => c.once("exit", () => resolve())),
  );
  try {
    const results = await Promise.all(
      children.map(
        (c) =>
          new Promise<unknown>((resolve, reject) => {
            c.once("message", resolve);
            c.once("error", reject);
          }),
      ),
    );
    expect(results.filter(Boolean)).toHaveLength(1);
  } finally {
    for (const c of children) if (c.connected) c.send("release");
    await Promise.all(closed);
  }
  expect(existsSync(path)).toBe(false);
});
