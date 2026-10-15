import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { callAdapter } from "../src/bench/protocol.ts";

it("rejects on timeout and kills a grandchild that ignores TERM while holding stdout", async () => {
  const dir = mkdtempSync(join(tmpdir(), "orbit-adapter-timeout-"));
  const child = `
    const fs = require('node:fs');
    process.on('SIGTERM', () => {});
    fs.writeFileSync('grandchild', String(process.pid));
    setInterval(() => {}, 1000);
  `;
  const parent = `
    require('node:fs').writeFileSync('parent', String(process.pid));
    const c = require('node:child_process').spawn(process.execPath, ['-e', ${JSON.stringify(child)}],
      { stdio: ['ignore', process.stdout, process.stderr] });
    c.unref();
  `;
  const alive = (pid: number) => {
    try {
      const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
      return stat.slice(stat.lastIndexOf(")") + 2).split(" ")[0] !== "Z";
    } catch {
      return false;
    }
  };
  try {
    const result = callAdapter(
      [process.execPath, "-e", parent],
      dir,
      {
        protocol: 1,
        op: "tasks",
        benchmark: { name: "fixture", path: dir, config: {} },
      },
      1200,
    );
    await expect(result).rejects.toThrow(/timed out/);
    expect(existsSync(join(dir, "grandchild"))).toBe(true);
    const pid = Number(readFileSync(join(dir, "grandchild"), "utf8"));
    expect(alive(pid)).toBe(true);
    await expect.poll(() => alive(pid), { timeout: 2000 }).toBe(false);
  } finally {
    for (const file of ["parent", "grandchild"]) {
      if (!existsSync(join(dir, file))) continue;
      const pid = Number(readFileSync(join(dir, file), "utf8"));
      if (alive(pid)) process.kill(pid, "SIGKILL");
    }
    rmSync(dir, { recursive: true, force: true });
  }
});

it("drains all stdout on successful adapters", async () => {
  const dir = mkdtempSync(join(tmpdir(), "orbit-adapter-output-"));
  try {
    const size = 2 * 1024 * 1024;
    const reply = await callAdapter(
      [
        process.execPath,
        "-e",
        `
      process.stdout.write(JSON.stringify({ value: 'x'.repeat(${size}) }));
    `,
      ],
      dir,
      { protocol: 1, op: "tasks", benchmark: { name: "fixture", path: dir, config: {} } },
      5000,
    );
    expect(reply).toEqual({ value: "x".repeat(size) });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
