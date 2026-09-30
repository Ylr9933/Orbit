import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Command } from "commander";
import type { OrbitClient } from "../client/index.ts";
import type {
  BenchCompare,
  BenchJobDetail,
  BenchJobList,
  Benchmark,
  BenchTask,
  MethodSummary,
} from "../contracts/index.ts";
import { kv, type Print } from "./auth.ts";

type Job = BenchJobList["jobs"][number];

function table(rows: string[][]): string {
  const widths = rows[0]?.map((_, i) => Math.max(...rows.map((r) => (r[i] ?? "").length))) ?? [];
  return rows
    .map((r) =>
      r
        .map((c, i) => c.padEnd(widths[i] ?? 0))
        .join("  ")
        .trimEnd(),
    )
    .join("\n");
}

const pct = (v: number | null | undefined) => (v == null ? "-" : `${v.toFixed(1)}%`);

/**
 * `name=agent[,auth=P][,model=M][,effort=E][,bundle=DIR]`; a bare `oracle` / `empty` names itself.
 */
export function parseMethod(text: string): Record<string, string> {
  if (text === "oracle" || text === "empty") return { name: text, agent: text };
  const [head, ...rest] = text.split(",");
  const i = head?.indexOf("=") ?? -1;
  if (!head || i <= 0) throw new Error(`--method must be name=agent[,key=value...]: ${text}`);
  const m: Record<string, string> = { name: head.slice(0, i), agent: head.slice(i + 1) };
  for (const [k, v] of Object.entries(kv(rest, "--method option"))) {
    if (!["auth", "model", "effort", "bundle"].includes(k))
      throw new Error(`unknown --method key ${k} (auth, model, effort, bundle)`);
    m[k] = k === "bundle" ? resolve(v) : v;
  }
  return m;
}

function summaryLine(s: MethodSummary): string {
  const bad = [
    s.invalid ? `${s.invalid} invalid` : "",
    s.unknown ? `${s.unknown} unknown` : "",
    s.pending ? `${s.pending} pending` : "",
  ]
    .filter(Boolean)
    .join(", ");
  return `${s.method} ${pct(s.meanPct)} (${s.valid}/${s.trials} valid${bad ? `; ${bad}` : ""})`;
}

function formatBenchmarks(bs: Benchmark[]): string {
  if (bs.length === 0) return "no benchmarks; add one with `orbit bench add`";
  return table([["NAME", "ADAPTER", "PATH"], ...bs.map((b) => [b.name, b.adapter, b.path])]);
}

function formatTasks(ts: BenchTask[]): string {
  if (ts.length === 0) return "no tasks";
  const ok = ts.filter((t) => t.supported).length;
  const rows = [["TASK", "OK", "TITLE / REASON"]];
  for (const t of ts)
    rows.push([t.id, t.supported ? "yes" : "no", (t.supported ? t.title : t.reason) ?? ""]);
  return `${table(rows)}\n${ok}/${ts.length} supported`;
}

function formatJobs(jobs: Job[]): string {
  if (jobs.length === 0) return "no bench jobs";
  const rows = [["ID", "STATE", "BENCHMARK", "NAME", "METHODS"]];
  for (const j of jobs)
    rows.push([
      j.id,
      j.state,
      j.spec.benchmark,
      j.spec.name ?? "-",
      j.summary.map(summaryLine).join(" | "),
    ]);
  return table(rows);
}

function formatJob(d: BenchJobDetail): string {
  const { job } = d;
  const lines = [
    `${job.id}  ${job.state}  ${job.spec.benchmark}${job.spec.name ? `  (${job.spec.name})` : ""}`,
    ...d.summary.map((s) => `  ${summaryLine(s)}`),
    "",
  ];
  const rows = [["TASK", "METHOD", "SEED", "STATE", "EVAL", "SCORE", "SOLVE", "VERIFY", "ISSUES"]];
  for (const t of d.trials) {
    const o = t.outcome;
    rows.push([
      t.task,
      t.method,
      String(t.seed),
      t.state,
      o?.evaluation ?? "-",
      o?.score == null ? "-" : `${o.score}/${o.maxScore}`,
      t.solveRunId ?? "-",
      t.verifyRunId ?? "-",
      (o?.issues ?? t.issues).join("; "),
    ]);
  }
  return [...lines, table(rows)].join("\n");
}

function formatCompare(c: BenchCompare): string {
  const keys = c.columns.map((x) => x.key);
  const rows = [["TASK", ...keys]];
  for (const r of c.rows)
    rows.push([
      r.task,
      ...keys.map((k) => `${pct(r.cells[k])} ${r.counts[k] ? `(${r.counts[k]})` : ""}`.trim()),
    ]);
  rows.push(["mean (all valid)", ...keys.map((k) => pct(c.means[k]?.all))]);
  rows.push([`mean (paired, ${c.pairedTasks} tasks)`, ...keys.map((k) => pct(c.means[k]?.paired))]);
  return table(rows);
}

