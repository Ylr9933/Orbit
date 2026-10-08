// Feishu self-built app over the plain OpenAPI (no SDK): tenant token, sending and Card 2.0 layouts.
// The long connection that receives commands lives in the `feishu` module.
import type { Ledger, Metrics, Run } from "../contracts/index.ts";

const API = "https://open.feishu.cn/open-apis";

export type Card = Record<string, unknown>;
export type ReceiveIdType = "open_id" | "chat_id";

/** OpenAPI calls of one app; the tenant token is cached until shortly before it expires. */
export class FeishuApi {
  private readonly appId: string;
  private readonly appSecret: string;
  private cached: { token: string; until: number } | null = null;

  constructor(appId: string, appSecret: string) {
    this.appId = appId;
    this.appSecret = appSecret;
  }

  private async token(): Promise<string> {
    if (this.cached && Date.now() < this.cached.until) return this.cached.token;
    const j = await call<{ tenant_access_token: string; expire: number }>(
      `${API}/auth/v3/tenant_access_token/internal`,
      { app_id: this.appId, app_secret: this.appSecret },
    );
    this.cached = {
      token: j.tenant_access_token,
      until: Date.now() + Math.max(60, j.expire - 300) * 1000,
    };
    return j.tenant_access_token;
  }

  async sendCard(type: ReceiveIdType, id: string, card: Card): Promise<void> {
    await call(
      `${API}/im/v1/messages?receive_id_type=${type}`,
      { receive_id: id, msg_type: "interactive", content: JSON.stringify(card) },
      await this.token(),
    );
  }
}

async function call<T>(url: string, body: unknown, token?: string): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  });
  const text = await res.text();
  let j: { code?: number; msg?: string } & T;
  try {
    j = JSON.parse(text);
  } catch {
    throw new Error(`HTTP ${res.status} ${text.slice(0, 200)}`);
  }
  if (!res.ok || (j.code ?? 0) !== 0)
    throw new Error(`error ${j.code ?? res.status}: ${(j.msg ?? text).slice(0, 300)}`);
  return j;
}

// ---- cards ----

type Template = "green" | "red" | "orange" | "blue" | "grey";

/** Validated with the dataviz palette checks (chroma, contrast on a light surface). */
const LINE = "#2a78d6";
const MAX_CHARTS = 2;
const MAX_POINTS = 200;

export function card(
  title: string,
  subtitle: string,
  template: Template,
  elements: unknown[],
): Card {
  return {
    schema: "2.0",
    config: { width_mode: "fill", summary: { content: title } },
    header: {
      title: { tag: "plain_text", content: title },
      ...(subtitle ? { subtitle: { tag: "plain_text", content: subtitle } } : {}),
      template,
    },
    body: { elements },
  };
}

export const md = (content: string) => ({ tag: "markdown", content });
export const hr = { tag: "hr" };
const columns = (cells: string[]) => ({
  tag: "column_set",
  flex_mode: "none",
  columns: cells.map((c) => ({
    tag: "column",
    width: "weighted",
    weight: 1,
    elements: [md(c)],
  })),
});
/** Markdown code block; backticks inside are broken up so they cannot close it. */
const code = (text: string) => md(`\`\`\`\n${text.replaceAll("```", "``​`")}\n\`\`\``);

/** About four significant digits, without exponents for usual magnitudes. */
export function num(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  return Number(v.toPrecision(4)).toString();
}

