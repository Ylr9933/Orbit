// Log text processing: split into display lines, collapse carriage-return progress bars,
// classify Orbit system lines and likely errors.

import type { LogChunk } from "@zjunlp/orbit/contracts";
import Anser from "anser";

/** A withheld live tail must wait for the next poll, even when the file has more bytes. */
export function canReadMoreLogs(chunk: LogChunk): boolean {
  return chunk.next > chunk.offset && chunk.next < chunk.size;
}

export interface LogLine {
  /** 1-based line number. */
  n: number;
  /** Raw text with ANSI codes (after \r collapse). */
  raw: string;
  /** Plain text for search. */
  plain: string;
  kind: "sys" | "err" | "out";
}

const ERR_RE =
  /\b(error|exception|traceback|fatal|panic|killed|out of memory|oom|cuda error|segmentation fault)\b/i;
const SYS_RE = /^\[orbit\]/;

/** Keep only what a terminal would show for a line that redraws itself with \r. */
export function collapseCR(line: string): string {
  if (!line.includes("\r")) return line;
  const parts = line.split("\r").filter((p) => p.length > 0);
  return parts[parts.length - 1] ?? "";
}

export function stripAnsi(s: string): string {
  // biome-ignore lint/suspicious/noControlCharactersInRegex: ANSI escape sequences
  return s.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "");
}

export function toLines(text: string, startN = 1): LogLine[] {
  const parts = text.split("\n");
  if (parts[parts.length - 1] === "") parts.pop();
  return parts.map((p, i) => {
    const raw = collapseCR(p);
    const plain = stripAnsi(raw);
    const kind = SYS_RE.test(plain) ? "sys" : ERR_RE.test(plain) ? "err" : "out";
    return { n: startN + i, raw, plain, kind };
  });
}

export interface Span {
  text: string;
  fg?: string;
  bg?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

export function ansiSpans(raw: string): Span[] {
  if (!raw.includes("\x1b")) return [{ text: raw }];
  return Anser.ansiToJson(raw, { json: true, remove_empty: true, use_classes: false }).map((c) => {
    const d = c.decorations ?? [];
    return {
      text: c.content,
      fg: c.fg ? `rgb(${c.fg})` : undefined,
      bg: c.bg ? `rgb(${c.bg})` : undefined,
      bold: d.includes("bold"),
      dim: d.includes("dim"),
      italic: d.includes("italic"),
      underline: d.includes("underline"),
    };
  });
}
