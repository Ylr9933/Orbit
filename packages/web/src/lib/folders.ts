// Folders are a path field on runs and bench jobs (`rcb/noskills`); the tree and its totals are
// derived here from the daemon's per-folder counts. Same nesting rule as `contracts.inFolder`.
import type { FolderStat } from "./api.ts";

export const inFolder = (f: string, folder: string) =>
  folder === "" || f === folder || f.startsWith(`${folder}/`);

export interface FolderNode {
  path: string;
  name: string;
  depth: number;
  /** Totals over the folder and its subfolders. */
  runs: number;
  jobs: number;
  active: number;
  sizeBytes: number;
}

/** Every folder and parent in use, depth-first by name, with totals over subfolders. */
export function folderTree(stats: FolderStat[]): FolderNode[] {
  const paths = new Set<string>();
  for (const s of stats) {
    const parts = s.path.split("/");
    for (let i = 1; i <= parts.length; i++) paths.add(parts.slice(0, i).join("/"));
  }
  return [...paths].sort().map((path) => {
    const sub = stats.filter((s) => inFolder(s.path, path));
    const sum = (k: "runs" | "jobs" | "active" | "sizeBytes") => sub.reduce((a, s) => a + s[k], 0);
    return {
      path,
      name: path.slice(path.lastIndexOf("/") + 1),
      depth: path.split("/").length - 1,
      runs: sum("runs"),
      jobs: sum("jobs"),
      active: sum("active"),
      sizeBytes: sum("sizeBytes"),
    };
  });
}

/** Same rule as the daemon's `Folder` schema; returns an error message or null. */
export function folderError(f: string): string | null {
  if (f === "") return null;
  if (f.length > 200) return "at most 200 characters";
  const ok = f.split("/").every((p) => /^[\p{L}\p{N}_.-]+$/u.test(p) && p !== "." && p !== "..");
  return ok ? null : "names of letters, digits, _ . - separated by /, e.g. rcb/noskills";
}
