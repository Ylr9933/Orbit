import type { DoctorReport, NodeResources } from "../contracts/index.ts";

export function formatResources(r: NodeResources): string {
  const lines = [`node ${r.node}`];
  if (r.gpuError) lines.push(`gpus: unavailable (${r.gpuError})`);
  for (const g of r.gpus) {
    const state = g.available ? "free" : "busy";
    const util = g.utilPct === null ? "-" : `${g.utilPct}%`;
    lines.push(
      `  gpu${g.index} ${state.padEnd(4)} ${g.name}  ${g.memUsedMiB}/${g.memTotalMiB} MiB  util ${util}  ${g.uuid}`,
    );
  }
  const free = r.gpus.filter((g) => g.available).length;
  lines.push(`gpus: ${free}/${r.gpus.length} free`);
  lines.push(`cpu: ${r.cpu.count} cores, load ${r.cpu.load1}`);
  lines.push(`memory: ${r.memory.availableGB}/${r.memory.totalGB} GB available`);
  lines.push(`disk (${r.disk.path}): ${r.disk.freeGB}/${r.disk.totalGB} GB free`);
  return lines.join("\n");
}

export function formatDoctor(r: DoctorReport): string {
  return r.checks
    .map((c) => `${c.ok ? "ok  " : "FAIL"} ${c.name.padEnd(11)} ${c.detail}`)
    .join("\n");
}

export const printResources = (r: NodeResources) => console.log(formatResources(r));
export const printDoctor = (r: DoctorReport) => console.log(formatDoctor(r));
