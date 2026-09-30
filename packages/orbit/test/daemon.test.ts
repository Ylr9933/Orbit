import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { tryConnect } from "../src/client/index.ts";
import { readDaemonInfo } from "../src/config/daemon-info.ts";
import { orbitPaths } from "../src/config/paths.ts";
import { type StartedDaemon, startDaemon } from "../src/daemon/server.ts";

const home = mkdtempSync(join(tmpdir(), "orbit-test-"));
const paths = orbitPaths({ ORBIT_HOME: home });
let daemon: StartedDaemon;

beforeAll(async () => {
  daemon = await startDaemon(paths, 0);
});
afterAll(async () => {
  await daemon.stop();
  rmSync(home, { recursive: true, force: true });
});

describe("daemon", () => {
  it("publishes its endpoint with a private token file", () => {
    expect(readDaemonInfo(paths)?.url).toBe(daemon.url);
    expect(statSync(paths.daemonFile).mode & 0o777).toBe(0o600);
  });

  it("serves health and resources to an authorized client", async () => {
    const client = await tryConnect(paths);
    expect(client).not.toBeNull();
    expect((await client?.health())?.pid).toBe(process.pid);
    const r = await client?.resources();
    expect(r?.cpu.count).toBeGreaterThan(0);
    expect(r?.memory.totalGB).toBeGreaterThan(0);
  });

  it("rejects requests without the token", async () => {
    const res = await fetch(`${daemon.url}/api/v1/health`);
    expect(res.status).toBe(401);
  });
});
