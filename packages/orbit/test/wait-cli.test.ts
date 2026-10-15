import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it, vi } from "vitest";
import { createProgram } from "../src/cli/program.ts";
import { OrbitClient, tryConnect } from "../src/client/index.ts";
import { orbitPaths } from "../src/config/paths.ts";
import type { Run } from "../src/contracts/index.ts";

vi.mock("../src/client/index.ts", async (original) => ({
  ...(await original<typeof import("../src/client/index.ts")>()),
  tryConnect: vi.fn(),
}));

it("waits for group members beyond 500, deduplicates explicit IDs and includes late failures", async () => {
  const home = mkdtempSync(join(tmpdir(), "orbit-wait-cli-"));
  const exitCode = process.exitCode;
  try {
    const client = new OrbitClient({ url: "http://unused", token: "fixture", pid: 0 });
    vi.mocked(tryConnect).mockResolvedValue(client);
    vi.spyOn(console, "log").mockImplementation(() => {});
    const runs = Array.from(
      { length: 501 },
      (_, i) =>
        ({
          id: `run-${i}`,
          state: i === 500 ? "failed" : "succeeded",
          cleanup: "done",
        }) as Run,
    );
    const list = vi
      .spyOn(client, "list")
      .mockImplementation(async (f) => runs.slice(0, f?.limit ?? 500));
    const get = vi
      .spyOn(client, "get")
      .mockImplementation(async (id) => runs.find((r) => r.id === id) as Run);
    await createProgram({ runDaemon: vi.fn() }, orbitPaths({ ORBIT_HOME: home })).parseAsync(
      ["wait", "run-0", "-g", "fixture"],
      { from: "user" },
    );
    expect(list).toHaveBeenCalledWith({ group: "fixture", limit: 10_000 });
    expect(get).toHaveBeenCalledTimes(501);
    expect(get).toHaveBeenCalledWith("run-500");
    expect(process.exitCode).toBe(1);
  } finally {
    process.exitCode = exitCode;
    vi.restoreAllMocks();
    rmSync(home, { recursive: true, force: true });
  }
});
