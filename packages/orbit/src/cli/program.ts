import { spawn } from "node:child_process";
import { openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { Command, Option } from "commander";
import { type OrbitClient, tryConnect } from "../client/index.ts";
import { ensureHome, type OrbitPaths, orbitPaths } from "../config/paths.ts";
import { isTerminal, type Run, type RunSpecInput } from "../contracts/index.ts";
import { exec } from "../lib/exec.ts";
import { VERSION } from "../lib/version.ts";
import { detectAgent } from "./agent.ts";
import { kv, registerAuth, registerNotify } from "./auth.ts";
import { registerBench } from "./bench.ts";
import { parseDataset, registerCluster } from "./cluster.ts";
import { confirmTyped } from "./confirm.ts";
import { formatDoctor, formatLedger, formatRun, formatRuns } from "./format.ts";

export interface ProgramDeps {
  /** Run the daemon in the foreground; provided by the composition root (src/bin.ts). */
  runDaemon(paths: OrbitPaths, port?: number): Promise<void>;
}

/** Connect to the local daemon, starting a detached one when none is running. */
async function connect(p: OrbitPaths): Promise<OrbitClient> {
  const existing = await tryConnect(p);
  if (existing) return existing;
  ensureHome(p);
  const log = openSync(p.daemonLog, "a");
  const entry = process.argv[1];
  if (!entry) throw new Error("cannot locate the orbit entrypoint to start the daemon");
  const child = spawn(process.execPath, [...process.execArgv, entry, "daemon"], {
    detached: true,
    stdio: ["ignore", log, log],
    env: process.env,
  });
  child.unref();
  for (let i = 0; i < 100; i++) {
    await new Promise((r) => setTimeout(r, 100));
    const client = await tryConnect(p);
    if (client) return client;
  }
  throw new Error(`daemon did not start; see ${p.daemonLog}`);
}

const collect = (v: string, prev: string[]) => [...prev, v];
const num = (v: string) => {
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`not a number: ${v}`);
  return n;
};

interface RunOpts {
  name?: string;
  group?: string;
  project?: string | false;
  image?: string;
  dockerfile?: string;
  gpus: number;
  gpuMem?: number;
  gpuIds?: string;
  cpus: number;
  mem: number;
  mount: string[];
  dataset: string[];
  node?: string;
  env: string[];
  passEnv: string[];
  network: boolean;
  hostNetwork?: boolean;
  auth?: string;
  snapshot: boolean;
  root?: boolean;
  timeout?: number;
  tag: string[];
  json?: boolean;
  wait?: boolean;
}

function addRunOptions(cmd: Command): Command {
  return cmd
    .option("-n, --name <name>", "run name")
    .option("-g, --group <group>", "group runs (sweeps, ablations) for comparison")
    .option("--project <dir>", "git repo to snapshot into /workspace (default: current repo)")
    .option("--no-project", "do not mount or snapshot any project")
    .option("--image <image>", "docker image")
    .option("--dockerfile <path>", "build the image from this Dockerfile (context: its directory)")
    .option("--gpus <n>", "number of GPUs", num, 0)
    .option("--gpu-mem <GB>", "minimum memory per GPU", num)
    .option("--gpu-ids <ids>", "pin GPUs (comma-separated UUIDs or indexes)")
    .option("--cpus <n>", "CPU limit", num, 4)
    .option("--mem <GB>", "memory limit in GB", num, 16)
    .option("-m, --mount <src:dst[:rw]>", "bind mount (read-only unless :rw)", collect, [])
    .option(
      "-d, --dataset <name[:dst[:rw]]>",
      "mount a registered dataset (orbit data ls; default /data/<name>, read-only)",
      collect,
      [],
    )
    .option("--node <name>", "run on this node (default: any node that can run it)")
    .option(
      "-e, --env <KEY=VALUE>",
      "environment variable (stored with the run: no secrets)",
      collect,
      [],
    )
    .option(
      "--pass-env <VAR>",
      "pass this variable from the daemon's environment (for secrets; the value is not stored)",
      collect,
      [],
    )
    .option("--no-network", "disable networking")
    .option("--host-network", "share the host network (e.g. to reach a proxy on 127.0.0.1)")
    .option(
      "--auth <profile>",
      "mount the Agent CLI with this credential profile (orbit auth list)",
    )
    .option("--no-snapshot", "mount the project read-only instead of snapshotting it")
    .option("--root", "run as root instead of your user")
    .option("--timeout <min>", "stop the run after this many minutes", num)
    .option("-t, --tag <KEY=VALUE>", "tag", collect, [])
    .option("-w, --wait", "wait for completion and exit with the run's status")
    .option("--json", "print JSON");
}

