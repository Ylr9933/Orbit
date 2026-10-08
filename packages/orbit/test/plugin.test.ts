import { Command } from "commander";
import { afterEach, describe, expect, it, vi } from "vitest";
import { registerPlugin } from "../src/cli/plugin.ts";
import { exec } from "../src/lib/exec.ts";

vi.mock("../src/lib/exec.ts", () => ({ exec: vi.fn() }));

async function install(args: string[] = []) {
  const program = new Command();
  registerPlugin(program);
  await program.parseAsync(["plugin", "install", ...args], { from: "user" });
}

afterEach(() => vi.resetAllMocks());

describe("Claude plugin installation (explicit command fake)", () => {
  it("registers the marketplace before installing the user plugin", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install();
    expect(vi.mocked(exec).mock.calls.map((call) => call.slice(0, 2))).toEqual([
      ["claude", ["plugin", "marketplace", "add", "zjunlp/Orbit"]],
      ["claude", ["plugin", "install", "orbit@orbit", "--scope", "user"]],
    ]);
  });

  it("stops on registration failure without installing from an unrelated marketplace", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 1, stdout: "", stderr: "" });
    await expect(install()).rejects.toThrow("exited with 1");
    expect(exec).toHaveBeenCalledTimes(1);
  });

  it("resolves a local checkout before handing it to Claude Code", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install(["--source", "."]);
    expect(vi.mocked(exec).mock.calls[0]?.[1]).toEqual([
      "plugin",
      "marketplace",
      "add",
      process.cwd(),
    ]);
  });

  it("reports missing Claude Code and installation failures", async () => {
    vi.mocked(exec).mockResolvedValueOnce({ code: 127, stdout: "", stderr: "" });
    await expect(install()).rejects.toThrow("Claude Code is required");
    vi.mocked(exec)
      .mockResolvedValueOnce({ code: 0, stdout: "", stderr: "" })
      .mockResolvedValueOnce({ code: 1, stdout: "", stderr: "" });
    await expect(install(["--source", "/tmp/marketplace with spaces"])).rejects.toThrow(
      "exited with 1",
    );
    expect(vi.mocked(exec).mock.calls[1]?.[1]).toEqual([
      "plugin",
      "marketplace",
      "add",
      "/tmp/marketplace with spaces",
    ]);
  });
});
