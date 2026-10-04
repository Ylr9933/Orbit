// A small Markdown renderer for reports produced by runs (headings, paragraphs, lists, tables, code,
// quotes, images, links, emphasis). It builds React elements, never HTML strings, so report text
// cannot inject markup. Relative image and link targets resolve to files of the same run; remote
// images are not loaded (shown as links).
import type React from "react";

type Resolve = (relPath: string) => string | null;

interface Props {
  text: string;
  /** Maps a path relative to the Markdown file to a URL, or null when it is not a run file. */
  resolve: Resolve;
}

const SAFE_URL = /^(https?:|mailto:)/i;

/** Normalize `a/./b/../c` and strip a leading `./`; null when it climbs out of the root. */
export function joinPath(dir: string, rel: string): string | null {
  const out: string[] = dir ? dir.split("/") : [];
  for (const part of rel.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") {
      if (!out.length) return null;
      out.pop();
    } else out.push(part);
  }
  return out.join("/");
}

/** Inline Markdown: code, images, links, bold, italic. */
function inline(text: string, resolve: Resolve, key = "i"): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re =
    /(`+)([\s\S]*?)\1|!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\s][^*]*)\*|(?<![\w])_([^_\s][^_]*)_(?![\w])/g;
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(re)) {
    const i = m.index ?? 0;
    if (i > last) out.push(text.slice(last, i));
    const k = `${key}-${n++}`;
    if (m[1]) out.push(<code key={k}>{m[2]}</code>);
    else if (m[4] !== undefined) {
      const src = m[4];
      const url = SAFE_URL.test(src) ? null : resolve(src);
      out.push(
        url ? (
          <img key={k} src={url} alt={m[3] ?? ""} loading="lazy" />
        ) : SAFE_URL.test(src) ? (
          <a key={k} href={src} target="_blank" rel="noreferrer noopener">
            [image: {m[3] || src}]
          </a>
        ) : (
          <span key={k} className="faint">
            [missing image: {src}]
          </span>
        ),
      );
    } else if (m[6] !== undefined) {
      const href = m[6];
      const url = SAFE_URL.test(href) ? href : href.startsWith("#") ? href : resolve(href);
      out.push(
        url ? (
          <a
            key={k}
            href={url}
            target={url.startsWith("#") ? undefined : "_blank"}
            rel="noreferrer noopener"
          >
            {inline(m[5] ?? "", resolve, k)}
          </a>
        ) : (
          <span key={k}>{m[5]}</span>
        ),
      );
    } else if (m[7] !== undefined || m[8] !== undefined)
      out.push(<strong key={k}>{inline(m[7] ?? m[8] ?? "", resolve, k)}</strong>);
    else out.push(<em key={k}>{inline(m[9] ?? m[10] ?? "", resolve, k)}</em>);
    last = i + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, "")
    .split(/(?<!\\)\|/)
    .map((c) => c.trim().replace(/\\\|/g, "|"));

export function Markdown({ text, resolve }: Props) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let n = 0;
  const key = () => `b${n++}`;
  const isBlockStart = (l: string) =>
    /^\s*(```|~~~|#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\|)/.test(l) || /^\s*([-*_])(\s*\1){2,}\s*$/.test(l);
  while (i < lines.length) {
    const line = lines[i] as string;
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = /^\s*(```|~~~)\s*([\w+-]*)/.exec(line);
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !(lines[i] as string).trim().startsWith(fence[1] as string))
        body.push(lines[i++] as string);
      i++;
      blocks.push(
        <pre key={key()} className="md-code" data-lang={fence[2] || undefined}>
          {body.join("\n")}
        </pre>,
      );
      continue;
    }
    const h = /^\s*(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (h) {
      const level = (h[1] as string).length;
      const Tag = `h${level}` as "h1";
      blocks.push(<Tag key={key()}>{inline(h[2] ?? "", resolve)}</Tag>);
      i++;
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      blocks.push(<hr key={key()} />);
      i++;
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i] as string))
        body.push((lines[i++] as string).replace(/^\s*>\s?/, ""));
      blocks.push(
        <blockquote key={key()}>
          <Markdown text={body.join("\n")} resolve={resolve} />
        </blockquote>,
      );
      continue;
    }
    if (/^\s*\|/.test(line) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] ?? "")) {
      const head = cells(line);
      const align = cells(lines[i + 1] as string).map((c) =>
        c.endsWith(":") ? (c.startsWith(":") ? "center" : "right") : undefined,
      );
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|/.test(lines[i] as string))
        rows.push(cells(lines[i++] as string));
      blocks.push(
        <div key={key()} className="md-table">
          <table>
            <thead>
              <tr>
                {head.map((c, j) => (
                  <th key={String(j)} style={{ textAlign: align[j] }}>
                    {inline(c, resolve)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={String(ri)}>
                  {head.map((_, j) => (
                    <td key={String(j)} style={{ textAlign: align[j] }}>
                      {inline(r[j] ?? "", resolve)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const li = /^\s*([-*+]|\d+[.)])\s+/.exec(line);
    if (li) {
      const ordered = /\d/.test(li[1] as string);
      const items: string[] = [];
      while (i < lines.length) {
        const l = lines[i] as string;
        const m = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(l);
        if (m) items.push(m[2] ?? "");
        else if (l.trim() && /^\s{2,}/.test(l) && items.length)
          items[items.length - 1] += ` ${l.trim()}`;
        else break;
        i++;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={key()}>
          {items.map((t, j) => (
            <li key={String(j)}>{inline(t, resolve)}</li>
          ))}
        </Tag>,
      );
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      (lines[i] as string).trim() &&
      !(para.length && isBlockStart(lines[i] as string))
    )
      para.push((lines[i++] as string).trim());
    blocks.push(<p key={key()}>{inline(para.join(" "), resolve)}</p>);
  }
  return <div className="md">{blocks}</div>;
}
