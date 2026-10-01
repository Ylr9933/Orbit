import { useEffect, useRef } from "react";

export type Handler = (e: KeyboardEvent) => void;

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

/** Enter on a focused control activates that control, not a page shortcut. */
const isControl = (t: EventTarget | null) =>
  t instanceof HTMLElement && t.closest("button, a[href], summary, [role=button]") !== null;

// One window listener for every mounted `useHotkeys`, so a `g x` sequence has a single prefix
// state and its second key never also fires a plain shortcut registered elsewhere.
const maps = new Set<{ current: Record<string, Handler> }>();
let prefix: string | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;

function onKey(e: KeyboardEvent) {
  const mod = e.metaKey || e.ctrlKey;
  if (isTyping(e.target) && e.key !== "Escape" && !mod) return;
  if (e.altKey) return;
  if (e.key === "Enter" && isControl(e.target)) return;
  let key = e.key;
  if (mod) key = `mod+${key.toLowerCase()}`;
  else if (e.shiftKey && key.length === 1 && /[a-z]/i.test(key)) key = `shift+${key.toUpperCase()}`;
  const combo = prefix ? `${prefix} ${key}` : key;
  const hadPrefix = prefix !== null;
  prefix = null;
  clearTimeout(timer);
  const handlers = [...maps].map((m) => m.current[combo]).filter((h): h is Handler => !!h);
  if (handlers.length) {
    e.preventDefault();
    for (const h of handlers) h(e);
    return;
  }
  if (hadPrefix || mod) return;
  if ([...maps].some((m) => Object.keys(m.current).some((k) => k.startsWith(`${key} `)))) {
    prefix = key;
    timer = setTimeout(() => {
      prefix = null;
    }, 900);
  }
}

/**
 * Register single-key and `g x` sequence shortcuts while the component is mounted.
 * Keys: "j", "shift+N", "mod+k", "g r", "Escape", "/". Ignored while typing unless the key is
 * Escape or uses mod; Enter is left to a focused button or link.
 */
export function useHotkeys(map: Record<string, Handler>) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (maps.size === 0) window.addEventListener("keydown", onKey);
    maps.add(ref);
    return () => {
      maps.delete(ref);
      if (maps.size === 0) {
        window.removeEventListener("keydown", onKey);
        prefix = null;
        clearTimeout(timer);
      }
    };
  }, []);
}

/** True while a modal overlay (palette, help) is open: page shortcuts like Escape defer to it. */
export const overlayOpen = () => document.querySelector(".overlay") !== null;
