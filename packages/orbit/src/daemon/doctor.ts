import { statfs } from "node:fs/promises";
import { type OrbitPaths, onSystemDisk } from "../config/paths.ts";
import type { DoctorCheck, DoctorReport, Harness } from "../contracts/index.ts";
import { hostCli } from "../harness/index.ts";
import { exec } from "../lib/exec.ts";

async function tool(name: string, cmd: string, args: string[]): Promise<DoctorCheck> {
  const r = await exec(cmd, args);
  const out = (r.code === 0 ? r.stdout : r.stderr).trim().split("\n")[0] ?? "";
  return { name, ok: r.code === 0, detail: out || `exit ${r.code}`, warn: false };
}

/** Agent CLIs mounted into containers for `--auth` runs. Missing ones only matter for those runs. */
async function harness(h: Harness): Promise<DoctorCheck> {
  const cli = await hostCli(h);
  return {
    name: h,
    ok: true,
    warn: false,
    detail: cli
      ? `${cli.version} (${cli.hostBin})`
      : "not found; --auth runs with this harness fail",
  };
}

const GIB = 1024 ** 3;
/** Free space below which a disk is reported: 10% of it, but at least 50 GB and at most 500 GB. */
const lowFreeGB = (totalGB: number) => Math.max(50, Math.min(totalGB * 0.1, 500));

/** Free space of a directory's disk, and whether it is low or the system disk. */
async function disk(name: string, dir: string, hint: string): Promise<DoctorCheck> {
  const fs = await statfs(dir).catch(() => null);
  if (!fs) return { name, ok: false, warn: false, detail: `${dir} not found` };
  const free = (fs.bavail * fs.bsize) / GIB;
  const total = (fs.blocks * fs.bsize) / GIB;
  const notes: string[] = [];
  if (onSystemDisk(dir)) notes.push(`on the system disk; ${hint}`);
  if (free < lowFreeGB(total)) notes.push("low on space");
  return {
    name,
    ok: true,
    warn: notes.length > 0,
    detail: `${dir}  ${Math.round(free)}/${Math.round(total)} GB free${notes.length ? ` (${notes.join("; ")})` : ""}`,
  };
}

/** Where Docker keeps images and container layers (often the system disk). */
async function dockerRoot(): Promise<DoctorCheck | null> {
  const r = await exec("docker", ["info", "--format", "{{.DockerRootDir}}"]);
  const dir = r.stdout.trim();
  if (r.code !== 0 || !dir.startsWith("/")) return null;
  return disk("docker data", dir, "large images fill it (docker `data-root`)");
}

export async function runDoctor(paths: OrbitPaths): Promise<DoctorReport> {
  const checks = await Promise.all([
    Promise.resolve<DoctorCheck>({ name: "node", ok: true, warn: false, detail: process.version }),
    disk(
      "orbit data",
      paths.data,
      `move runs to a large disk with \`orbit config data <dir>\` (now: ${paths.dataSource})`,
    ),
    tool("git", "git", ["--version"]),
    tool("docker", "docker", ["version", "--format", "server {{.Server.Version}}"]),
    tool("nvidia-smi", "nvidia-smi", ["--query-gpu=driver_version", "--format=csv,noheader"]),
    harness("codex"),
    harness("claude-code"),
    dockerRoot(),
  ]);
  const all = checks.filter((c): c is DoctorCheck => c !== null);
  return { ok: all.every((c) => c.ok), checks: all };
}
