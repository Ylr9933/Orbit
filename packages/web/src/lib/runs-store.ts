// Live run list: one initial fetch, then server-sent `run` events upsert individual runs.
import { useSyncExternalStore } from "react";
import { api, authState, type Run } from "./api.ts";

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

async function load() {
  try {
    const runs = await api.runs();
    emit({ runs: new Map(runs.map((r) => [r.id, r])), loaded: true, error: null });
  } catch (e) {
    emit({ loaded: true, error: (e as Error).message });
  }
}

function connect() {
  source?.close();
  source = new EventSource("/api/v1/stream");
  source.addEventListener("open", () => {
    // Reload on (re)connect so nothing missed during a disconnect is lost.
    if (!state.connected) void load();
    emit({ connected: true });
  });
  source.addEventListener("run", (ev) => {
    const run = JSON.parse((ev as MessageEvent<string>).data) as Run;
    const runs = new Map(state.runs);
    runs.set(run.id, run);
    emit({ runs });
  });
  source.addEventListener("error", () => {
    emit({ connected: false });
    if (authState.unauthorized) source?.close();
  });
}

export function startRunsStore() {
  if (started) return;
  started = true;
  void load();
  connect();
}

export function upsertRun(run: Run) {
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
      list: [...s.runs.values()].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)),
    };
  return cache.list;
}

export function useRun(id: string): Run | undefined {
  return useRunsState().runs.get(id);
}
