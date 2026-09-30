import type { DoctorCheck, DoctorReport } from "../contracts/index.ts";
import { exec } from "../lib/exec.ts";

async function tool(name: string, cmd: string, args: string[]): Promise<DoctorCheck> {
  const r = await exec(cmd, args);
  const out = (r.code === 0 ? r.stdout : r.stderr).trim().split("\n")[0] ?? "";
  return { name, ok: r.code === 0, detail: out || `exit ${r.code}` };
}

export async function runDoctor(): Promise<DoctorReport> {
  const checks = await Promise.all([
    Promise.resolve<DoctorCheck>({ name: "node", ok: true, detail: process.version }),
    tool("git", "git", ["--version"]),
    tool("docker", "docker", ["version", "--format", "server {{.Server.Version}}"]),
    tool("nvidia-smi", "nvidia-smi", ["--query-gpu=driver_version", "--format=csv,noheader"]),
  ]);
  return { ok: checks.every((c) => c.ok), checks };
}
