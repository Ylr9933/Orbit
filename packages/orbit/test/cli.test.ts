import { describe, expect, it } from "vitest";
import { detectAgent } from "../src/cli/agent.ts";
import { expandGrid, substitute } from "../src/cli/program.ts";
import { envFileText, runArgs } from "../src/executor/docker.ts";

describe("sweep helpers", () => {
  it("expands the cartesian product and substitutes placeholders", () => {
    const grid = expandGrid(["seed=1,2", "lr=1e-3,1e-4"]);
    expect(grid).toHaveLength(4);
    expect(grid[1]).toEqual({ seed: "1", lr: "1e-4" });
    expect(substitute(["train.py", "--seed={seed}", "{missing}"], { seed: "7" })).toEqual([
      "train.py",
      "--seed=7",
      "{missing}",
    ]);
    expect(() => expandGrid(["seed"])).toThrow();
  });
});

describe("detectAgent", () => {
  it("prefers explicit ORBIT_AGENT, then Claude Code env", () => {
    expect(detectAgent({ ORBIT_AGENT: "codex:abc" }, "/p")).toEqual({
      harness: "codex",
      sessionId: "abc",
      cwd: "/p",
    });
    expect(detectAgent({ CLAUDECODE: "1", CLAUDE_CODE_SESSION_ID: "s1" }, "/p", [])).toEqual({
      harness: "claude-code",
      sessionId: "s1",
      cwd: "/p",
    });
  });

  it("lets the nearest agent process win when agents are nested", () => {
    const env = { CLAUDECODE: "1", CLAUDE_CODE_SESSION_ID: "s1", CODEX_THREAD_ID: "t1" };
    expect(detectAgent(env, "/p", ["bash", "codex", "node", "claude"])).toEqual({
      harness: "codex",
      sessionId: "t1",
      cwd: "/p",
    });
    expect(detectAgent(env, "/p", ["bash", "claude", "codex"])?.harness).toBe("claude-code");
    expect(detectAgent({ CODEX_THREAD_ID: "t1" }, "/p", [])?.sessionId).toBe("t1");
    expect(detectAgent({}, "/p", ["bash"])).toBeUndefined();
  });
});

describe("docker run args", () => {
  const base = {
    name: "orbit-x",
    image: "img",
    command: ["python", "t.py"],
    labels: { "orbit.run": "x" },
    gpuIds: ["GPU-a", "GPU-b"],
    cpus: 2,
    memGB: 8,
    mounts: [{ source: "/d", target: "/data", mode: "ro" as const }],
    env: { A: "1" },
    workdir: "/workspace",
    network: "none" as const,
    user: "1000:1000",
  };
  it("uses CDI devices when available", () => {
    const a = runArgs({ ...base, gpuMode: "cdi" });
    expect(a).toContain("nvidia.com/gpu=GPU-a");
    expect(a).toContain("type=bind,source=/d,target=/data,readonly");
    expect(a.slice(-3)).toEqual(["img", "python", "t.py"]);
    expect(a.join(" ")).toContain("--network none");
  });
  it("falls back to --gpus", () => {
    expect(runArgs({ ...base, gpuMode: "gpus" })).toContain('"device=GPU-a,GPU-b"');
  });
  it("passes secrets by env file and supports host network", () => {
    const a = runArgs({ ...base, gpuMode: "cdi", network: "host", envFile: "/t/x.env" }).join(" ");
    expect(a).toContain("--env-file /t/x.env");
    expect(a).toContain("--network host");
    expect(runArgs({ ...base, gpuMode: "cdi", network: "bridge" })).not.toContain("--network");
    expect(envFileText({ K: "v=1" })).toBe("K=v=1\n");
    expect(() => envFileText({ K: "a\nb" })).toThrow();
  });
});
