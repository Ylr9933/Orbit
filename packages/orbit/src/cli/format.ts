import type { DoctorReport, Lease, Ledger, NodeResources, Run } from "../contracts/index.ts";

export function duration(ms: number): string {
  if (ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h${String(m % 60).padStart(2, "0")}m`;
}

export function runDuration(r: Run, now = Date.now()): string {
  if (!r.startedAt) return "-";
  const end = r.endedAt ? Date.parse(r.endedAt) : now;
  return duration(end - Date.parse(r.startedAt));
}

function table(rows: string[][]): string {
  const widths = rows[0]?.map((_, i) => Math.max(...rows.map((r) => (r[i] ?? "").length))) ?? [];
  return rows
    .map((r) => r.map((c, i) => (i === r.length - 1 ? c : c.padEnd(widths[i] ?? 0))).join("  "))
    .join("\n");
}

export function formatRuns(runs: Run[]): string {
  if (runs.length === 0) return "no runs";
  const multi = new Set(runs.map((r) => r.node)).size > 1 || runs.some((r) => r.remote);
  const rows = [["ID", "STATE", "GROUP", "NAME", "GPUS", "TIME", "COMMIT", "INFO"]];
  if (multi) rows[0]?.splice(5, 0, "NODE");
  for (const r of runs) {
    const code = r.code ? `${r.code.commit?.slice(0, 7) ?? "-"}${r.code.dirty ? "*" : ""}` : "-";
    const gpus = r.lease?.gpuIds.length
      ? String(r.lease.gpuIds.length)
      : String(r.spec.resources.gpus);
    const row = [
      r.id,
      r.state,
      r.spec.group ?? "-",
      r.spec.name ?? "-",
      gpus,
      runDuration(r),
      code,
      r.reason ?? "",
    ];
    if (multi) row.splice(5, 0, r.state === "queued" ? "-" : r.node);
    rows.push(row);
  }
  return table(rows);
}

export function formatRun(r: Run, summary?: Record<string, number>): string {
  const lines = [
    `${r.id}  ${r.state}${r.reason ? ` (${r.reason})` : ""}`,
    `  name     ${r.spec.name ?? "-"}   group ${r.spec.group ?? "-"}`,
    `  command  ${r.spec.command.join(" ")}`,
    `  image    ${r.image ?? r.spec.dockerfile ?? "-"}`,
    `  request  ${r.spec.resources.gpus} GPU, ${r.spec.resources.cpus} CPU, ${r.spec.resources.memGB} GB`,
    `  node     ${r.node}${r.remote ? " (remote; outputs stay there)" : ""}${r.origin ? ` (from ${r.origin})` : ""}`,
  ];
  if (r.lease) lines.push(`  lease    ${r.lease.state} ${r.lease.gpuIds.join(", ") || "no GPUs"}`);
  if (r.code) {
    const c = r.code;
    lines.push(
      `  code     ${c.repo}${c.subdir ? `/${c.subdir}` : ""} @ ${c.commit?.slice(0, 12) ?? "(no commit)"}${c.dirty ? ` +${c.changedFiles.length} changed` : ""}`,
    );
  }
  lines.push(
    `  time     created ${r.createdAt}  ran ${runDuration(r)}  exit ${r.exitCode ?? "-"}  cleanup ${r.cleanup}`,
  );
  if (Object.keys(r.spec.params).length)
    lines.push(
      `  params   ${Object.entries(r.spec.params)
        .map(([k, v]) => `${k}=${v}`)
        .join(" ")}`,
    );
  if (r.spec.agent)
    lines.push(
      `  agent    ${r.spec.agent.harness} ${r.spec.agent.sessionId ?? "(session unknown)"}`,
    );
  if (summary && Object.keys(summary).length) {
    lines.push(
      `  metrics  ${Object.entries(summary)
        .map(([k, v]) => `${k}=${fmtNum(v)}`)
        .join("  ")}`,
    );
  }
  if (r.note) lines.push(`  note     ${r.note.split("\n").join("\n           ")}`);
  return lines.join("\n");
}

export function fmtNum(v: number): string {
  if (Number.isInteger(v)) return String(v);
  const a = Math.abs(v);
  return a !== 0 && (a < 1e-3 || a >= 1e5) ? v.toExponential(3) : String(Number(v.toPrecision(5)));
}

function formatNode(r: NodeResources, leases: Lease[], head: string): string[] {
  const owner = new Map(leases.flatMap((x) => x.gpuIds.map((g) => [g, x.runId] as const)));
  const lines = [head];
  if (r.gpuError) lines.push(`gpus: unavailable (${r.gpuError})`);
  for (const g of r.gpus) {
    const run = owner.get(g.uuid);
    const state = run ? `run ${run}` : g.available ? "free" : "busy (external)";
    const util = g.utilPct === null ? "-" : `${g.utilPct}%`;
    lines.push(
      `  gpu${g.index} ${g.name}  ${g.memUsedMiB}/${g.memTotalMiB} MiB  util ${util.padStart(4)}  ${state}`,
    );
  }
  const leasedCpu = leases.reduce((n, x) => n + x.cpus, 0);
  const leasedMem = leases.reduce((n, x) => n + x.memGB, 0);
  lines.push(
    `cpu     ${r.cpu.count} cores, ${leasedCpu} leased, ${r.cpu.busy} in use, load ${r.cpu.load1}`,
  );
  lines.push(
    `memory  ${r.memory.totalGB} GB, ${leasedMem} leased, ${r.memory.availableGB} available`,
  );
  lines.push(`disk    ${r.disk.freeGB}/${r.disk.totalGB} GB free (${r.disk.path})`);
  return lines;
}

export function formatLedger(l: Ledger): string {
  const lines = formatNode(l.resources, l.leases, `node ${l.resources.node}`);
  for (const n of l.nodes) {
    const state = n.online ? "online" : `offline${n.error ? ` (${n.error})` : ""}`;
    const head = `\nnode ${n.name}  ${n.url}  ${state}`;
    if (!n.info) {
      lines.push(head);
      continue;
    }
    lines.push(...formatNode(n.info.resources, n.info.leases, head));
    lines.push(`queue   ${n.info.queued} waiting there`);
    if (n.info.datasets.length) lines.push(`data    ${n.info.datasets.join(", ")}`);
  }
  lines.push(`${l.nodes.length ? "\n" : ""}queue   ${l.queued.length === 0 ? "empty" : ""}`);
  for (const q of l.queued) lines.push(`  ${q.runId}  ${q.reason ?? ""}`);
  return lines.join("\n");
}

export function formatDoctor(r: DoctorReport): string {
  return r.checks
    .map((c) => `${c.ok ? "ok  " : "FAIL"} ${c.name.padEnd(11)} ${c.detail}`)
    .join("\n");
}
