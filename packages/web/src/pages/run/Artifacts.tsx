import { useEffect, useMemo, useState } from "react";
import {
  IconDownload,
  IconExternal,
  IconFile,
  IconFolder,
  IconImage,
} from "../../components/icons.tsx";
import { Empty, Loading } from "../../components/ui.tsx";
import { type Artifacts, fileUrl, type Run } from "../../lib/api.ts";
import { ago, bytes, isActive } from "../../lib/format.ts";
import { setHash, useLocation } from "../../lib/router.ts";

const IMG = /\.(png|jpe?g|gif|svg|webp)$/i;
const TEXT = /\.(txt|log|json|jsonl|csv|tsv|md|py|sh|ya?ml|toml|cfg|ini|out|err|html|xml)$/i;
const MAX_PREVIEW = 2 * 1024 * 1024;

export function ArtifactsTab({ run, artifacts }: { run: Run; artifacts: Artifacts | undefined }) {
  const loc = useLocation();
  const files = artifacts?.files ?? [];
  const sel =
    decodeURIComponent(loc.hash) ||
    files.find((f) => IMG.test(f.path) || /result|summary|metrics/i.test(f.path))?.path ||
    files[0]?.path;
  const file = files.find((f) => f.path === sel);

  const tree = useMemo(() => {
    const rows: { path: string; depth: number; dir: boolean; name: string }[] = [];
    const seen = new Set<string>();
    for (const f of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
      const parts = f.path.split("/");
      for (let i = 0; i < parts.length - 1; i++) {
        const d = parts.slice(0, i + 1).join("/");
        if (!seen.has(d)) {
          seen.add(d);
          rows.push({ path: d, depth: i, dir: true, name: parts[i] as string });
        }
      }
      rows.push({
        path: f.path,
        depth: parts.length - 1,
        dir: false,
        name: parts[parts.length - 1] as string,
      });
    }
    return rows;
  }, [files]);

  if (!artifacts) return <Loading what="Loading artifacts" />;
  if (!files.length)
    return (
      <Empty
        title={isActive(run.state) ? "No outputs yet" : "No outputs"}
        icon={<IconFolder size={30} />}
      >
        <p>
          Files written to <code>$ORBIT_OUTPUT</code> (<code>/orbit/output</code>) inside the
          container are kept here after the run.
        </p>
      </Empty>
    );
  const total = files.reduce((a, f) => a + f.bytes, 0);
  return (
    <div className="split-pane">
      <div className="sidetree">
        <div className="faint" style={{ padding: "4px 8px 8px", fontSize: 12 }}>
          {files.length} files · {bytes(total)}
          {artifacts.truncated && " (list truncated)"}
        </div>
        {tree.map((r) =>
          r.dir ? (
            <div
              key={`d:${r.path}`}
              className="f"
              style={{ paddingLeft: 8 + r.depth * 14, cursor: "default" }}
            >
              <IconFolder size={13} /> {r.name}
            </div>
          ) : (
            <div
              key={r.path}
              className={`f${r.path === sel ? " on" : ""}`}
              style={{ paddingLeft: 8 + r.depth * 14 }}
              onClick={() => setHash(encodeURIComponent(r.path))}
            >
              {IMG.test(r.name) ? <IconImage size={13} /> : <IconFile size={13} />}
              <span className="grow ellipsis">{r.name}</span>
              <span className="faint num" style={{ fontSize: 11 }}>
                {bytes(files.find((f) => f.path === r.path)?.bytes ?? 0)}
              </span>
            </div>
          ),
        )}
      </div>
      <div className="preview">
        {file ? (
          <>
            <div className="toolbar">
              <span className="mono">{file.path}</span>
              <span className="faint">
                {bytes(file.bytes)} · modified {ago(file.mtime)}
              </span>
              <div className="spacer" />
              <a
                className="btn sm"
                href={fileUrl(run.id, file.path)}
                target="_blank"
                rel="noreferrer"
              >
                <IconExternal size={13} /> Open
              </a>
              <a className="btn sm" href={fileUrl(run.id, file.path, true)}>
                <IconDownload size={13} /> Download
              </a>
            </div>
            <Preview runId={run.id} path={file.path} size={file.bytes} />
          </>
        ) : (
          <Empty title="Select a file" />
        )}
      </div>
    </div>
  );
}

function Preview({ runId, path, size }: { runId: string; path: string; size: number }) {
  const [text, setText] = useState<string | null>(null);
  const isText = TEXT.test(path) || !/\.[a-z0-9]+$/i.test(path);
  useEffect(() => {
    setText(null);
    if (!isText || size > MAX_PREVIEW || IMG.test(path)) return;
    let live = true;
    fetch(fileUrl(runId, path))
      .then((r) => r.text())
      .then((t) => live && setText(t));
    return () => {
      live = false;
    };
  }, [runId, path, size, isText]);

  if (IMG.test(path)) return <img src={fileUrl(runId, path)} alt={path} />;
  if (!isText) return <Empty title="No preview for this file type">Use Open or Download.</Empty>;
  if (size > MAX_PREVIEW)
    return <Empty title="File too large to preview">{bytes(size)} — use Download.</Empty>;
  if (text === null) return <Loading />;
  if (/\.json$/i.test(path)) {
    try {
      return <pre>{JSON.stringify(JSON.parse(text), null, 2)}</pre>;
    } catch {
      /* fall through */
    }
  }
  if (/\.(csv|tsv)$/i.test(path))
    return <Csv text={text} sep={/\.tsv$/i.test(path) ? "\t" : ","} />;
  return <pre>{text}</pre>;
}

function Csv({ text, sep }: { text: string; sep: string }) {
  const rows = text
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(0, 1001)
    .map((l) => l.split(sep));
  const [head, ...body] = rows;
  return (
    <div style={{ overflow: "auto" }}>
      <table className="table compact csv">
        <thead>
          <tr>
            {head?.map((h, i) => (
              <th key={String(i)}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={String(i)}>
              {r.map((c, j) => (
                <td key={String(j)}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
