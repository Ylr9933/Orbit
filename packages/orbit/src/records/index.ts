import { createReadStream } from "node:fs";
import { open, readdir, readFile, stat } from "node:fs/promises";
import { join, relative, resolve, sep } from "node:path";
import { createInterface } from "node:readline";
import type { Artifacts, LogChunk, Metrics } from "../contracts/index.ts";

export const MAX_LOG_CHUNK = 1024 * 1024;
const MAX_DIFF_BYTES = 5 * 1024 * 1024;
const MAX_ARTIFACTS = 2000;
const MAX_POINTS_PER_SERIES = 5000;

/** Read up to `limit` bytes of a log from `offset`. A negative offset reads the tail. */
export async function readLog(
  file: string,
  offset: number,
  limit: number,
  terminal: boolean,
): Promise<LogChunk> {
  const size = (await stat(file).catch(() => null))?.size ?? 0;
  const len = Math.min(Math.max(1, limit), MAX_LOG_CHUNK);
  let start = offset < 0 ? Math.max(0, size + offset) : Math.min(offset, size);
  const end = Math.min(size, start + len);
  let text = "";
  if (end > start) {
    const fh = await open(file, "r");
    try {
      const buf = Buffer.alloc(end - start);
      await fh.read(buf, 0, buf.length, start);
      // Never split a UTF-8 sequence: trim a partial trailing character, and skip a partial leading one.
      let from = 0;
      if (offset < 0 && start > 0) {
        const nl = buf.indexOf(10);
        if (nl >= 0 && nl < buf.length - 1) from = nl + 1;
      }
      while (from < buf.length && ((buf[from] ?? 0) & 0xc0) === 0x80) from++;
      let to = buf.length;
      if (end < size) to = safeUtf8End(buf);
      text = buf.subarray(from, to).toString("utf8");
      start += from;
      return {
        offset: start,
        next: start + (to - from),
        size,
        text,
        eof: terminal && start + (to - from) >= size,
      };
    } finally {
      await fh.close();
    }
  }
  return { offset: start, next: start, size, text, eof: terminal && start >= size };
}

function safeUtf8End(buf: Buffer): number {
  // Walk back over continuation bytes to the lead byte and drop the sequence if incomplete.
  let i = buf.length - 1;
  let cont = 0;
  while (i >= 0 && ((buf[i] ?? 0) & 0xc0) === 0x80 && cont < 3) {
    i--;
    cont++;
  }
  if (i < 0) return buf.length;
  const lead = buf[i] ?? 0;
  const need = lead >= 0xf0 ? 3 : lead >= 0xe0 ? 2 : lead >= 0xc0 ? 1 : 0;
  return need > cont ? i : buf.length;
}

/** Parse `metrics.jsonl`: one JSON object per line; numeric fields become series keyed by name. */
export async function readMetrics(file: string): Promise<Metrics> {
  const series = new Map<string, [number, number][]>();
  let invalid = 0;
  let line = 0;
  const exists = await stat(file).catch(() => null);
  if (exists) {
    const rl = createInterface({ input: createReadStream(file, "utf8"), crlfDelay: Infinity });
    for await (const raw of rl) {
      if (!raw.trim()) continue;
      line++;
      let obj: unknown;
      try {
        obj = JSON.parse(raw);
      } catch {
        invalid++;
        continue;
      }
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
        invalid++;
        continue;
      }
      const rec = obj as Record<string, unknown>;
      const step = typeof rec.step === "number" ? rec.step : line;
      for (const [k, v] of Object.entries(rec)) {
        if (k === "step" || typeof v !== "number" || !Number.isFinite(v)) continue;
        const s = series.get(k);
        if (s) s.push([step, v]);
        else series.set(k, [[step, v]]);
      }
    }
  }
  const out: Metrics = { series: [], summary: {}, invalidLines: invalid };
  for (const [key, points] of [...series].sort(([a], [b]) => a.localeCompare(b))) {
    out.series.push({ key, points: downsample(points, MAX_POINTS_PER_SERIES) });
    const last = points.at(-1);
    if (last) out.summary[key] = last[1];
  }
  return out;
}

/** Keep every k-th point plus the last one; enough for review charts. */
export function downsample<T>(points: T[], max: number): T[] {
  if (points.length <= max) return points;
  const k = Math.ceil(points.length / max);
  const out = points.filter((_, i) => i % k === 0);
  const last = points.at(-1);
  if (last !== undefined && out.at(-1) !== last) out.push(last);
  return out;
}

export async function listArtifacts(dir: string): Promise<Artifacts> {
  const files: Artifacts["files"] = [];
  let truncated = false;
  async function walk(d: string): Promise<void> {
    const entries = await readdir(d, { withFileTypes: true }).catch(() => []);
    for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (files.length >= MAX_ARTIFACTS) {
        truncated = true;
        return;
      }
      const p = join(d, e.name);
      if (e.isDirectory()) await walk(p);
      else if (e.isFile()) {
        const st = await stat(p);
        files.push({ path: relative(dir, p), bytes: st.size, mtime: st.mtime.toISOString() });
      }
    }
  }
  await walk(dir);
  return { files, truncated };
}

/** Resolve a user-supplied relative path inside `dir`, or null if it escapes. */
export function safeJoin(dir: string, rel: string): string | null {
  const root = resolve(dir);
  const p = resolve(root, rel);
  return p === root || p.startsWith(root + sep) ? p : null;
}

export async function readDiff(file: string): Promise<{ patch: string; truncated: boolean }> {
  const st = await stat(file).catch(() => null);
  if (!st) return { patch: "", truncated: false };
  if (st.size <= MAX_DIFF_BYTES) return { patch: await readFile(file, "utf8"), truncated: false };
  const fh = await open(file, "r");
  try {
    const buf = Buffer.alloc(MAX_DIFF_BYTES);
    await fh.read(buf, 0, MAX_DIFF_BYTES, 0);
    return { patch: buf.toString("utf8"), truncated: true };
  } finally {
    await fh.close();
  }
}
