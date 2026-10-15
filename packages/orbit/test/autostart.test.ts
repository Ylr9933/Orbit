import { execFile } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { expect, it } from "vitest";
import { readDaemonInfo } from "../src/config/daemon-info.ts";
import { orbitPaths } from "../src/config/paths.ts";

it("concurrent CLI auto-starts attach to one daemon in a temporary home", async () => {
  const home = mkdtempSync(join(tmpdir(), "orbit-autostart-"));
  const paths = orbitPaths({ ORBIT_HOME: home });
  const entry = join(home, "fixture.mjs");
  writeFileSync(
    entry,
    `
    import { appendFileSync, writeFileSync } from 'node:fs';
    import { connect } from ${JSON.stringify(new URL("../src/cli/program.ts", import.meta.url).href)};
    import { startDaemon } from ${JSON.stringify(new URL("../src/daemon/server.ts", import.meta.url).href)};
    import { orbitPaths } from ${JSON.stringify(new URL("../src/config/paths.ts", import.meta.url).href)};
    const paths = orbitPaths();
    if (process.argv[2] === 'daemon') {
      appendFileSync(paths.home + '/starts', 'started\\n');
      await new Promise(r => setTimeout(r, 200));
      const d = await startDaemon(paths, { port: 0, probe: async () => ({
        node: 'fixture', probedAt: new Date().toISOString(), gpus: [], gpuError: null,
        cpu: { count: 1, load1: 0, busy: 0 }, memory: { totalGB: 1, availableGB: 1 },
        disk: { path: paths.home, totalGB: 1, freeGB: 1 }
      }) });
      process.once('SIGTERM', async () => {
        await d.stop();
        writeFileSync(paths.home + '/stopped', 'done');
      });
    } else {
      console.log((await (await connect(paths)).health()).pid);
    }
  `,
  );
  try {
    const results = await Promise.all(
      Array.from({ length: 5 }, () =>
        promisify(execFile)(process.execPath, [entry], {
          env: { ...process.env, ORBIT_HOME: home, ORBIT_DATA: home, ORBIT_PORT: "0" },
          timeout: 15000,
        }),
      ),
    );
    const pids = results.map((r) => Number(r.stdout.trim()));
    expect(new Set(pids).size).toBe(1);
    expect(pids[0]).toBe(readDaemonInfo(paths)?.pid);
    expect(readFileSync(join(home, "starts"), "utf8")).toBe("started\n");
    expect(existsSync(join(home, "daemon.spawn.lock"))).toBe(false);
  } finally {
    const info = readDaemonInfo(paths);
    if (info) {
      process.kill(info.pid, "SIGTERM");
      await expect.poll(() => existsSync(join(home, "stopped")), { timeout: 5000 }).toBe(true);
    }
    rmSync(home, { recursive: true, force: true });
  }
}, 20000);
