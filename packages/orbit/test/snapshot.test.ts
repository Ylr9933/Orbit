import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { snapshotProject } from "../src/workspace/snapshot.ts";

function repo(): string {
  const d = mkdtempSync(join(tmpdir(), "orbit-repo-"));
  const git = (...a: string[]) => execFileSync("git", ["-C", d, ...a], { stdio: "pipe" });
  git("init", "-q");
  mkdirSync(join(d, "src"));
  writeFileSync(join(d, "src/a.py"), "print(1)\n");
  writeFileSync(join(d, ".gitignore"), "data/\n");
  git("add", ".");
  git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init");
  return d;
}

describe("snapshotProject", () => {
  it("copies tracked + untracked files, skips ignored ones, and records the diff", async () => {
    const d = repo();
    writeFileSync(join(d, "src/a.py"), "print(2)\n");
    writeFileSync(join(d, "new.txt"), "hello\n");
    mkdirSync(join(d, "data"));
    writeFileSync(join(d, "data/big.bin"), "x");
    const out = mkdtempSync(join(tmpdir(), "orbit-snap-"));
    const snap = await snapshotProject(join(d, "src"), join(out, "ws"), join(out, "code.diff"));
    expect(snap.subdir).toBe("src");
    expect(snap.dirty).toBe(true);
    expect(snap.changedFiles.sort()).toEqual(["new.txt", "src/a.py"]);
    expect(readFileSync(join(out, "ws/src/a.py"), "utf8")).toBe("print(2)\n");
    expect(existsSync(join(out, "ws/new.txt"))).toBe(true);
    expect(existsSync(join(out, "ws/data/big.bin"))).toBe(false);
    const diff = readFileSync(join(out, "code.diff"), "utf8");
    expect(diff).toContain("+print(2)");
    expect(diff).toContain("+hello");
    // The real index is untouched: new.txt is still untracked.
    expect(execFileSync("git", ["-C", d, "status", "--porcelain"], { encoding: "utf8" })).toContain(
      "?? new.txt",
    );
  });

  it("reports a clean tree and rejects non-repositories", async () => {
    const d = repo();
    const out = mkdtempSync(join(tmpdir(), "orbit-snap-"));
    const snap = await snapshotProject(d, join(out, "ws"), join(out, "code.diff"));
    expect(snap.dirty).toBe(false);
    expect(snap.commit).toMatch(/^[0-9a-f]{40}$/);
    await expect(snapshotProject(tmpdir(), join(out, "x"), join(out, "y"))).rejects.toThrow(
      /not inside a git/,
    );
  });
});
