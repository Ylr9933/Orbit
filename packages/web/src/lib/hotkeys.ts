import { useEffect, useRef } from "react";

export type Handler = (e: KeyboardEvent) => void;

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

/**
 * Register single-key and `g x` sequence shortcuts while the component is mounted.
 * Keys: "j", "shift+N", "mod+k", "g r", "Escape", "/". Ignored while typing unless the key is
 * Escape or uses mod.
 */
export function useHotkeys(map: Record<string, Handler>, deps: unknown[] = []) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    let prefix: string | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (isTyping(e.target) && e.key !== "Escape" && !mod) return;
      if (e.altKey) return;
      let key = e.key.length === 1 ? e.key : e.key;
      if (mod) key = `mod+${key.toLowerCase()}`;
      else if (e.shiftKey && key.length === 1 && /[a-z]/i.test(key))
        key = `shift+${key.toUpperCase()}`;
      const combo = prefix ? `${prefix} ${key}` : key;
      const h = ref.current[combo];
      if (h) {
        e.preventDefault();
        prefix = null;
        h(e);
        return;
      }
      if (!prefix && !mod && Object.keys(ref.current).some((k) => k.startsWith(`${key} `))) {
        prefix = key;
        clearTimeout(timer);
        timer = setTimeout(() => {
          prefix = null;
        }, 900);
        return;
      }
      prefix = null;
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearTimeout(timer);
    };
    // biome-ignore lint/correctness/useExhaustiveDependencies: handlers are read through the ref
  }, deps);
}
