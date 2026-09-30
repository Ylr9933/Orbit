import { type ChildProcess, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { openSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { exec } from "../lib/exec.ts";

export const LABEL_RUN = "orbit.run";
export const LABEL_HOME = "orbit.home";

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
  workdir: string;
  network: boolean;
  /** `uid:gid`, or null for the image default user. */
  user: string | null;
}

export interface ContainerStatus {
  id: string;
  running: boolean;
  exitCode: number;
  oomKilled: boolean;
  gpuIds: string[];
}

/** Build the `docker run` argument list. Pure, for testing. */
export function runArgs(s: ContainerSpec): string[] {
  const args = ["run", "-d", "--init", "--name", s.name];
  for (const [k, v] of Object.entries(s.labels)) args.push("--label", `${k}=${v}`);
  if (s.gpuIds.length > 0 && s.gpuMode === "cdi") {
    for (const id of s.gpuIds) args.push("--device", `nvidia.com/gpu=${id}`);
  } else if (s.gpuIds.length > 0) {
    args.push("--gpus", `"device=${s.gpuIds.join(",")}"`);
  }
  args.push("--cpus", String(s.cpus), "--memory", `${Math.ceil(s.memGB * 1024)}m`);
  args.push("--shm-size", `${Math.max(1, Math.min(16, Math.floor(s.memGB / 2)))}g`);
  for (const m of s.mounts) {
    args.push(
      "--mount",
      `type=bind,source=${m.source},target=${m.target}${m.mode === "ro" ? ",readonly" : ""}`,
    );
  }
  for (const [k, v] of Object.entries(s.env)) args.push("-e", `${k}=${v}`);
  if (!s.network) args.push("--network", "none");
  if (s.user) args.push("--user", s.user);
  args.push("-w", s.workdir, s.image, ...s.command);
  return args;
}

async function docker(args: string[], timeoutMs = 60_000) {
  return exec("docker", args, { timeoutMs });
}

export function dockerfileTag(dockerfile: string, project: string): string {
  const hash = createHash("sha256").update(readFileSync(dockerfile)).digest("hex").slice(0, 12);
  const name =
    project
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^[-.]+/, "") || "project";
  return `orbit-local/${name}:${hash}`;
}

export async function imageExists(image: string): Promise<boolean> {
  return (await docker(["image", "inspect", "--format", "{{.Id}}", image])).code === 0;
}

/** `docker build`, streaming output to `logFile`. Resolves with the exit code. */
export function buildImage(dockerfile: string, context: string, tag: string, logFile: string) {
  const fd = openSync(logFile, "a");
  return new Promise<number>((resolve) => {
    const p = spawn("docker", ["build", "-f", dockerfile, "-t", tag, context], {
      stdio: ["ignore", fd, fd],
    });
    p.on("error", () => resolve(127));
    p.on("close", (code) => resolve(code ?? 1));
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

export async function inspectContainer(idOrName: string): Promise<ContainerStatus | null> {
  const r = await docker(["inspect", idOrName]);
  if (r.code !== 0) return null;
  const [c] = JSON.parse(r.stdout) as {
    Id: string;
    State: { Running: boolean; ExitCode: number; OOMKilled: boolean };
    HostConfig: { DeviceRequests: { DeviceIDs: string[] | null }[] | null };
  }[];
  if (!c) return null;
  return {
    id: c.Id,
    running: c.State.Running,
    exitCode: c.State.ExitCode,
    oomKilled: c.State.OOMKilled,
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

/** Follow container logs (stdout + stderr) into `logFile` from the beginning, until EOF. */
export function followLogs(id: string, logFile: string, append: boolean): ChildProcess {
  const fd = openSync(logFile, append ? "a" : "w");
  return spawn("docker", ["logs", "-f", id], { stdio: ["ignore", fd, fd] });
}

export async function stopContainer(id: string, graceSec = 10): Promise<void> {
  await docker(["stop", "-t", String(graceSec), id], (graceSec + 30) * 1000);
}

/** Remove the container; resolves true when it is gone. */
export async function removeContainer(id: string): Promise<boolean> {
  const r = await docker(["rm", "-f", id]);
  if (r.code === 0) return true;
  return (await inspectContainer(id)) === null;
}
