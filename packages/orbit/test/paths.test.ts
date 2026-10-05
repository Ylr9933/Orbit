import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { orbitPaths, readConfig, writeConfig } from "../src/config/paths.ts";
import { Folder, inFolder } from "../src/contracts/index.ts";

const home = mkdtempSync(join(tmpdir(), "orbit-paths-"));
afterAll(() => rmSync(home, { recursive: true, force: true }));

describe("data directory", () => {
  it("keeps run data in home by default, else the config file, else ORBIT_DATA", () => {
    const def = orbitPaths({ ORBIT_HOME: home });
    expect([def.data, def.dataSource, def.runs]).toEqual([home, "default", join(home, "runs")]);
    expect(def.db).toBe(join(home, "orbit.db"));
    writeConfig(def.config, { dataDir: "/big/orbit" });
    const cfg = orbitPaths({ ORBIT_HOME: home });
    expect([cfg.data, cfg.dataSource, cfg.runs, cfg.bench, cfg.bundles]).toEqual([
      "/big/orbit",
      "config",
      "/big/orbit/runs",
      "/big/orbit/bench",
      "/big/orbit/cache/bundles",
    ]);
    // Small state stays in home.
    expect([cfg.db, cfg.auth]).toEqual([join(home, "orbit.db"), join(home, "auth.json")]);
    expect(orbitPaths({ ORBIT_HOME: home, ORBIT_DATA: "/env" })).toMatchObject({
      data: "/env",
      dataSource: "env",
    });
    expect(() => orbitPaths({ ORBIT_HOME: home, ORBIT_DATA: "rel" })).toThrow(/absolute/);
    writeFileSync(def.config, JSON.stringify({ dataDir: "relative" }));
    expect(() => readConfig(def.config)).toThrow(/absolute path/);
    writeFileSync(def.config, "{");
    expect(() => readConfig(def.config)).toThrow(/not valid JSON/);
  });
});

describe("folders", () => {
  it("accepts slash-separated names and nests by prefix", () => {
    for (const ok of ["", "rcb", "rcb/noskills", "ResearchClawBench/v1.2_a-b", "实验/一"])
      expect(Folder.safeParse(ok).success, ok).toBe(true);
    for (const bad of ["/rcb", "rcb/", "a//b", "../x", "a/./b", "a b", "a\\b"])
      expect(Folder.safeParse(bad).success, bad).toBe(false);
    expect(inFolder("rcb/noskills", "rcb")).toBe(true);
    expect(inFolder("rcb", "rcb")).toBe(true);
    expect(inFolder("rcbx", "rcb")).toBe(false);
    expect(inFolder("x", "")).toBe(true);
  });
});
