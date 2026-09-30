import { useEffect, useMemo, useRef, useState } from "react";
import { IconChevron, IconChevronDown, IconFile, IconGit } from "../../components/icons.tsx";
import { CopyButton, Empty, Loading } from "../../components/ui.tsx";
import { api, type Run } from "../../lib/api.ts";
import { type DiffFile, type DiffLine, parseDiff, splitRows } from "../../lib/diff.ts";
import { setHash, useLocation } from "../../lib/router.ts";
import { useAsync } from "../../lib/use.ts";

const pathOf = (f: DiffFile) => (f.status === "deleted" ? f.oldPath : f.newPath);
const STATUS: Record<DiffFile["status"], [string, string]> = {
  added: ["A", "var(--add-fg)"],
  deleted: ["D", "var(--del-fg)"],
  modified: ["M", "var(--st-cancelled)"],
  renamed: ["R", "var(--st-starting)"],
};

export function DiffTab({ run }: { run: Run }) {
  const diff = useAsync(() => api.diff(run.id), [run.id]);
  const files = useMemo(() => parseDiff(diff.data?.patch ?? ""), [diff.data]);
  const [mode, setMode] = useState<"unified" | "split">(
    () => (localStorage.getItem("orbit.diff") as "split") ?? "unified",
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const loc = useLocation();
  const target = decodeURIComponent(loc.hash);
  const box = useRef<HTMLDivElement>(null);
  const c = run.code;

  useEffect(() => {
    if (!target || !files.length) return;
    document.getElementById(`diff-${target}`)?.scrollIntoView({ block: "start" });
  }, [target, files.length]);

  if (!c)
    return (
      <Empty title="No code snapshot" icon={<IconGit size={30} />}>
        This run was submitted without a project (<code>--no-project</code> or not in a git
        repository).
      </Empty>
    );
  if (diff.loading && !diff.data) return <Loading what="Loading diff" />;

  const adds = files.reduce((a, f) => a + f.additions, 0);
  const dels = files.reduce((a, f) => a + f.deletions, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="toolbar">
        <IconGit size={14} />
        <span className="mono">
          {c.branch ?? "detached"} @ {c.commit?.slice(0, 12) ?? "no commits"}
        </span>
        {c.commit && <CopyButton text={c.commit} title="Copy commit" />}
        <span className="faint">
          {files.length ? (
            <>
              + uncommitted: {files.length} files <span className="adds">+{adds}</span>{" "}
              <span className="dels">−{dels}</span>
            </>
          ) : (
            "working tree was clean"
          )}
        </span>
        <div className="spacer" />
        {diff.data?.truncated && <span className="chip warn">diff truncated</span>}
        <div className="seg">
          {(["unified", "split"] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={mode === m ? "on" : ""}
              onClick={() => {
                setMode(m);
                localStorage.setItem("orbit.diff", m);
              }}
            >
              {m === "unified" ? "Unified" : "Split"}
            </button>
          ))}
        </div>
      </div>
      {!files.length ? (
        <Empty title="No uncommitted changes">
          The container ran exactly commit <code>{c.commit?.slice(0, 12)}</code> of{" "}
          <code>{c.repo}</code>.
        </Empty>
      ) : (
        <div className="split-pane">
          <div className="sidetree">
            {files.map((f) => {
              const p = pathOf(f);
              const [s, col] = STATUS[f.status];
              return (
                <div
                  key={p}
                  className={`f${p === target ? " on" : ""}`}
                  onClick={() => setHash(encodeURIComponent(p))}
                  title={p}
                >
                  <span className="mono" style={{ color: col, fontWeight: 600, width: 12 }}>
                    {s}
                  </span>
                  <span className="grow ellipsis" style={{ direction: "rtl", textAlign: "left" }}>
                    {p}
                  </span>
                  <span className="mono" style={{ fontSize: 11 }}>
                    <span className="adds">+{f.additions}</span>{" "}
                    <span className="dels">−{f.deletions}</span>
                  </span>
                </div>
              );
            })}
          </div>
          <div ref={box} className="scroll" style={{ padding: 14 }}>
            {files.map((f) => {
              const p = pathOf(f);
              const closed = collapsed.has(p);
              return (
                <div key={p} id={`diff-${p}`} className="diff-file" style={{ scrollMarginTop: 8 }}>
                  <header
                    onClick={() =>
                      setCollapsed((s) => {
                        const n = new Set(s);
                        if (n.has(p)) n.delete(p);
                        else n.add(p);
                        return n;
                      })
                    }
                  >
                    {closed ? <IconChevron size={14} /> : <IconChevronDown size={14} />}
                    <IconFile size={13} />
                    <span className="mono">
                      {f.status === "renamed" ? `${f.oldPath} → ${f.newPath}` : p}
                    </span>
                    <span className="chip" style={{ height: 18, color: STATUS[f.status][1] }}>
                      {f.status}
                    </span>
                    <div className="spacer" />
                    <span className="mono" style={{ fontSize: 12 }}>
                      <span className="adds">+{f.additions}</span>{" "}
                      <span className="dels">−{f.deletions}</span>
                    </span>
                  </header>
                  {!closed &&
                    (f.binary ? (
                      <div className="card-b faint">Binary file</div>
                    ) : f.hunks.length === 0 ? (
                      <div className="card-b faint">No textual changes (mode or empty file)</div>
                    ) : (
                      <table className="diff-table">
                        {mode === "split" ? (
                          <colgroup>
                            <col style={{ width: 52 }} />
                            <col />
                            <col style={{ width: 52 }} />
                            <col />
                          </colgroup>
                        ) : (
                          <colgroup>
                            <col style={{ width: 52 }} />
                            <col style={{ width: 52 }} />
                            <col style={{ width: 22 }} />
                            <col />
                          </colgroup>
                        )}
                        <tbody>
                          {f.hunks.map((h, hi) => (
                            <HunkRows
                              key={String(hi)}
                              header={h.header}
                              lines={h.lines}
                              mode={mode}
                            />
                          ))}
                        </tbody>
                      </table>
                    ))}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function HunkRows({
  header,
  lines,
  mode,
}: {
  header: string;
  lines: DiffLine[];
  mode: "unified" | "split";
}) {
  if (mode === "unified")
    return (
      <>
        <tr className="hunk">
          <td colSpan={4}>{header}</td>
        </tr>
        {lines.map((l, i) => (
          <tr key={String(i)} className={l.type === "ctx" ? "" : l.type}>
            <td className="n">{l.old ?? ""}</td>
            <td className="n">{l.new ?? ""}</td>
            <td className="s">{l.type === "add" ? "+" : l.type === "del" ? "−" : ""}</td>
            <td>{l.text || " "}</td>
          </tr>
        ))}
      </>
    );
  return (
    <>
      <tr className="hunk">
        <td colSpan={4}>{header}</td>
      </tr>
      {splitRows(lines).map((r, i) => (
        <tr key={String(i)}>
          <td
            className={`n ${r.left && r.left.type !== "ctx" ? r.left.type : ""} ${r.left ? "" : "blank"}`}
          >
            {r.left?.old ?? ""}
          </td>
          <td
            className={`${r.left && r.left.type !== "ctx" ? r.left.type : ""} ${r.left ? "" : "blank"}`}
          >
            {r.left ? r.left.text || " " : ""}
          </td>
          <td
            className={`n ${r.right && r.right.type !== "ctx" ? r.right.type : ""} ${r.right ? "" : "blank"}`}
          >
            {r.right?.new ?? ""}
          </td>
          <td
            className={`${r.right && r.right.type !== "ctx" ? r.right.type : ""} ${r.right ? "" : "blank"}`}
          >
            {r.right ? r.right.text || " " : ""}
          </td>
        </tr>
      ))}
    </>
  );
}
