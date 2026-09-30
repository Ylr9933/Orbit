import { useEffect, useState } from "react";
import type { RunState } from "../lib/api.ts";
import { STATE_LABEL } from "../lib/format.ts";
import { onLinkClick } from "../lib/router.ts";
import { IconBan, IconCheck, IconCircle, IconCopy, IconHelp, IconLoader, IconX } from "./icons.tsx";

export function Link(props: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  return <a {...props} onClick={props.onClick ?? onLinkClick} />;
}

export const stateColor = (s: RunState) => `var(--st-${s})`;

export function StateIcon({ state, size = 14 }: { state: RunState; size?: number }) {
  const style = { color: stateColor(state), flex: "none" } as const;
  switch (state) {
    case "queued":
      return <IconCircle size={size} style={style} strokeDasharray="3 3" />;
    case "starting":
      return <IconLoader size={size} style={style} className="spin" />;
    case "running":
      return (
        <span
          className="dot pulse"
          style={{ "--c": stateColor(state), margin: 3 } as React.CSSProperties}
        />
      );
    case "succeeded":
      return <IconCheck size={size} style={style} strokeWidth={2.6} />;
    case "failed":
      return <IconX size={size} style={style} strokeWidth={2.6} />;
    case "cancelled":
      return <IconBan size={size} style={style} />;
    case "lost":
      return <IconHelp size={size} style={style} />;
  }
}

export function StateBadge({ state, large }: { state: RunState; large?: boolean }) {
  return (
    <span
      className={`badge${large ? " lg" : ""}`}
      style={{ "--c": stateColor(state) } as React.CSSProperties}
    >
      <StateIcon state={state} size={large ? 14 : 12} />
      {STATE_LABEL[state]}
    </span>
  );
}

let toastSet: ((s: string | null) => void) | null = null;
export function toast(msg: string) {
  toastSet?.(msg);
}
export function Toaster() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    toastSet = setMsg;
    return () => {
      toastSet = null;
    };
  }, []);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 1800);
    return () => clearTimeout(t);
  }, [msg]);
  return msg ? <div className="toast">{msg}</div> : null;
}

export async function copy(text: string, what = "Copied") {
  try {
    await navigator.clipboard.writeText(text);
    toast(what);
  } catch {
    toast("Copy failed — clipboard needs a secure context");
  }
}

export function CopyButton({
  text,
  label,
  title,
}: {
  text: string;
  label?: string;
  title?: string;
}) {
  return (
    <button
      type="button"
      className={`btn ghost sm${label ? "" : " icon"}`}
      title={title ?? "Copy"}
      onClick={(e) => {
        e.stopPropagation();
        void copy(text, `Copied ${label ?? ""}`.trim());
      }}
    >
      <IconCopy size={13} />
      {label}
    </button>
  );
}

export function Empty({
  title,
  children,
  icon,
}: {
  title: string;
  children?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="empty">
      {icon}
      <h3>{title}</h3>
      {children && <div>{children}</div>}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <div className="empty">
      <IconLoader className="spin" />
      <div>{what}…</div>
    </div>
  );
}

/** Re-render every `ms` so live durations tick. */
export function useNow(ms = 1000, enabled = true): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!enabled) return;
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms, enabled]);
  return now;
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd>{children}</kbd>;
}

/** Metric/param chip list: `k=v`. */
export function Params({ params }: { params: Record<string, string> }) {
  const e = Object.entries(params);
  if (!e.length) return null;
  return (
    <span className="params">
      {e.map(([k, v]) => (
        <span key={k} className="param">
          <i>{k}=</i>
          {v}
        </span>
      ))}
    </span>
  );
}
