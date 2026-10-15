// In-memory store and HTTP handlers, with an explicit run-service facade; no daemon or executor.
import { EventEmitter } from "node:events";
import { afterEach, expect, it, vi } from "vitest";
import { OrbitClient } from "../src/client/index.ts";
import { Run } from "../src/contracts/index.ts";
import { type AppDeps, createApp } from "../src/daemon/app.ts";
import type { RunService } from "../src/runs/service.ts";
import { type RunFilter, Store } from "../src/store/index.ts";

const stores: Store[] = [];
afterEach(() => {
  vi.unstubAllGlobals();
  for (const store of stores.splice(0)) store.close();
});
function fixture(count: number) {
  const store = new Store(":memory:");
  stores.push(store);
  const at = "2026-10-16T00:00:00.000Z";
  const make = (id: string) =>
    Run.parse({
      id,
      spec: { backend: "process", command: ["true"], group: "fixture" },
      folder: "parent/child",
      state: "succeeded",
      reason: null,
      exitCode: 0,
      node: "fixture",
      image: null,
      containerId: null,
      lease: null,
      code: null,
      cleanup: "done",
      note: "",
      createdAt: at,
      startedAt: at,
      endedAt: at,
    });
  store.tx(() => {
    for (let i = 0; i < count; i++) store.putRun(make(`run-${String(i).padStart(4, "0")}`));
  });
  const runs = Object.assign(new EventEmitter(), {
    storeList: (filter: RunFilter) => store.listRuns(filter),
  }) as unknown as RunService;
  const token = "fixture-token";
  const app = createApp({ runs, token, webDir: null, startedAt: at } as AppDeps);
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => app.request(url, init));
  const client = new OrbitClient({ url: "http://orbit.test", token, pid: 0 });
  return { store, app, client, token, make };
}

it("loads more than 1000 runs without omissions when creation times tie and the cursor row is deleted", async () => {
  const { client, store, make } = fixture(1125);
  const first = await client.listPage({ limit: 1000 });
  expect(first.runs).toHaveLength(1000);
  const cursor = first.next;
  if (!cursor) throw new Error("missing cursor");
  store.deleteRuns([cursor.id]);
  store.putRun({ ...make("new"), createdAt: "2026-10-17T00:00:00.000Z" });
  const second = await client.listPage({ limit: 1000, before: cursor });
  expect(second.runs).toHaveLength(125);
  expect(second.next).toBeNull();
  const ids = [...first.runs, ...second.runs].map((r) => r.id);
  expect(new Set(ids).size).toBe(1125);
  expect(ids).not.toContain("new");
  expect(await client.list({ limit: 1000, before: cursor })).toEqual(second.runs);
});

it("combines cursors with state, folder and group filters and ends at an empty page", async () => {
  const { client } = fixture(4);
  const query = { limit: 2, states: ["succeeded" as const], group: "fixture", folder: "parent" };
  const first = await client.listPage(query);
  const second = await client.listPage({ ...query, before: first.next ?? undefined });
  const last = await client.listPage({ ...query, before: second.next ?? undefined });
  expect([...first.runs, ...second.runs].map((r) => r.id)).toEqual([
    "run-0003",
    "run-0002",
    "run-0001",
    "run-0000",
  ]);
  expect(last).toEqual({ runs: [], next: null });
  expect(await client.list({ ...query, folder: "other", before: first.next ?? undefined })).toEqual(
    [],
  );
});

it.each(["bad-json", "null", "{}", '{"createdAt":"","id":"x"}', '{"createdAt":"a","id":1}'])(
  "rejects malformed cursor %s",
  async (before) => {
    const { app, token } = fixture(0);
    const res = await app.request(`/api/v1/runs?before=${encodeURIComponent(before)}`, {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(res.status).toBe(400);
  },
);