export function registerBench(program: Command, client: () => Promise<OrbitClient>, print: Print) {
  const bench = program
    .command("bench")
    .description("benchmarks: trials of task × method × seed as solve + verify runs");

  bench
    .command("add <name> <path>")
    .description("register a benchmark checkout")
    .requiredOption("--adapter <adapter>", "harbor (task.toml tasks) | asi (ASI-Bench seed31415)")
    .option("--python <python>", "asi: Python with the benchmark's dependencies")
    .option("--instances <dir>", "asi: instances directory")
    .option(
      "-e, --env <KEY=VALUE>",
      "non-secret variable for every run",
      (v, p: string[]) => [...p, v],
      [],
    )
    .option(
      "--pass-env <VAR>",
      "variable copied from the daemon environment at launch (e.g. a judge API key)",
      (v, p: string[]) => [...p, v],
      [],
    )
    .option("--json", "print JSON")
    .action(
      async (
        name: string,
        path: string,
        o: {
          adapter: "harbor" | "asi";
          python?: string;
          instances?: string;
          env: string[];
          passEnv: string[];
          json?: boolean;
        },
      ) => {
        const b = await (await client()).benchmarkPut({
          name,
          adapter: o.adapter,
          path: resolve(path),
          python: o.python,
          instances: o.instances ? resolve(o.instances) : undefined,
          env: kv(o.env, "--env"),
          passEnv: o.passEnv,
        });
        print(o.json, b, () => `saved ${b.name}: ${b.adapter} ${b.path}`);
      },
    );

  bench
    .command("ls")
    .description("list registered benchmarks")
    .option("--json", "print JSON")
    .action(async (o: { json?: boolean }) => {
      const bs = await (await client()).benchmarks();
      print(o.json, bs, () => formatBenchmarks(bs));
    });

  bench
    .command("rm <name>")
    .description("unregister a benchmark (its jobs are kept)")
    .action(async (name: string) => {
      await (await client()).benchmarkRemove(name);
      console.log(`removed ${name}`);
    });

  bench
    .command("tasks <benchmark>")
    .description("list tasks and whether Orbit can run them")
    .option("--json", "print JSON")
    .action(async (name: string, o: { json?: boolean }) => {
      const ts = await (await client()).benchTasks(name);
      print(o.json, ts, () => formatTasks(ts));
    });

  bench
    .command("run <benchmark>")
    .description("start a job: every task × method × seed becomes a trial")
    .option(
      "-m, --method <spec>",
      "name=agent[,auth=P,model=M,effort=E,bundle=DIR]; agent: codex | claude-code | oracle | empty",
      (v, p: string[]) => [...p, v],
      [],
    )
    .option("--methods-file <file>", "JSON array of methods")
    .option(
      "-t, --task <id>",
      "task id (repeatable; default: all supported)",
      (v, p: string[]) => [...p, v],
      [],
    )
    .option("--seeds <n>", "repetitions per task × method", (v) => Number.parseInt(v, 10), 1)
    .option("--timeout <min>", "solve timeout per trial in minutes", Number.parseFloat)
    .option(
      "--option <KEY=VALUE>",
      "adapter option, e.g. promptLevel=b2 for asi",
      (v, p: string[]) => [...p, v],
      [],
    )
    .option("-n, --name <name>", "job name")
    .option("--json", "print JSON")
    .action(
      async (
        name: string,
        o: {
          method: string[];
          methodsFile?: string;
          task: string[];
          seeds: number;
          timeout?: number;
          option: string[];
          name?: string;
          json?: boolean;
        },
      ) => {
        const methods: unknown[] = o.method.map(parseMethod);
        if (o.methodsFile)
          methods.push(...(JSON.parse(readFileSync(o.methodsFile, "utf8")) as unknown[]));
        if (methods.length === 0)
          throw new Error("give at least one --method (e.g. --method oracle)");
        const job = await (await client()).benchSubmit({
          name: o.name,
          benchmark: name,
          tasks: o.task,
          methods: methods as never,
          seeds: o.seeds,
          options: kv(o.option, "--option"),
          timeoutMin: o.timeout,
        });
        print(
          o.json,
          job,
          () =>
            `started ${job.id}: ${job.spec.tasks.length} tasks × ${job.spec.methods.length} methods × ${job.spec.seeds} seeds`,
        );
      },
    );

  bench
    .command("jobs")
    .description("list jobs with per-method results")
    .option("--json", "print JSON")
    .action(async (o: { json?: boolean }) => {
      const jobs = await (await client()).benchJobs();
      print(o.json, jobs, () => formatJobs(jobs));
    });

  bench
    .command("show <job>")
    .description("trials of a job with their outcome and runs")
    .option("--json", "print JSON")
    .action(async (id: string, o: { json?: boolean }) => {
      const d = await (await client()).benchJob(id);
      print(o.json, d, () => formatJob(d));
    });

  bench
    .command("cancel <job>")
    .description("cancel a job's open trials (they end as unknown)")
    .action(async (id: string) => {
      const j = await (await client()).benchCancel(id);
      console.log(`${j.id} ${j.state}`);
    });

  bench
    .command("compare <jobs...>")
    .description("per-task method comparison; paired means use tasks valid for every method")
    .option("--json", "print JSON")
    .action(async (ids: string[], o: { json?: boolean }) => {
      const c = await (await client()).benchCompare(ids);
      print(o.json, c, () => formatCompare(c));
    });
}