export function duration(a: string | null, b: string | null): string {
  if (!a) return "";
  const s = Math.max(0, Math.round(((b ? Date.parse(b) : Date.now()) - Date.parse(a)) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60}s`;
  return `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`;
}

const label = (r: Run) => r.spec.name ?? r.id;

const STATE_ICON: Record<Run["state"], string> = {
  queued: "⏳",
  starting: "🚀",
  running: "▶️",
  succeeded: "✅",
  failed: "❌",
  cancelled: "⏹",
  lost: "❓",
};

/** Up to two series, losses first: the plain line chart chosen on a phone (no marks, no labels). */
export function metricCharts(metrics: Metrics | null): unknown[] {
  if (!metrics) return [];
  const series = metrics.series
    .filter((s) => s.points.length >= 2)
    .sort((a, b) => Number(!/loss/i.test(a.key)) - Number(!/loss/i.test(b.key)))
    .slice(0, MAX_CHARTS);
  return series.map((s) => ({
    tag: "chart",
    chart_spec: {
      type: "line",
      data: { values: thin(s.points, MAX_POINTS).map(([step, v]) => ({ step, value: v })) },
      xField: "step",
      yField: "value",
      title: { text: `${s.key}  (last ${num(s.points.at(-1)?.[1] ?? Number.NaN)})` },
      point: { visible: false },
      label: { visible: false },
      line: { style: { lineWidth: 2, stroke: LINE } },
      axes: [{ orient: "left" }, { orient: "bottom" }],
      padding: { top: 6, bottom: 2, left: 2, right: 8 },
    },
  }));
}

function thin<T>(points: T[], max: number): T[] {
  if (points.length <= max) return points;
  const k = Math.ceil(points.length / max);
  const out = points.filter((_, i) => i % k === 0);
  const last = points.at(-1);
  if (last !== undefined && out.at(-1) !== last) out.push(last);
  return out;
}

/** One run: state, resources, measured peaks, metric curves and, when it failed, the log tail. */
export function runCard(run: Run, metrics: Metrics | null, logTail = ""): Card {
  const r = run.spec.resources;
  const u = run.usage;
  const template: Template =
    run.state === "succeeded"
      ? "green"
      : run.state === "failed" || run.state === "lost"
        ? "red"
        : run.state === "cancelled"
          ? "grey"
          : "blue";
  const took = duration(run.startedAt, run.endedAt);
  const elements: unknown[] = [
    columns([
      `**${r.gpus ? `${r.gpus} GPU` : "no GPU"}**\n${r.cpus} cpus · ${r.memGB} GB`,
      `**${u ? `${num(u.peakMemGB)} GB` : "—"}**\npeak memory`,
      r.gpus
        ? `**${u?.peakGpuMemGB != null ? `${num(u.peakGpuMemGB)} GB` : "—"}**\npeak GPU memory`
        : `**${u ? num(u.peakCpus) : "—"}**\npeak cpus`,
    ]),
  ];
  if (run.reason) elements.push(md(`**reason** ${run.reason}`));
  const charts = metricCharts(metrics);
  if (charts.length) elements.push(hr, ...charts);
  if (logTail && run.state !== "succeeded") elements.push(hr, md("**log tail**"), code(logTail));
  return card(
    `${STATE_ICON[run.state]} ${label(run)} ${run.state}`,
    [`run ${run.id}`, run.node, took].filter(Boolean).join(" · "),
    template,
    elements,
  );
}

/** A finished group: counts and the runs that did not succeed. */
export function groupCard(group: string, runs: Run[]): Card {
  const count = (s: Run["state"]) => runs.filter((r) => r.state === s).length;
  const bad = runs.filter((r) => r.state !== "succeeded");
  const cells = [`**${count("succeeded")}**\nsucceeded`, `**${count("failed")}**\nfailed`];
  const other = runs.length - count("succeeded") - count("failed");
  cells.push(`**${other}**\ncancelled / lost`);
  const elements: unknown[] = [columns(cells)];
  if (bad.length) {
    const lines = bad
      .slice(0, 10)
      .map((r) => `- ${label(r)}: ${r.state}${r.reason ? ` (${r.reason})` : ""}`);
    if (bad.length > 10) lines.push(`- … ${bad.length - 10} more`);
    elements.push(hr, md(lines.join("\n")));
  }
  return card(
    `${bad.length ? "⚠️" : "✅"} group ${group} finished`,
    `${runs.length} runs`,
    bad.length ? "orange" : "green",
    elements,
  );
}

/** GPUs (who holds each), CPU, memory, disk and the queue of this node, plus worker nodes. */
export function resourcesCard(l: Ledger): Card {
  const res = l.resources;
  const holder = (uuid: string, procs: Ledger["resources"]["gpus"][number]["processes"]) => {
    const lease = l.leases.find((x) => x.state === "active" && x.gpuIds.includes(uuid));
    if (lease) return `run ${lease.runId}`;
    const p = procs[0];
    if (!p) return "";
    return [p.user ?? "unknown", p.command ?? "", p.runId ? `run ${p.runId}` : ""]
      .filter(Boolean)
      .join(" ");
  };
  const gpuLines = res.gpus.map((g) => {
    const who = holder(g.uuid, g.processes);
    const used = `${num(g.memUsedMiB / 1024)}/${num(g.memTotalMiB / 1024)} GB`;
    const util = g.utilPct == null ? "" : ` · ${g.utilPct}%`;
    const state = g.available && !who ? "free" : who || "busy";
    return `${g.available && !who ? "🟢" : "🔴"} **GPU${g.index}** ${used}${util} · ${state}`;
  });
  const elements: unknown[] = [
    columns([
      `**${num(res.cpu.busy)}/${res.cpu.count}**\ncpus busy`,
      `**${num(res.memory.availableGB)} GB**\nmemory free`,
      `**${num(res.disk.freeGB)} GB**\ndisk free`,
    ]),
    hr,
    md(gpuLines.length ? gpuLines.join("\n") : (res.gpuError ?? "no GPUs")),
  ];
  if (l.queued.length) {
    const q = l.queued
      .slice(0, 5)
      .map((x) => `- ${x.runId}${x.reason ? `: ${x.reason}` : ""}`)
      .join("\n");
    elements.push(hr, md(`**${l.queued.length} queued**\n${q}`));
  }
  if (l.nodes.length) {
    const nodes = l.nodes.map((n) => {
      if (!n.online || !n.info) return `🔴 **${n.name}** offline`;
      const gpus = n.info.resources.gpus;
      const free = gpus.filter((g) => g.available).length;
      return `🟢 **${n.name}** ${free}/${gpus.length} GPUs free · ${n.info.leases.length} runs`;
    });
    elements.push(hr, md(nodes.join("\n")));
  }
  return card(`Resources · ${res.node}`, res.gpus[0]?.name ?? "", "blue", elements);
}

/** Recent runs, newest first. */
export function runsCard(runs: Run[]): Card {
  const lines = runs.map((r) => {
    const took = duration(r.startedAt, r.endedAt);
    return `${STATE_ICON[r.state]} **${label(r)}** ${r.state}${took ? ` · ${took}` : ""}\n<font color='grey'>${r.id}</font>`;
  });
  return card(
    "Recent runs",
    `${runs.filter((r) => r.state === "running").length} running · ${runs.filter((r) => r.state === "queued").length} queued`,
    "blue",
    [md(lines.length ? lines.join("\n") : "no runs yet")],
  );
}

export function textCard(title: string, text: string, template: Template = "blue"): Card {
  return card(title, "", template, [md(text)]);
}
