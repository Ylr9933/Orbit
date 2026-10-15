import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { visiblePolling } from "./polling.ts";

export interface Async<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch on mount and whenever `deps` change; optionally poll every `pollMs` while `poll` is true.
 * The next poll is scheduled only after the current request settles, so a response slower than
 * the interval is still applied. Keeps the previous data while reloading so views don't flash.
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  opts: { pollMs?: number; poll?: boolean } = {},
): Async<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const optsRef = useRef(opts);
  optsRef.current = opts;
  const reload = useCallback(() => setTick((t) => t + 1), []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: caller controls deps
  useEffect(() => {
    let live = true;
    const polling = visiblePolling(reload, () => optsRef.current);
    setLoading(true);
    fnRef.current().then(
      (d) => {
        if (!live) return;
        setData(d);
        setError(null);
        setLoading(false);
        polling.settled();
      },
      (e: Error) => {
        if (!live) return;
        setError(e.message);
        setLoading(false);
        polling.settled();
      },
    );
    return () => {
      live = false;
      polling.dispose();
    };
  }, [...deps, tick]);

  // Polling switched on (or its interval changed) after the last request settled: restart it.
  const first = useRef(true);
  // biome-ignore lint/correctness/useExhaustiveDependencies: only reacts to the poll options
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (opts.poll && opts.pollMs && document.visibilityState !== "hidden") reload();
  }, [opts.poll, opts.pollMs]);

  return { data, error, loading, reload };
}

const subscribeVisibility = (changed: () => void) => {
  document.addEventListener("visibilitychange", changed);
  return () => document.removeEventListener("visibilitychange", changed);
};
export function usePageVisible(): boolean {
  return useSyncExternalStore(
    subscribeVisibility,
    () => document.visibilityState !== "hidden",
    () => true,
  );
}
