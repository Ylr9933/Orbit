import { describe, expect, it } from "vitest";
import { parseDiff, splitRows } from "../src/lib/diff.ts";
import { ema, stats } from "../src/lib/ema.ts";
import { collapseCR, stripAnsi, toLines } from "../src/lib/log.ts";

const PATCH = `diff --git a/train.py b/train.py
index 111..222 100644
--- a/train.py
+++ b/train.py
@@ -1,3 +1,4 @@
 import torch
-lr = 1e-3
+lr = 3e-4
+warmup = 100
 print(lr)
diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+hello
diff --git a/img.png b/img.png
Binary files a/img.png and b/img.png differ
`;

describe("parseDiff", () => {
  it("parses files, statuses and counts", () => {
    const files = parseDiff(PATCH);
    expect(files.map((f) => [f.newPath, f.status, f.additions, f.deletions, f.binary])).toEqual([
      ["train.py", "modified", 2, 1, false],
      ["new.txt", "added", 1, 0, false],
      ["img.png", "modified", 0, 0, true],
    ]);
  });
  it("pairs deletions with additions in split rows", () => {
    const f = parseDiff(PATCH)[0];
    const rows = splitRows(f?.hunks[0]?.lines ?? []);
    const changed = rows.find((r) => r.left?.type === "del");
    expect(changed?.right?.text).toBe("lr = 3e-4");
  });
});

describe("log", () => {
  it("collapses carriage-return progress bars", () => {
    expect(collapseCR("10%\r50%\r100%")).toBe("100%");
  });
  it("strips ansi and classifies lines", () => {
    expect(stripAnsi("\x1b[31mred\x1b[0m")).toBe("red");
    const lines = toLines("[orbit] started\nTraceback (most recent call last):\nok", 5);
    expect(lines.map((l) => [l.n, l.kind])).toEqual([
      [5, "sys"],
      [6, "err"],
      [7, "out"],
    ]);
  });
});

describe("ema", () => {
  it("is debiased and identity at weight 0", () => {
    expect(ema([1, 2, 3], 0)).toEqual([1, 2, 3]);
    expect(ema([5, 5, 5], 0.9)[0]).toBeCloseTo(5);
  });
  it("computes stats", () => {
    const s = stats([1, 2, 3]);
    expect([s.min, s.max, s.mean]).toEqual([1, 3, 2]);
    expect(s.std).toBeCloseTo(1);
  });
});
