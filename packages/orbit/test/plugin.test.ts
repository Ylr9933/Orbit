import { Command } from "commander";
import { afterEach, describe, expect, it, vi } from "vitest";
import { registerPlugin } from "../src/cli/plugin.ts";
import { exec } from "../src/lib/exec.ts";
import { VERSION } from "../src/lib/version.ts";

vi.mock("../src/lib/exec.ts", () => ({ exec: vi.fn() }));

async function install(args: string[] = []) {
  const program = new Command().exitOverride().configureOutput({ writeErr: () => {} });
  registerPlugin(program);
  await program.parseAsync(["plugin", "install", ...args], { from: "user" });
}

afterEach(() => vi.resetAllMocks());

describe("native plugin installation (explicit command fake)", () => {
  it("registers the marketplace before installing the user plugin", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install();
    expect(vi.mocked(exec).mock.calls.map((call) => call.slice(0, 2))).toEqual([
      ["claude", ["plugin", "install", "--help"]],
      ["claude", ["plugin", "marketplace", "add", "zjunlp/Orbit"]],
      ["claude", ["plugin", "install", "orbit@orbit", "--scope", "user"]],
    ]);
  });

  it("stops on registration failure without installing from an unrelated marketplace", async () => {
    vi.mocked(exec)
      .mockResolvedValueOnce({ code: 0, stdout: "", stderr: "" })
      .mockResolvedValueOnce({ code: 1, stdout: "", stderr: "" });
    await expect(install()).rejects.toThrow("exited with 1");
    expect(exec).toHaveBeenCalledTimes(2);
  });

  it("resolves a local checkout before handing it to Claude Code", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install(["--source", "."]);
    expect(vi.mocked(exec).mock.calls[1]?.[1]).toEqual([
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
      .mockResolvedValueOnce({ code: 0, stdout: "", stderr: "" })
      .mockResolvedValueOnce({ code: 1, stdout: "", stderr: "" });
    await expect(
      install(["--source", "https://example.test/marketplace with spaces.git"]),
    ).rejects.toThrow("exited with 1");
    expect(vi.mocked(exec).mock.calls[2]?.[1]).toEqual([
      "plugin",
      "marketplace",
      "add",
      "https://example.test/marketplace with spaces.git",
    ]);
  });

  it("uses Codex's native add command and stops unsupported CLIs before registration", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install(["codex"]);
    expect(vi.mocked(exec).mock.calls.map((call) => call.slice(0, 2))).toEqual([
      ["codex", ["plugin", "add", "--help"]],
      ["codex", ["plugin", "marketplace", "add", "zjunlp/Orbit"]],
      ["codex", ["plugin", "add", "orbit@orbit"]],
    ]);
    vi.mocked(exec).mockReset().mockResolvedValue({ code: 2, stdout: "", stderr: "" });
    await expect(install(["codex"])).rejects.toThrow("upgrade it");
    expect(exec).toHaveBeenCalledTimes(1);
  });

  it("adds the matching npm version to the explicitly selected dsh profile", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install(["dsh", "--profile", "headless"]);
    expect(vi.mocked(exec).mock.calls.at(-1)?.slice(0, 2)).toEqual([
      "dsh",
      ["plugin", "--profile", "headless", "add", `@zjunlp/orbit@${VERSION}`],
    ]);
  });

  it.each([[], ["--profile", "desktop"], ["--profile", "sdk-minimal"], ["--profile", "../unsafe"]])(
    "rejects missing or invalid dsh profiles: %j",
    async (...args) => {
      await expect(install(["dsh", ...args])).rejects.toThrow(/profile/);
      expect(exec).not.toHaveBeenCalled();
    },
  );

  it("copies local dsh packages into the profile instead of linking an external directory", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install(["dsh", "--profile", "headless", "--source", "."]);
    expect(vi.mocked(exec).mock.calls.at(-1)?.[1]).toEqual([
      "plugin",
      "--profile",
      "headless",
      "add",
      `file:${process.cwd()}`,
    ]);
  });

  it.each(["claude", "codex", "pi"])("rejects a local file for %s", async (agent) => {
    await expect(install([agent, "--source", "./package.json"])).rejects.toThrow(
      "source directory",
    );
    expect(exec).not.toHaveBeenCalled();
  });

  it.each(["codex", "dsh", "pi"])("reports a missing %s CLI", async (agent) => {
    vi.mocked(exec).mockResolvedValue({ code: 127, stdout: "", stderr: "" });
    await expect(
      install([agent, ...(agent === "dsh" ? ["--profile", "headless"] : [])]),
    ).rejects.toThrow("is required");
    expect(exec).toHaveBeenCalledTimes(1);
  });

  it("rejects irrelevant profiles and unknown agents before invoking an installer", async () => {
    await expect(install(["codex", "--profile", "headless"])).rejects.toThrow(
      "only supported for dsh",
    );
    await expect(install(["unknown"])).rejects.toThrow("Allowed choices");
    expect(exec).not.toHaveBeenCalled();
  });

  it("installs pi's npm source once and supports local packages", async () => {
    vi.mocked(exec).mockResolvedValue({ code: 0, stdout: "", stderr: "" });
    await install(["pi"]);
    expect(vi.mocked(exec).mock.calls.at(-1)?.slice(0, 2)).toEqual([
      "pi",
      ["install", `npm:@zjunlp/orbit@${VERSION}`],
    ]);
    await install(["pi", "--source", "npm:@zjunlp/orbit@next"]);
    expect(vi.mocked(exec).mock.calls.at(-1)?.[1]).toEqual(["install", "npm:@zjunlp/orbit@next"]);
    await install(["pi", "--source", "."]);
    expect(vi.mocked(exec).mock.calls.at(-1)?.[1]).toEqual(["install", process.cwd()]);
  });

  it.each(["./missing-orbit-plugin-source", "--unsafe", ""])(
    "rejects an invalid source without side effects: %s",
    async (source) => {
      await expect(install(["--source", source])).rejects.toThrow(/source/);
      expect(exec).not.toHaveBeenCalled();
    },
  );
});
