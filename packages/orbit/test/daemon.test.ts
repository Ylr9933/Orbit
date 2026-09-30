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
  daemon = await startDaemon(paths, { port: 0, tickMs: 200 });
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

  it("logs the browser in with a cookie and only redirects to local paths", async () => {
    const token = readDaemonInfo(paths)?.token ?? "";
    const login = (next: string) =>
      fetch(`${daemon.url}/login?token=${token}&next=${encodeURIComponent(next)}`, {
        redirect: "manual",
      });
    const ok = await login("/runs/x?tab=logs");
    expect(ok.headers.get("location")).toBe("/runs/x?tab=logs");
    const cookie = ok.headers.get("set-cookie")?.split(";")[0] ?? "";
    expect(cookie).toContain("orbit_token=");
    expect((await fetch(`${daemon.url}/api/v1/health`, { headers: { cookie } })).status).toBe(200);
    expect((await login("//evil.example")).headers.get("location")).toBe("/");
    expect((await login("https://evil.example")).headers.get("location")).toBe("/");
  });
});
