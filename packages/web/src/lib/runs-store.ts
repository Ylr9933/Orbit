// Live run list: one initial fetch, then server-sent `run` events upsert individual runs.
import { useSyncExternalStore } from "react";
import { api, authState, type Run } from "./api.ts";
import { notifyTransition } from "./browser-notify.ts";

interface State {
  runs: Map<string, Run>;
  loaded: boolean;
  connected: boolean;
  error: string | null;
  version: number;
}

let state: State = { runs: new Map(), loaded: false, connected: false, error: null, version: 0 };
const listeners = new Set<() => void>();
const emit = (patch: Partial<State>) => {
  state = { ...state, ...patch, version: state.version + 1 };
  for (const l of listeners) l();
};

let started = false;
let source: EventSource | null = null;
let opened = false;
let retry: ReturnType<typeof setTimeout> | undefined;
/** Runs received from the stream while a full load is in flight; they are newer than its snapshot. */
let during: Map<string, Run | null> | null = null;
let loading: Promise<void> | null = null;
let reloadAgain = false;

function load(): Promise<void> {
  if (loading) {
    reloadAgain = true;
    return loading;
  }
  loading = (async () => {
    do {
      reloadAgain = false;
      await loadAll();
    } while (reloadAgain);
  })().finally(() => {
    loading = null;
  });
  return loading;
}

async function loadAll() {
  during = new Map();
  try {
    const runs = new Map((await api.allRuns()).map((r) => [r.id, r]));
    for (const [id, r] of during) {
      if (r) runs.set(id, r);
      else runs.delete(id);
    }
    emit({ runs, loaded: true, error: null });
  } catch (e) {
    emit({ loaded: true, error: (e as Error).message });
  } finally {
    during = null;
  }
}

function connect() {
  clearTimeout(retry);
  source?.close();
  const es = new EventSource("/api/v1/stream");
  source = es;
  es.addEventListener("open", () => {
    // Reload on reconnect so nothing missed during a disconnect is lost.
    if (opened && !state.connected) void load();
    opened = true;
    emit({ connected: true });
  });
  es.addEventListener("run", (ev) => {
    const run = JSON.parse((ev as MessageEvent<string>).data) as Run;
    notifyTransition(state.runs.get(run.id), run, state.runs.values());
    upsertRun(run);
  });
  es.addEventListener("deleted", (ev) => {
    const { ids } = JSON.parse((ev as MessageEvent<string>).data) as { ids: string[] };
    removeRuns(ids);
  });
  es.addEventListener("error", () => {
    if (state.connected) emit({ connected: false });
    // The browser retries on its own unless the stream failed outright (e.g. 401): then probe the
    // API (which records 401 in authState) and reconnect by hand.
    if (es.readyState !== EventSource.CLOSED || source !== es) return;
    retry = setTimeout(() => {
      api.health().then(
        () => connect(),
        () => {
          if (!authState.unauthorized) connect();
        },
      );
    }, 3000);
  });
}

export function startRunsStore() {
  if (started) return;
  started = true;
  void load();
  connect();
}

export function removeRuns(ids: string[]) {
  const runs = new Map(state.runs);
  for (const id of ids) {
    runs.delete(id);
    during?.set(id, null);
  }
  emit({ runs });
}

export function upsertRun(run: Run) {
  during?.set(run.id, run);
  const runs = new Map(state.runs);
  runs.set(run.id, run);
  emit({ runs });
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
const snap = () => state;

export function useRunsState(): State {
  return useSyncExternalStore(subscribe, snap);
}

/** Runs sorted newest first. */
export function useRuns(): Run[] {
  const s = useRunsState();
  return sortedCache(s);
}

let cache: { version: number; list: Run[] } = { version: -1, list: [] };
function sortedCache(s: State): Run[] {
  if (cache.version !== s.version)
    cache = {
      version: s.version,
      list: [...s.runs.values()].sort((a, b) =>
        a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0,
      ),
    };
  return cache.list;
}

export function useRun(id: string): Run | undefined {
  return useRunsState().runs.get(id);
}
