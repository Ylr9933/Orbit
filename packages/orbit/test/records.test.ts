import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { downsample, readLog, readMetrics, safeJoin } from "../src/records/index.ts";

const dir = mkdtempSync(join(tmpdir(), "orbit-records-"));

describe("records", () => {
  it("reads logs in chunks without splitting UTF-8 characters", async () => {
    const f = join(dir, "log.txt");
    writeFileSync(f, "ab中文\nline2\n");
    const first = await readLog(f, 0, 4, false); // "ab" + first byte of 中 would split
    expect(first.text).toBe("ab");
    const rest = await readLog(f, first.next, 1024, true);
    expect(first.text + rest.text).toBe("ab中文\nline2\n");
    expect(rest.eof).toBe(true);
    const tail = await readLog(f, -7, 1024, false);
    expect(tail.text).toBe("line2\n");
  });

  it("parses metrics, falling back to the line number as step", async () => {
    const f = join(dir, "metrics.jsonl");
    writeFileSync(
      f,
      '{"step": 10, "loss": 0.5}\nnot json\n{"loss": 0.25, "acc": 0.9, "tag": "x"}\n[1]\n',
    );
    const m = await readMetrics(f);
    expect(m.invalidLines).toBe(2);
    expect(m.series).toEqual([
      { key: "acc", points: [[3, 0.9]] },
      {
        key: "loss",
        points: [
          [10, 0.5],
          [3, 0.25],
        ],
      },
    ]);
    expect(m.summary).toEqual({ acc: 0.9, loss: 0.25 });
    expect((await readMetrics(join(dir, "missing"))).series).toEqual([]);
  });

  it("downsamples but keeps the last point", () => {
    const pts = Array.from({ length: 10 }, (_, i) => i);
    expect(downsample(pts, 4)).toEqual([0, 3, 6, 9]);
    expect(downsample(pts, 20)).toBe(pts);
  });

  it("refuses paths escaping the artifact directory", () => {
    expect(safeJoin("/a/b", "c/d.txt")).toBe("/a/b/c/d.txt");
    expect(safeJoin("/a/b", "../x")).toBeNull();
    expect(safeJoin("/a/b", "/etc/passwd")).toBeNull();
  });
});
