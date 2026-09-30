// Parser for `git diff --binary` unified patches.

export interface DiffLine {
  type: "add" | "del" | "ctx";
  text: string;
  old: number | null;
  new: number | null;
}
export interface Hunk {
  header: string;
  lines: DiffLine[];
}
export interface DiffFile {
  oldPath: string;
  newPath: string;
  status: "added" | "deleted" | "modified" | "renamed";
  binary: boolean;
  hunks: Hunk[];
  additions: number;
  deletions: number;
}

const unquote = (p: string) => {
  if (!p.startsWith('"')) return p;
  try {
    return JSON.parse(p) as string;
  } catch {
    return p.slice(1, -1);
  }
};
const strip = (p: string) => {
  const u = unquote(p.trim());
  return u === "/dev/null" ? u : u.replace(/^[ab]\//, "");
};

export function parseDiff(patch: string): DiffFile[] {
  const files: DiffFile[] = [];
  let f: DiffFile | null = null;
  let h: Hunk | null = null;
  let oldN = 0;
  let newN = 0;
  const lines = patch.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i] as string;
    if (l.startsWith("diff --git ")) {
      const m = /^diff --git (?:"?a\/)(.+?)"? (?:"?b\/)(.+?)"?$/.exec(l);
      f = {
        oldPath: m?.[1] ?? "",
        newPath: m?.[2] ?? "",
        status: "modified",
        binary: false,
        hunks: [],
        additions: 0,
        deletions: 0,
      };
      files.push(f);
      h = null;
      continue;
    }
    if (!f) continue;
    if (!h || !/^[ +\-\\]/.test(l)) {
      if (l.startsWith("new file mode")) f.status = "added";
      else if (l.startsWith("deleted file mode")) f.status = "deleted";
      else if (l.startsWith("rename from ")) {
        f.status = "renamed";
        f.oldPath = unquote(l.slice(12));
      } else if (l.startsWith("rename to ")) f.newPath = unquote(l.slice(10));
      else if (l.startsWith("--- ")) {
        const p = strip(l.slice(4));
        if (p !== "/dev/null") f.oldPath = p;
      } else if (l.startsWith("+++ ")) {
        const p = strip(l.slice(4));
        if (p !== "/dev/null") f.newPath = p;
      } else if (l.startsWith("GIT binary patch") || l.startsWith("Binary files")) f.binary = true;
      else if (l.startsWith("@@")) {
        const m = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(l);
        oldN = Number(m?.[1] ?? 0);
        newN = Number(m?.[2] ?? 0);
        h = { header: l, lines: [] };
        f.hunks.push(h);
      }
      continue;
    }
    const c = l[0];
    const text = l.slice(1);
    if (c === "+") {
      h.lines.push({ type: "add", text, old: null, new: newN++ });
      f.additions++;
    } else if (c === "-") {
      h.lines.push({ type: "del", text, old: oldN++, new: null });
      f.deletions++;
    } else if (c === " ") {
      h.lines.push({ type: "ctx", text, old: oldN++, new: newN++ });
    }
    // "\ No newline at end of file" is ignored.
  }
  // A trailing empty line from split() lands in the last hunk as nothing (it has no prefix).
  return files;
}

export interface SplitRow {
  left: DiffLine | null;
  right: DiffLine | null;
}

/** Pair deletions with following additions for side-by-side view. */
export function splitRows(lines: DiffLine[]): SplitRow[] {
  const rows: SplitRow[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i] as DiffLine;
    if (l.type === "ctx") {
      rows.push({ left: l, right: l });
      i++;
      continue;
    }
    const dels: DiffLine[] = [];
    const adds: DiffLine[] = [];
    while (i < lines.length && lines[i]?.type === "del") dels.push(lines[i++] as DiffLine);
    while (i < lines.length && lines[i]?.type === "add") adds.push(lines[i++] as DiffLine);
    for (let k = 0; k < Math.max(dels.length, adds.length); k++)
      rows.push({ left: dels[k] ?? null, right: adds[k] ?? null });
  }
  return rows;
}
