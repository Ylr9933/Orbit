// Harbor task format: <task>/{task.toml, instruction.md, environment/Dockerfile, tests/, solution/}.
// Orbit runs the solve phase in the task environment and the verifier in a separate container built
// from tests/Dockerfile, with the declared artifacts copied across (environment_mode = "separate").
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, join, relative } from "node:path";
import { parse as parseToml } from "smol-toml";
import type { Benchmark, BenchTask, Method, RunSpecInput } from "../contracts/index.ts";
import { type Adapter, agentCommand, type ScoreResult } from "./adapter.ts";

export interface Artifact {
  /** Absolute path in the solve container. */
  source: string;
  /** Absolute path in the verifier container. */
  destination: string;
}

export interface HarborTask {
  id: string;
  dir: string;
  title: string | null;
  supported: boolean;
  reason: string | null;
  artifacts: Artifact[];
  agentTimeoutSec: number | null;
  verifierTimeoutSec: number | null;
  env: Resources & { network: boolean; vars: Record<string, string> };
  solutionEnv: Record<string, string>;
  verifier: Resources & { network: boolean; vars: Record<string, string> };
  tags: Record<string, string>;
}

interface Resources {
  cpus: number;
  memGB: number;
  gpus: number;
}

type Table = Record<string, unknown>;
const table = (v: unknown): Table => (v && typeof v === "object" ? (v as Table) : {});
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

function vars(v: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, x] of Object.entries(table(v))) out[k] = String(x);
  return out;
}

function resources(t: Table, fallback?: Resources): Resources {
  return {
    cpus: num(t.cpus) ?? fallback?.cpus ?? 2,
    memGB: (num(t.memory_mb) ?? (fallback ? fallback.memGB * 1024 : 4096)) / 1024,
    gpus: num(t.gpus) ?? fallback?.gpus ?? 0,
  };
}

const trimSlash = (p: string) => (p.length > 1 ? p.replace(/\/+$/, "") : p);

/** `artifacts` entries: strings, or `{source, destination?, exclude?, service?}` tables. */
export function parseArtifacts(v: unknown): { artifacts: Artifact[]; skipped: string[] } {
  const artifacts: Artifact[] = [];
  const skipped: string[] = [];
  for (const a of Array.isArray(v) ? v : []) {
    if (typeof a === "string") {
      artifacts.push({ source: trimSlash(a), destination: trimSlash(a) });
      continue;
    }
    const t = table(a);
    const source = str(t.source);
    if (!source) continue;
    const exclude = Array.isArray(t.exclude) ? t.exclude : [];
    const service = str(t.service);
    // `exclude = ["*"]` placeholders carry nothing; other services only exist with compose.
    if (exclude.includes("*") || (service && service !== "main")) {
      skipped.push(source);
      continue;
    }
    const dest = str(t.destination);
    artifacts.push({
      source: trimSlash(source),
      destination: trimSlash(dest?.startsWith("/") ? dest : source),
    });
  }
  return { artifacts, skipped };
}

export function parseHarborTask(dir: string, id: string): HarborTask {
  const toml = table(parseToml(readFileSync(join(dir, "task.toml"), "utf8")));
  const task = table(toml.task);
  const meta = table(toml.metadata);
  const environment = table(toml.environment);
  const verifier = table(toml.verifier);
  const verifierEnv = table(verifier.environment);
  const envRes = resources(environment);
  const problems: string[] = [];
  if (
    existsSync(join(dir, "environment", "docker-compose.yaml")) ||
    existsSync(join(dir, "environment", "docker-compose.yml"))
  )
    problems.push("docker-compose environments are not supported");
  if (!existsSync(join(dir, "environment", "Dockerfile")))
    problems.push("environment/Dockerfile missing");
  if (!existsSync(join(dir, "instruction.md"))) problems.push("instruction.md missing");
  const mode = str(verifier.environment_mode) ?? "shared";
  if (mode === "separate" && !existsSync(join(dir, "tests", "Dockerfile")))
    problems.push("tests/Dockerfile missing");
  if (mode !== "separate") problems.push(`verifier environment_mode "${mode}" is not supported`);
  const tags: Record<string, string> = {};
  for (const k of ["domain", "field", "subfield"]) {
    const v = str(meta[k]);
    if (v) tags[k] = v;
  }
  return {
    id,
    dir,
    title: str(task.description) ?? str(task.name),
    supported: problems.length === 0,
    reason: problems.length ? problems.join("; ") : null,
    artifacts: parseArtifacts(toml.artifacts).artifacts,
    agentTimeoutSec: num(table(toml.agent).timeout_sec),
    verifierTimeoutSec: num(verifier.timeout_sec),
    env: {
      ...envRes,
      network: (str(environment.network_mode) ?? "public") !== "no-network",
      vars: vars(environment.env),
    },
    solutionEnv: vars(table(toml.solution).env),
    verifier: {
      ...resources(verifierEnv, envRes),
      network: (str(verifierEnv.network_mode) ?? "no-network") !== "no-network",
      vars: vars(verifier.env),
    },
    tags,
  };
}

