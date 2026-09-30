import { chmodSync, existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import {
  isTerminal,
  type NotifyEvent,
  type NotifyTarget,
  NotifyTargetInput,
  type NotifyTargetInput as NotifyTargetInputT,
  type Run,
} from "../contracts/index.ts";

type StoredTarget = ReturnType<typeof NotifyTargetInput.parse>;

/** Webhook URLs usually embed a token: show only the origin and the last 4 characters. */
export function urlHint(url: string): string {
  try {
    const u = new URL(url);
    return `${u.origin}/…${url.slice(-4)}`;
  } catch {
    return "…";
  }
}

const toPublic = (t: StoredTarget): NotifyTarget => ({
  name: t.name,
  kind: t.kind,
  on: t.on,
  urlHint: urlHint(t.url),
});

/** Notification targets in one 0600 JSON file, written only by the daemon. */
export class NotifyStore {
  private readonly file: string;

  constructor(file: string) {
    this.file = file;
  }

  private read(): StoredTarget[] {
    if (!existsSync(this.file)) return [];
    const raw = JSON.parse(readFileSync(this.file, "utf8")) as { targets?: unknown[] };
    return (raw.targets ?? []).map((t) => NotifyTargetInput.parse(t));
  }

  private write(targets: StoredTarget[]): void {
    const tmp = `${this.file}.${process.pid}.tmp`;
    writeFileSync(tmp, `${JSON.stringify({ version: 1, targets }, null, 2)}\n`, { mode: 0o600 });
    chmodSync(tmp, 0o600);
    renameSync(tmp, this.file);
  }

  list(): NotifyTarget[] {
    return this.read().map(toPublic);
  }

  targets(): StoredTarget[] {
    return this.read();
  }

  put(input: NotifyTargetInputT): NotifyTarget {
    const t = NotifyTargetInput.parse(input);
    const all = [...this.read().filter((x) => x.name !== t.name), t].sort((a, b) =>
      a.name.localeCompare(b.name),
    );
    this.write(all);
    return toPublic(t);
  }

  remove(name: string): boolean {
    const all = this.read();
    const rest = all.filter((t) => t.name !== name);
    if (rest.length === all.length) return false;
    this.write(rest);
    return true;
  }
}

export interface Message {
  event: NotifyEvent;
  title: string;
  text: string;
  runs: Run[];
}

/** Request body for each target kind. */
export function payload(kind: StoredTarget["kind"], m: Message): unknown {
  const text = `${m.title}\n${m.text}`.trim();
  switch (kind) {
    case "feishu":
      return { msg_type: "text", content: { text } };
    case "dingtalk":
    case "wecom":
      return { msgtype: "text", text: { content: text } };
    case "slack":
      return { text };
    case "webhook":
      return {
        event: m.event,
        title: m.title,
        text: m.text,
        runs: m.runs.map((r) => ({
          id: r.id,
          name: r.spec.name ?? null,
          group: r.spec.group ?? null,
          state: r.state,
          reason: r.reason,
        })),
      };
  }
}

const label = (r: Run) => r.spec.name ?? r.id;

export function runMessage(run: Run, logTail: string, webUrl?: string): Message {
  const ok = run.state === "succeeded";
  const lines = [`state: ${run.state}${run.reason ? ` (${run.reason})` : ""}`];
  if (run.startedAt && run.endedAt) lines.push(`duration: ${duration(run.startedAt, run.endedAt)}`);
  if (!ok && logTail) lines.push("", logTail);
  if (webUrl) lines.push("", `${webUrl}/runs/${run.id}`);
  return {
    event: ok ? "succeeded" : "failed",
    title: `[orbit] ${ok ? "✅" : "❌"} ${label(run)} ${run.state}`,
    text: lines.join("\n"),
    runs: [run],
  };
}

export function groupMessage(group: string, runs: Run[], webUrl?: string): Message {
  const count = (s: Run["state"]) => runs.filter((r) => r.state === s).length;
  const bad = runs.filter((r) => r.state !== "succeeded");
  const lines = [
    `${count("succeeded")} succeeded, ${count("failed")} failed` +
      (count("cancelled") ? `, ${count("cancelled")} cancelled` : "") +
      (count("lost") ? `, ${count("lost")} lost` : ""),
  ];
  for (const r of bad.slice(0, 10))
    lines.push(`- ${label(r)}: ${r.state}${r.reason ? ` (${r.reason})` : ""}`);
  if (bad.length > 10) lines.push(`- … ${bad.length - 10} more`);
  if (webUrl) lines.push("", `${webUrl}/compare?group=${encodeURIComponent(group)}`);
  return {
    event: "group",
    title: `[orbit] ${bad.length === 0 ? "✅" : "⚠️"} group ${group} finished (${runs.length} runs)`,
    text: lines.join("\n"),
    runs,
  };
}

function duration(a: string, b: string): string {
  const s = Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60}s`;
  return `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`;
}

export async function send(target: StoredTarget, m: Message): Promise<void> {
  const res = await fetch(target.url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload(target.kind, m)),
    signal: AbortSignal.timeout(10_000),
  });
  const body = await res.text().catch(() => "");
  if (!res.ok) throw new Error(`HTTP ${res.status} ${body.slice(0, 200)}`);
  // Feishu, DingTalk and WeCom answer 200 with an error code in the body.
  try {
    const j = JSON.parse(body) as {
      code?: number;
      errcode?: number;
      msg?: string;
      errmsg?: string;
    };
    const code = j.code ?? j.errcode ?? 0;
    if (code !== 0) throw new Error(`error ${code}: ${j.msg ?? j.errmsg ?? ""}`);
  } catch (e) {
    if (!(e instanceof SyntaxError)) throw e;
  }
}

export interface NotifierDeps {
  store: NotifyStore;
  /** All runs of a group. */
  groupRuns(group: string): Run[];
  /** Last lines of the (already redacted) log. */
  logTail(runId: string): string;
  /** Daemon URL for links, known once the server listens. */
  webUrl?: () => string | undefined;
  /** Where send errors go; they never affect runs. */
  log?: (msg: string) => void;
}

/**
 * Decides what to send when a run reaches a terminal state: ungrouped runs notify on their own; a
 * group sends one summary when its last queued or running run ends.
 */
export class Notifier {
  private readonly deps: NotifierDeps;

  constructor(deps: NotifierDeps) {
    this.deps = deps;
  }

  /** Call with each run change whose event kind is the run's new terminal state. */
  onTerminal(run: Run): Promise<void> {
    if (!isTerminal(run.state)) return Promise.resolve();
    const group = run.spec.group;
    if (!group) {
      if (run.state === "cancelled") return Promise.resolve();
      const tail = run.state === "succeeded" ? "" : this.deps.logTail(run.id);
      const m = runMessage(run, tail, this.deps.webUrl?.());
      return this.deliver(m);
    }
    const runs = this.deps.groupRuns(group);
    if (runs.some((r) => !isTerminal(r.state))) return Promise.resolve();
    return this.deliver(groupMessage(group, runs, this.deps.webUrl?.()));
  }

  async deliver(m: Message, only?: string): Promise<void> {
    const targets = this.deps.store
      .targets()
      .filter((t) => (only ? t.name === only : t.on.includes(m.event)));
    await Promise.all(
      targets.map((t) =>
        send(t, m).catch((e: Error) => {
          this.deps.log?.(`notify ${t.name}: ${e.message}`);
          if (only) throw e;
        }),
      ),
    );
  }

  /** Send a test message to one target; throws on failure. */
  test(name: string): Promise<void> {
    return this.deliver(
      {
        event: "succeeded",
        title: "[orbit] test notification",
        text: "Orbit can reach this target.",
        runs: [],
      },
      name,
    );
  }
}
