import { type ChildProcess, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  closeSync,
  createWriteStream,
  type Dirent,
  mkdirSync,
  openSync,
  readdirSync,
  readFileSync,
  statSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";
import { exec } from "../lib/exec.ts";
import type { Redactor } from "../lib/redact.ts";

export const LABEL_RUN = "orbit.run";
export const LABEL_HOME = "orbit.home";
/** Containers started by a process run (through the docker shim). */
export const LABEL_PARENT = "orbit.parent";

/** How GPUs are passed to containers: CDI devices (preferred) or the legacy `--gpus` flag. */
export type GpuMode = "cdi" | "gpus";

const CDI_DIRS = ["/etc/cdi", "/var/run/cdi"];

/** Use CDI when an NVIDIA CDI spec is installed; `--gpus` is broken on some Docker versions. */
export function detectGpuMode(dirs = CDI_DIRS): GpuMode {
  for (const d of dirs) {
    let names: string[] = [];
    try {
      names = readdirSync(d);
    } catch {
      continue;
    }
    for (const n of names) {
      if (!/\.(ya?ml|json)$/.test(n)) continue;
      try {
        if (readFileSync(join(d, n), "utf8").includes("nvidia.com/gpu")) return "cdi";
      } catch {}
    }
  }
  return "gpus";
}

export interface ContainerSpec {
  name: string;
  image: string;
  command: string[];
  labels: Record<string, string>;
  gpuIds: string[];
  gpuMode: GpuMode;
  cpus: number;
  memGB: number;
  mounts: { source: string; target: string; mode: "ro" | "rw" }[];
  env: Record<string, string>;
  /** Null keeps the image's WORKDIR. */
  workdir: string | null;
  network: "bridge" | "host" | "none";
  /** `uid:gid`, or null for the image default user. */
  user: string | null;
  /** Private `KEY=VALUE` file for secret variables, so they never appear in argv. */
  envFile?: string;
}

export interface ContainerStatus {
  id: string;
  running: boolean;
  exitCode: number;
  oomKilled: boolean;
  gpuIds: string[];
  /** Host pid of the container's init process (0 when stopped). */
  pid: number;
}

/** Build the `docker run` argument list. Pure, for testing. */
export function runArgs(s: ContainerSpec): string[] {
  const args = ["run", "-d", "--init", "--name", s.name];
  for (const [k, v] of Object.entries(s.labels)) args.push("--label", `${k}=${v}`);
  if (s.gpuIds.length > 0 && s.gpuMode === "cdi") {
    for (const id of s.gpuIds) args.push("--device", `nvidia.com/gpu=${id}`);
  } else if (s.gpuIds.length > 0) {
    args.push("--gpus", `"device=${s.gpuIds.join(",")}"`);
  } else {
    // Hosts whose default runtime is nvidia would otherwise expose every GPU to CUDA images.
    args.push("-e", "NVIDIA_VISIBLE_DEVICES=void");
  }
  args.push("--cpus", String(s.cpus), "--memory", `${Math.ceil(s.memGB * 1024)}m`);
  args.push("--shm-size", `${Math.max(1, Math.min(16, Math.floor(s.memGB / 2)))}g`);
  for (const m of s.mounts) {
    args.push(
      "--mount",
      [
        "type=bind",
        csvField(`source=${m.source}`),
        csvField(`target=${m.target}`),
        ...(m.mode === "ro" ? ["readonly"] : []),
      ].join(","),
    );
  }
  for (const [k, v] of Object.entries(s.env)) args.push("-e", `${k}=${v}`);
  if (s.envFile) args.push("--env-file", s.envFile);
  if (s.network !== "bridge") args.push("--network", s.network);
  if (s.user) args.push("--user", s.user);
  if (s.workdir) args.push("-w", s.workdir);
  args.push(s.image, ...s.command);
  return args;
}

/** `--mount` is parsed as CSV: quote a field holding a comma or a quote. */
const csvField = (f: string) => (/[",]/.test(f) ? `"${f.replace(/"/g, '""')}"` : f);

async function docker(args: string[], timeoutMs = 60_000) {
  return exec("docker", args, { timeoutMs });
}

/**
 * Image tag for a Dockerfile build: the hash covers the Dockerfile and the build context's file list
 * (path, size, mtime), so changed context files rebuild the image.
 */
export function dockerfileTag(dockerfile: string, context: string, project: string): string {
  const h = createHash("sha256").update(readFileSync(dockerfile));
  for (const line of contextListing(context)) h.update(`${line}\n`);
  const hash = h.digest("hex").slice(0, 12);
  const name =
    project
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^[-.]+/, "") || "project";
  return `orbit-local/${name}:${hash}`;
}

const SKIP_DIRS = new Set([".git", "node_modules", "__pycache__"]);

function contextListing(root: string, limit = 50_000): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    let entries: Dirent[] = [];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const e of entries) {
      if (out.length >= limit) return;
      const p = join(dir, e.name);
      if (e.isDirectory()) {
        if (!SKIP_DIRS.has(e.name)) walk(p);
        continue;
      }
      try {
        const st = statSync(p);
        out.push(`${relative(root, p)} ${st.size} ${Math.floor(st.mtimeMs)}`);
      } catch {}
    }
  };
  walk(root);
  return out;
}

export async function imageExists(image: string): Promise<boolean> {
  return (await docker(["image", "inspect", "--format", "{{.Id}}", image])).code === 0;
}

/** The image's configured `PATH`, or null when it sets none. */
export async function imagePath(image: string): Promise<string | null> {
  const r = await docker(["image", "inspect", "--format", "{{json .Config.Env}}", image]);
  if (r.code !== 0) return null;
  const env = (JSON.parse(r.stdout || "null") as string[] | null) ?? [];
  return env.find((e) => e.startsWith("PATH="))?.slice(5) ?? null;
}

/** `docker run --env-file` content. Values cannot span lines in that format. */
export function envFileText(env: Record<string, string>): string {
  return Object.entries(env)
    .map(([k, v]) => {
      if (/[\r\n]/.test(v)) throw new Error(`environment value of ${k} must be a single line`);
      return `${k}=${v}\n`;
    })
    .join("");
}

/** `docker build`, streaming output to `logFile`. Resolves with the exit code. */
export function buildImage(
  dockerfile: string,
  context: string,
  tag: string,
  logFile: string,
  opts: { hostNetwork?: boolean } = {},
) {
  const net = opts.hostNetwork ? ["--network", "host"] : [];
  return spawnToLog(["build", ...net, "-f", dockerfile, "-t", tag, context], logFile);
}

/** `docker pull`, streaming progress to `logFile`. Resolves with the exit code. */
export function pullImage(image: string, logFile: string): Promise<number> {
  return spawnToLog(["pull", image], logFile);
}

function spawnToLog(args: string[], logFile: string): Promise<number> {
  const fd = openSync(logFile, "a");
  return new Promise<number>((resolve) => {
    try {
      const p = spawn("docker", args, { stdio: ["ignore", fd, fd] });
      p.on("error", () => resolve(127));
      p.on("close", (code) => resolve(code ?? 1));
    } finally {
      closeSync(fd);
    }
  });
}

export async function startContainer(spec: ContainerSpec): Promise<string> {
  const r = await docker(runArgs(spec), 300_000);
  if (r.code !== 0) {
    const line = r.stderr.split("\n").find((l) => l.trim()) ?? `exit ${r.code}`;
    throw new Error(`docker run failed: ${line.replace(/^docker: /, "").trim()}`);
  }
  return r.stdout.trim();
}

/** The container's status, null when it does not exist; throws when docker itself fails. */
export async function inspectContainer(idOrName: string): Promise<ContainerStatus | null> {
  const r = await docker(["inspect", "--type", "container", idOrName]);
  if (r.code !== 0) {
    if (/no such (object|container)/i.test(r.stderr)) return null;
    throw new Error(`docker inspect failed: ${r.stderr.trim().split("\n")[0] ?? `exit ${r.code}`}`);
  }
  const [c] = JSON.parse(r.stdout) as {
    Id: string;
    State: { Running: boolean; ExitCode: number; OOMKilled: boolean; Pid: number };
    HostConfig: { DeviceRequests: { DeviceIDs: string[] | null }[] | null };
  }[];
  if (!c) return null;
  return {
    id: c.Id,
    running: c.State.Running,
    exitCode: c.State.ExitCode,
    oomKilled: c.State.OOMKilled,
    pid: c.State.Pid ?? 0,
    // CDI ids look like `nvidia.com/gpu=<UUID>`; `--gpus` ids are bare UUIDs.
    gpuIds: (c.HostConfig.DeviceRequests ?? [])
      .flatMap((d) => d.DeviceIDs ?? [])
      .map((id) => id.replace(/^nvidia\.com\/gpu=/, "")),
  };
}

/** Resolves with the container exit code once it stops (or -1 if docker wait fails). */
export async function waitContainer(id: string): Promise<number> {
  const r = await exec("docker", ["wait", id], { timeoutMs: 0 });
  const code = Number.parseInt(r.stdout.trim(), 10);
  return r.code === 0 && Number.isFinite(code) ? code : -1;
}

export interface LogFollower {
  proc: ChildProcess;
  /** Resolves once the logs reached EOF and are written. */
  done: Promise<void>;
}

/**
 * Append container logs (stdout + stderr) to `logFile` from the beginning, until EOF. With a
 * redactor, known secrets are replaced before anything is written (one filter per stream, so a
 * secret split across chunks of one stream is still caught when the other interleaves).
 */
export function followLogs(id: string, logFile: string, redactor?: Redactor): LogFollower {
  if (!redactor || redactor.empty) {
    const fd = openSync(logFile, "a");
    try {
      const proc = spawn("docker", ["logs", "-f", id], { stdio: ["ignore", fd, fd] });
      return { proc, done: new Promise((r) => proc.once("close", () => r())) };
    } finally {
      closeSync(fd);
    }
  }
  const proc = spawn("docker", ["logs", "-f", id], { stdio: ["ignore", "pipe", "pipe"] });
  const out = createWriteStream(logFile, { flags: "a" });
  const filters = [proc.stdout, proc.stderr].map((src) => {
    const f = redactor.stream();
    src?.pipe(f);
    f.on("data", (chunk) => out.write(chunk));
    return new Promise<void>((r) => f.once("end", () => r()));
  });
  const done = Promise.all(filters).then(() => new Promise<void>((r) => out.end(() => r())));
  return { proc, done };
}

export async function stopContainer(id: string, graceSec = 10): Promise<void> {
  await docker(["stop", "-t", String(graceSec), id], (graceSec + 30) * 1000);
}

/** Remove the container; resolves true when it is gone. */
export async function removeContainer(id: string): Promise<boolean> {
  const r = await docker(["rm", "-f", id]);
  if (r.code === 0) return true;
  return (await inspectContainer(id).catch(() => undefined)) === null;
}

/** Copy `src` out of a container to `dest` on the host; returns an error line or null. */
export async function copyFromContainer(
  id: string,
  src: string,
  dest: string,
): Promise<string | null> {
  mkdirSync(dirname(dest), { recursive: true });
  const r = await docker(["cp", `${id}:${src}`, dest], 600_000);
  return r.code === 0 ? null : (r.stderr.trim().split("\n")[0] ?? `exit ${r.code}`);
}

/** Ids of containers (running or not) with this label. */
export async function containersWithLabel(label: string, value: string): Promise<string[] | null> {
  const r = await docker(["ps", "-aq", "--no-trunc", "--filter", `label=${label}=${value}`]);
  if (r.code !== 0) return null;
  return r.stdout.split("\n").filter(Boolean);
}