/** Task directories (containing task.toml) under `root/tasks` or `root`; ids are directory names. */
export function findHarborTasks(root: string): HarborTask[] {
  const base = existsSync(join(root, "tasks")) ? join(root, "tasks") : root;
  const dirs: string[] = [];
  const walk = (d: string, depth: number) => {
    if (existsSync(join(d, "task.toml"))) {
      dirs.push(d);
      return;
    }
    if (depth === 0) return;
    let names: string[] = [];
    try {
      names = readdirSync(d);
    } catch {
      return;
    }
    for (const n of names.sort()) {
      if (n.startsWith(".")) continue;
      const p = join(d, n);
      if (statSync(p, { throwIfNoEntry: false })?.isDirectory()) walk(p, depth - 1);
    }
  };
  walk(base, 4);
  const counts = new Map<string, number>();
  for (const d of dirs) counts.set(basename(d), (counts.get(basename(d)) ?? 0) + 1);
  return dirs.map((d) => {
    const id = (counts.get(basename(d)) ?? 0) > 1 ? relative(base, d) : basename(d);
    try {
      return parseHarborTask(d, id);
    } catch (e) {
      return brokenTask(d, id, `task.toml: ${(e as Error).message}`);
    }
  });
}

function brokenTask(dir: string, id: string, reason: string): HarborTask {
  const r = { cpus: 1, memGB: 1, gpus: 0, network: false, vars: {} };
  return {
    id,
    dir,
    title: null,
    supported: false,
    reason,
    artifacts: [],
    agentTimeoutSec: null,
    verifierTimeoutSec: null,
    env: r,
    solutionEnv: {},
    verifier: r,
    tags: {},
  };
}

export const toBenchTask = (t: HarborTask): BenchTask => ({
  id: t.id,
  title: t.title,
  supported: t.supported,
  reason: t.reason,
  tags: t.tags,
});

/** Solve run: the Agent (or the oracle solution) in the task environment, as the image's user. */
export function harborSolveSpec(
  t: HarborTask,
  method: Method,
  staging: string,
  timeoutMin?: number,
): RunSpecInput {
  const mounts: RunSpecInput["mounts"] = [];
  let command: string[];
  let env = t.env.vars;
  if (method.agent === "oracle") {
    const sol = join(staging, "solution");
    mkdirSync(staging, { recursive: true });
    cpSync(join(t.dir, "solution"), sol, { recursive: true });
    mounts.push({ source: sol, target: "/solution", mode: "rw" });
    command = ["bash", "/solution/solve.sh"];
    env = { ...env, ...t.solutionEnv };
  } else if (method.agent === "empty") {
    command = ["true"];
  } else {
    command = agentCommand(method, readFileSync(join(t.dir, "instruction.md"), "utf8"));
  }
  return {
    dockerfile: join(t.dir, "environment", "Dockerfile"),
    command,
    resources: { gpus: t.env.gpus, cpus: t.env.cpus, memGB: t.env.memGB },
    mounts,
    env,
    network: t.env.network || Boolean(method.auth),
    auth: method.auth,
    agentBundle: method.bundle,
    snapshot: false,
    root: true,
    workdir: "image",
    timeoutMin: timeoutMin ?? (t.agentTimeoutSec ? t.agentTimeoutSec / 60 : undefined),
    collect: t.artifacts.map((a) => a.source),
  };
}