async function gitRoot(dir: string): Promise<string | null> {
  const r = await exec("git", ["-C", dir, "rev-parse", "--show-toplevel"]);
  return r.code === 0 ? r.stdout.trim() : null;
}

async function buildSpec(
  o: RunOpts,
  command: string[],
  params: Record<string, string> = {},
): Promise<RunSpecInput> {
  if (!o.image && !o.dockerfile) throw new Error("--image or --dockerfile is required");
  let project: string | undefined;
  if (typeof o.project === "string") project = resolve(o.project);
  else if (o.project !== false && (await gitRoot(process.cwd()))) project = process.cwd();
  const mounts = o.mount.map((m) => {
    const parts = m.split(":");
    const [source, target, mode] = parts;
    if (!source || !target || parts.length > 3 || (mode && mode !== "rw" && mode !== "ro")) {
      throw new Error(`--mount must be SRC:DST[:rw]: ${m}`);
    }
    return { source: resolve(source), target, mode: (mode as "rw" | "ro" | undefined) ?? "ro" };
  });
  const datasets = o.dataset.map(parseDataset);
  const gpuIds = o.gpuIds?.split(",").filter(Boolean);
  return {
    name: o.name,
    group: o.group,
    project,
    image: o.image,
    dockerfile: o.dockerfile ? resolve(o.dockerfile) : undefined,
    command,
    resources: {
      // Pinned GPUs without a count: one per pinned id.
      gpus: o.gpus || (gpuIds?.length ?? 0),
      gpuMemGB: o.gpuMem,
      gpuIds,
      cpus: o.cpus,
      memGB: o.mem,
      node: o.node,
    },
    mounts: [...mounts, ...datasets],
    env: kv(o.env, "--env"),
    passEnv: o.passEnv,
    network: o.network,
    hostNetwork: Boolean(o.hostNetwork),
    auth: o.auth,
    snapshot: o.snapshot,
    root: o.root ?? false,
    timeoutMin: o.timeout,
    tags: kv(o.tag, "--tag"),
    params,
    agent: detectAgent(),
  };
}

/** Wait for all runs to finish; exit code 1 if any did not succeed. */
async function waitAll(
  client: OrbitClient,
  ids: string[],
  json: boolean,
  single = false,
): Promise<void> {
  const done: Run[] = [];
  for (const id of ids) {
    let r = await client.get(id);
    while (!isTerminal(r.state) || r.cleanup === "pending") r = await client.wait(id, 60);
    done.push(r);
    if (!json) console.log(`${r.id}  ${r.state}${r.reason ? ` (${r.reason})` : ""}`);
  }
  if (json) console.log(JSON.stringify(single ? done[0] : done, null, 2));
  if (done.some((r) => r.state !== "succeeded")) process.exitCode = 1;
}

/** Expand `a=1,2 b=x,y` into the cartesian product of parameter assignments. */
export function expandGrid(params: string[]): Record<string, string>[] {
  if (params.length === 0) throw new Error("give at least one --param KEY=V1,V2,...");
  let grid: Record<string, string>[] = [{}];
  for (const p of params) {
    const i = p.indexOf("=");
    if (i <= 0) throw new Error(`--param must be KEY=V1,V2,...: ${p}`);
    const key = p.slice(0, i);
    if (!/^\w+$/.test(key))
      throw new Error(`--param key must be letters, digits or _ (used as {${key}}): ${key}`);
    const values = p
      .slice(i + 1)
      .split(",")
      .filter((v) => v !== "");
    if (values.length === 0) throw new Error(`--param ${key} has no values`);
    grid = grid.flatMap((g) => values.map((v) => ({ ...g, [key]: v })));
  }
  return grid;
}

export function substitute(command: string[], params: Record<string, string>): string[] {
  return command.map((a) => a.replace(/\{(\w+)\}/g, (m, k: string) => params[k] ?? m));
}

