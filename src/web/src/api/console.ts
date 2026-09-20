import { useEffect, useState } from "react";

export interface Project {
  id?: string;
  source?: "legacy" | "workspace";
  workspace?: string | null;
  workspace_project_id?: string | null;
  binding_status?: string;
  task_mappings?: {
    key: string;
    identity: { task_id: string; revision: string } | null;
    resolved: boolean;
  }[];
  revision: number;
  name: string;
  goal: string;
  status: string;
  milestones: { title: string; done: boolean }[];
  run_ids: string[];
  task_keys: string[];
}
export interface Run {
  id: string;
  status: string;
  created_at: string;
}
export interface Task {
  key: string;
  task_id: string;
  mode?: string;
  error?: string;
  view?: unknown;
  evaluation?: string;
  resource_intent?: unknown;
}
export interface Snapshot {
  node_id: string;
  captured_at: string;
  cpu_logical_cores: number;
  cpu_utilization_percent: number | null;
  memory_total_bytes: number;
  memory_available_bytes: number;
  issues: string[];
  gpus: {
    device_id: string;
    index: number;
    name: string;
    memory_total_bytes: number;
    memory_free_bytes: number;
    utilization_percent: number | null;
  }[];
}
export interface Resources {
  latest: Snapshot | null;
  history: Snapshot[];
  stale: boolean;
  error: string | null;
}
export interface Attempt {
  id: string;
  status: string;
  evaluation_status: string | null;
  cleanup_complete: boolean | null;
  lease_released: boolean | null;
  coverage: unknown;
}
export interface TraceEvent {
  id: string;
  type: string;
  at: string;
  producer: string;
  text: string;
  payload: unknown;
  capture_status: string;
}
export interface Artifact {
  id: string;
  name: string;
  kind: string;
  size_bytes: number;
  media_type: string;
}
export interface Agent {
  provider: string;
  name: string;
  available: boolean | null;
  authenticated: boolean | null;
  version?: string;
  compatible?: boolean;
  capabilities: string[];
  issues: string[];
  checked_at: string;
}

export async function request<T>(
  token: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(`${response.status} · ${value.error ?? "请求失败"}`);
  return value as T;
}

export function useData<T>(token: string, path: string | null, interval = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState("");
  const [revision, setRevision] = useState(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies: revision explicitly requests a refresh.
  useEffect(() => {
    setData(undefined);
    setError("");
    setUpdated("");
    if (!path) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await request<T>(
          token,
          path as string,
          undefined,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setData(value);
          setError("");
          setUpdated(new Date().toLocaleTimeString());
        }
      } catch (reason) {
        if (!controller.signal.aborted) setError(String(reason));
      } finally {
        if (interval && !controller.signal.aborted)
          timer = setTimeout(load, interval);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, path, interval, revision]);
  return { data, error, updated, refresh: () => setRevision((n) => n + 1) };
}

export const pretty = (value: unknown) => JSON.stringify(value, null, 2);
export const bytes = (value: number) => `${(value / 1024 ** 3).toFixed(1)} GiB`;
export const percent = (value: number | null) =>
  value === null ? "未知" : `${value.toFixed(1)}%`;
export const known = (value: boolean | null | undefined) =>
  value == null ? "未知" : value ? "是" : "否";