/**
 * Verify run: tests/Dockerfile with the collected artifacts copied in; `/logs/verifier` (reward) is
 * collected back. Missing artifacts are left out, so the tests see what the Agent actually produced.
 */
export function harborVerifySpec(
  t: HarborTask,
  solveOutput: string,
  staging: string,
): { spec: RunSpecInput; missing: string[] } {
  const mounts: RunSpecInput["mounts"] = [];
  const missing: string[] = [];
  for (const a of t.artifacts) {
    const src = join(solveOutput, "collected", a.source);
    if (!existsSync(src)) {
      missing.push(a.source);
      continue;
    }
    const copy = join(staging, "artifacts", a.source);
    mkdirSync(dirname(copy), { recursive: true });
    cpSync(src, copy, { recursive: true });
    mounts.push({ source: copy, target: a.destination, mode: "rw" });
  }
  return {
    spec: {
      dockerfile: join(t.dir, "tests", "Dockerfile"),
      command: ["sh", "-c", "mkdir -p /logs/verifier /logs/agent && exec bash /tests/test.sh"],
      resources: { gpus: t.verifier.gpus, cpus: t.verifier.cpus, memGB: t.verifier.memGB },
      mounts,
      env: t.verifier.vars,
      network: t.verifier.network,
      snapshot: false,
      root: true,
      workdir: "image",
      priority: 1,
      timeoutMin: t.verifierTimeoutSec ? t.verifierTimeoutSec / 60 : 10,
      collect: ["/logs/verifier"],
    },
    missing,
  };
}

/** Reward from `reward.json` (the `reward` key, or its only key) or `reward.txt` (one number). */
export function harborReward(verifierDir: string): ScoreResult {
  const json = join(verifierDir, "reward.json");
  const txt = join(verifierDir, "reward.txt");
  const bad = (issue: string): ScoreResult => ({
    score: null,
    maxScore: 1,
    issues: [issue],
    invalid: true,
  });
  if (existsSync(json)) {
    let v: unknown;
    try {
      v = JSON.parse(readFileSync(json, "utf8"));
    } catch {
      return bad("reward.json is not valid JSON");
    }
    const t = table(v);
    const keys = Object.keys(t);
    const pick = "reward" in t ? t.reward : keys.length === 1 ? t[keys[0] as string] : undefined;
    const n = num(pick);
    if (n === null)
      return bad(`reward.json has no single numeric reward (keys: ${keys.join(", ")})`);
    return { score: n, maxScore: 1, issues: [], invalid: false };
  }
  if (existsSync(txt)) {
    const raw = readFileSync(txt, "utf8").trim();
    const n = Number(raw);
    if (raw === "" || !Number.isFinite(n))
      return bad(`reward.txt is not a number: ${raw.slice(0, 40)}`);
    return { score: n, maxScore: 1, issues: [], invalid: false };
  }
  return bad("verifier wrote no reward");
}

function harborTask(b: Benchmark, id: string): HarborTask {
  const t = findHarborTasks(b.path).find((x) => x.id === id);
  if (!t) throw new Error(`task not found: ${id}`);
  if (!t.supported) throw new Error(`task ${id} is not supported: ${t.reason}`);
  return t;
}

export const harborAdapter: Adapter = {
  tasks: (b) => findHarborTasks(b.path).map(toBenchTask),
  solveSpec: (ctx) => {
    const spec = harborSolveSpec(
      harborTask(ctx.benchmark, ctx.task),
      ctx.method,
      ctx.staging,
      ctx.timeoutMin,
    );
    return { ...spec, env: { ...ctx.benchmark.env, ...spec.env } };
  },
  verifySpec: (ctx, _solve, solveOutput) => {
    const t = harborTask(ctx.benchmark, ctx.task);
    const { spec, missing } = harborVerifySpec(t, solveOutput, ctx.staging);
    return {
      // `passEnv` names grader secrets: the verifier gets them, the Agent under test does not.
      spec: { ...spec, env: { ...ctx.benchmark.env, ...spec.env }, passEnv: ctx.benchmark.passEnv },
      issues: missing.map((m) => `artifact not produced: ${m}`),
    };
  },
  score: (_ctx, _solve, _solveOutput, verifyOutput) =>
    harborReward(join(verifyOutput, "collected", "logs", "verifier")),
};