export function createProgram(deps: ProgramDeps, paths: OrbitPaths = orbitPaths()): Command {
  const program = new Command()
    .name("orbit")
    .description("Run, isolate and record experiments for Codex / Claude Code")
    .version(VERSION)
    .enablePositionalOptions();
  const client = () => connect(paths);
  const print = (json: boolean | undefined, value: unknown, text: () => string) =>
    console.log(json ? JSON.stringify(value, null, 2) : text());

  program
    .command("daemon")
    .description("run the node daemon in the foreground (the CLI starts it automatically)")
    .option("-p, --port <port>", "listen port on 127.0.0.1", num)
    .option("--stop", "stop the running daemon (runs keep going and are reattached on restart)")
    .action(async (opts: { port?: number; stop?: boolean }) => {
      if (!opts.stop) return deps.runDaemon(paths, opts.port);
      // The pid the daemon reports itself: a stale daemon.json may name a reused pid.
      const live = await tryConnect(paths);
      if (!live) return console.log("daemon is not running");
      const { pid } = await live.health();
      process.kill(pid, "SIGTERM");
      console.log(`stopped daemon pid ${pid}`);
    });

  addRunOptions(
    program
      .command("run")
      .description("run a command in a container: orbit run [options] -- <command...>")
      .argument("<command...>")
      .passThroughOptions(),
  ).action(async (command: string[], o: RunOpts) => {
    const c = await client();
    const run = await c.submit(await buildSpec(o, command));
    if (o.wait) return waitAll(c, [run.id], Boolean(o.json), true);
    print(o.json, run, () => `${run.id}  ${run.state}${run.reason ? ` (${run.reason})` : ""}`);
  });

  addRunOptions(
    program
      .command("sweep")
      .description("submit one run per parameter combination; {key} in the command is substituted")
      .option("-p, --param <KEY=V1,V2,...>", "parameter values (repeatable, required)", collect, [])
      .argument("<command...>")
      .passThroughOptions(),
  ).action(async (command: string[], o: RunOpts & { param: string[] }) => {
    const grid = expandGrid(o.param);
    const unused = Object.keys(grid[0] ?? {}).filter(
      (k) => !command.some((a) => a.includes(`{${k}}`)),
    );
    if (unused.length)
      throw new Error(`--param ${unused.join(", ")} not used as {key} in the command`);
    const c = await client();
    const group =
      o.group ?? o.name ?? `sweep-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;
    const runs: Run[] = [];
    for (const params of grid) {
      const suffix = Object.entries(params)
        .map(([k, v]) => `${k}=${v}`)
        .join(",");
      const spec = await buildSpec(
        { ...o, group, name: `${o.name ?? group}[${suffix}]` },
        substitute(command, params),
        params,
      );
      runs.push(await c.submit(spec));
    }
    if (o.wait)
      return waitAll(
        c,
        runs.map((r) => r.id),
        Boolean(o.json),
      );
    print(o.json, runs, () => `group ${group}\n${formatRuns(runs)}`);
  });

  program
    .command("ps")
    .description("list runs (active by default)")
    .option("-a, --all", "include finished runs")
    .option("-g, --group <group>", "only this group")
    .option("-l, --limit <n>", "max runs", num, 50)
    .option("--json", "print JSON")
    .action(async (o: { all?: boolean; group?: string; limit: number; json?: boolean }) => {
      const states = o.all || o.group ? undefined : (["queued", "starting", "running"] as const);
      const runs = await (await client()).list({
        states: states ? [...states] : undefined,
        group: o.group,
        limit: o.limit,
      });
      print(o.json, runs, () => formatRuns(runs));
    });

  program
    .command("show")
    .description("show a run with its latest metrics")
    .argument("<id>")
    .option("--json", "print JSON")
    .action(async (id: string, o: { json?: boolean }) => {
      const c = await client();
      const [run, metrics] = await Promise.all([c.get(id), c.metrics(id)]);
      print(o.json, { run, metrics: metrics.summary }, () => formatRun(run, metrics.summary));
    });

  program
    .command("logs")
    .description("print run logs")
    .argument("<id>")
    .option("-f, --follow", "keep printing until the run ends")
    .option("--tail <bytes>", "start this many bytes before the end", num)
    .action(async (id: string, o: { follow?: boolean; tail?: number }) => {
      const c = await client();
      let offset = o.tail ? -o.tail : 0;
      for (;;) {
        const chunk = await c.logs(id, offset);
        if (chunk.text) process.stdout.write(chunk.text);
        offset = chunk.next;
        if (chunk.next < chunk.size) continue;
        if (!o.follow || chunk.eof) break;
        const run = await c.get(id);
        if (isTerminal(run.state) && run.cleanup !== "pending") {
          const last = await c.logs(id, offset);
          process.stdout.write(last.text);
          if (last.next >= last.size) break;
          offset = last.next;
          continue;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    });

  program
    .command("wait")
    .description("wait for runs to finish; exits 1 if any did not succeed")
    .argument("[ids...]")
    .option("-g, --group <group>", "wait for every run in this group")
    .option("--json", "print JSON")
    .action(async (ids: string[], o: { group?: string; json?: boolean }) => {
      const c = await client();
      if (o.group) ids = [...ids, ...(await c.list({ group: o.group })).map((r) => r.id)];
      if (ids.length === 0) throw new Error("give run ids or --group");
      await waitAll(c, [...new Set(ids)], Boolean(o.json));
    });

  program
    .command("cancel")
    .description("cancel queued or running runs")
    .argument("<ids...>")
    .action(async (ids: string[]) => {
      const c = await client();
      for (const id of ids) {
        const r = await c.cancel(id);
        console.log(`${r.id}  ${r.state}`);
      }
    });

  program
    .command("rm")
    .description(
      "permanently delete finished runs (records, logs, outputs); asks you to type the id or group",
    )
    .argument("[ids...]")
    .option("-g, --group <group>", "every run of this group")
    .option("-y, --yes", "skip the typed confirmation (required without a terminal)")
    .option("--json", "print JSON")
    .action(async (ids: string[], o: { group?: string; yes?: boolean; json?: boolean }) => {
      const c = await client();
      const targets = [...ids];
      if (o.group)
        targets.push(...(await c.list({ group: o.group, limit: 10_000 })).map((r) => r.id));
      if (targets.length === 0) throw new Error("give run ids or --group");
      const expected =
        o.group && ids.length === 0
          ? o.group
          : targets.length === 1
            ? (targets[0] as string)
            : `delete ${targets.length} runs`;
      await confirmTyped(
        `delete ${targets.length} run(s)${o.group ? ` of group ${o.group}` : ""}`,
        expected,
        o.yes,
      );
      const r = await c.deleteRuns(targets);
      print(o.json, r, () =>
        [
          `deleted ${r.deleted.length} run(s)`,
          ...r.leftovers.map((d) => `could not remove all files of ${d}`),
        ].join("\n"),
      );
    });

  program
    .command("note")
    .description(
      "attach an analysis note to a run (text, or - for stdin); replaces the previous note",
    )
    .argument("<id>")
    .argument("<text>")
    .action(async (id: string, text: string) => {
      const note = text === "-" ? readFileSync(0, "utf8") : text;
      await (await client()).note(id, note);
      console.log(`noted ${id}`);
    });

  program
    .command("resources")
    .description("show GPUs, CPU, memory, leases and the queue on this node and its workers")
    .option("--json", "print JSON")
    .action(async (o: { json?: boolean }) => {
      const l = await (await client()).ledger();
      print(o.json, l, () => formatLedger(l));
    });

  program
    .command("doctor")
    .description("check docker, nvidia-smi, git, node and the Agent CLIs")
    .option("--json", "print JSON")
    .action(async (o: { json?: boolean }) => {
      const r = await (await client()).doctor();
      print(o.json, r, () => formatDoctor(r));
      if (!r.ok) process.exitCode = 1;
    });

  registerAuth(program, client, print);
  registerNotify(program, client, print);
  registerBench(program, client, print);
  registerCluster(program, client, print);

  program
    .command("web [id]")
    .description("print the local Web UI login URL (optionally deep-linked to a run)")
    .addOption(new Option("--open", "open it in the default browser"))
    .action(async (id: string | undefined, o: { open?: boolean }) => {
      const c = await client();
      const next = id ? `&next=${encodeURIComponent(`/runs/${id}`)}` : "";
      const url = `${c.info.url}/login?token=${c.info.token}${next}`;
      console.log(url);
      if (o.open)
        spawn("xdg-open", [url], { detached: true, stdio: "ignore" })
          .on("error", () => {})
          .unref();
    });

  return program;
}
