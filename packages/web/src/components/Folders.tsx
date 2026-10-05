// Folder sidebar of the run list (kept in `?folder=`) and the dialog that files runs and bench jobs
// in a folder. Folders are logical: moving changes a field, never the run directories.
import { useState } from "react";
import { api, type FolderStat } from "../lib/api.ts";
import { folderError, folderTree } from "../lib/folders.ts";
import { bytes } from "../lib/format.ts";
import { IconFolder, IconLayers } from "./icons.tsx";
import { toast } from "./ui.tsx";

export function FolderSidebar({
  stats,
  total,
  value,
  onChange,
}: {
  stats: FolderStat[];
  /** Runs in the whole list. */
  total: number;
  value: string;
  onChange: (folder: string) => void;
}) {
  const tree = folderTree(stats);
  const filed = stats.reduce((a, s) => a + s.runs, 0);
  return (
    <nav className="folders" aria-label="Folders">
      <div className="folders-h">Folders</div>
      <button
        type="button"
        className={`folder${value === "" ? " on" : ""}`}
        onClick={() => onChange("")}
      >
        <IconLayers size={13} />
        <span className="name">All runs</span>
        <span className="n">{total}</span>
      </button>
      {tree.map((f) => (
        <button
          key={f.path}
          type="button"
          className={`folder${value === f.path ? " on" : ""}`}
          style={{ paddingLeft: 10 + f.depth * 14 }}
          onClick={() => onChange(f.path)}
          title={`${f.path}\n${f.runs} runs · ${f.jobs} bench jobs · ${bytes(f.sizeBytes)}${f.active ? ` · ${f.active} active` : ""}`}
        >
          <IconFolder size={13} />
          <span className="name">{f.name}</span>
          {f.active > 0 && <span className="dot" />}
          <span className="n">{f.runs}</span>
        </button>
      ))}
      {tree.length === 0 ? (
        <p className="folders-hint faint">
          Select runs and choose <b>Move to folder</b>, or pass <code>--folder rcb/noskills</code>.
        </p>
      ) : (
        <p className="folders-hint faint">
          {total - filed} run{total - filed === 1 ? "" : "s"} not in a folder
        </p>
      )}
    </nav>
  );
}

/** File the given runs / bench jobs in a folder; a job takes all of its runs along. */
export function MoveDialog({
  ids,
  folders,
  initial,
  onClose,
  onMoved,
}: {
  ids: string[];
  folders: FolderStat[];
  initial: string;
  onClose: () => void;
  onMoved: (folder: string) => void;
}) {
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const target = value.trim().replace(/\/+$/, "");
  const err = folderError(target);
  const known = folderTree(folders).map((f) => f.path);
  const move = async () => {
    if (err || busy) return;
    setBusy(true);
    try {
      const r = await api.move(ids, target);
      toast(
        `Moved ${r.runs.length} run(s)${r.jobs.length ? ` and ${r.jobs.length} bench job(s)` : ""} to ${target || "no folder"}`,
      );
      onMoved(target);
      onClose();
    } catch (e) {
      toast((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="overlay" onMouseDown={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="move-title"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
      >
        <div className="dialog-h" id="move-title">
          Move {ids.length} run{ids.length === 1 ? "" : "s"} to a folder
        </div>
        <div className="dialog-b">
          <label htmlFor="move-input" className="faint" style={{ fontSize: 12.5 }}>
            Folder path, e.g. <span className="mono">rcb/noskills</span>; empty takes them out of
            any folder. Runs of a bench job move with the whole job. Files on disk stay where they
            are.
          </label>
          <input
            id="move-input"
            className="input mono"
            list="move-folders"
            // biome-ignore lint/a11y/noAutofocus: the dialog exists to take this input
            autoFocus
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void move();
            }}
          />
          <datalist id="move-folders">
            {known.map((f) => (
              <option key={f} value={f} />
            ))}
          </datalist>
          {err && <div className="errbox">{err}</div>}
        </div>
        <div className="dialog-f">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={Boolean(err) || busy}
            onClick={() => void move()}
          >
            {busy ? "Moving…" : target ? `Move to ${target}` : "Remove from folder"}
          </button>
        </div>
      </div>
    </div>
  );
}
