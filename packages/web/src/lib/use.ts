import { useCallback, useEffect, useRef, useState } from "react";

export interface Async<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch on mount and whenever `deps` change; optionally poll every `pollMs` while `poll` is true.
 * Keeps the previous data while reloading so views don't flash.
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
  const reload = useCallback(() => setTick((t) => t + 1), []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: caller controls deps
  useEffect(() => {
    let live = true;
    setLoading(true);
    fnRef.current().then(
      (d) => {
        if (!live) return;
        setData(d);
        setError(null);
        setLoading(false);
      },
      (e: Error) => {
        if (!live) return;
        setError(e.message);
        setLoading(false);
      },
    );
    return () => {
      live = false;
    };
  }, [...deps, tick]);

  useEffect(() => {
    if (!opts.poll || !opts.pollMs) return;
    const t = setInterval(reload, opts.pollMs);
    return () => clearInterval(t);
  }, [opts.poll, opts.pollMs, reload]);

  return { data, error, loading, reload };
}
