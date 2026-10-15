// Real HTTP handlers with an explicit in-memory run event source; no daemon or executor.
import { EventEmitter, getEventListeners } from "node:events";
import { afterEach, expect, it, vi } from "vitest";
import { Run } from "../src/contracts/index.ts";
import { type AppDeps, createApp } from "../src/daemon/app.ts";
import type { RunService } from "../src/runs/service.ts";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function fixture() {
  vi.useFakeTimers();
  const run = Run.parse({
    id: "run-0",
    spec: { backend: "process", command: ["true"] },
    state: "running",
    reason: null,
    exitCode: null,
    node: "fixture",
    image: null,
    containerId: null,
    lease: null,
    code: null,
    cleanup: "pending",
    note: "",
    createdAt: "2026-10-16T00:00:00Z",
    startedAt: null,
    endedAt: null,
  });
  const records = new Map(
    Array.from({ length: 4 }, (_, i) => [`run-${i}`, { ...run, id: `run-${i}` }]),
  );
  const source = Object.assign(new EventEmitter(), { get: vi.fn((id: string) => records.get(id)) });
  const app = createApp({ token: "fixture", runs: source as unknown as RunService } as AppDeps);
  const request = (path: string, aborted = false) => {
    const controller = new AbortController();
    if (aborted) controller.abort();
    const req = new Request(`http://orbit.test/api/v1${path}`, {
      headers: { authorization: "Bearer fixture" },
      signal: controller.signal,
    });
    return { controller, req, response: Promise.resolve(app.fetch(req)) };
  };
  return { run, records, source, request };
}

it("dispatches many waiters by run id and cleans up completion, abort and timeout", async () => {
  const f = fixture();
  const pending = Array.from({ length: 80 }, (_, i) => f.request(`/runs/run-${i % 4}/wait`));
  expect(f.source.listenerCount("change")).toBe(1);
  expect(vi.getTimerCount()).toBe(80);
  const first = pending[0];
  if (!first) throw new Error("waiter fixture missing");
  const remove = vi.spyOn(first.req.signal, "removeEventListener");
  f.source.emit("change", { run: { ...f.run, state: "succeeded" } });
  f.source.emit("change", {
    run: { ...f.run, id: "unrelated", state: "succeeded", cleanup: "done" },
  });
  expect(vi.getTimerCount()).toBe(80);
  f.source.emit("change", { run: { ...f.run, state: "succeeded", cleanup: "done" } });
  for (const p of pending.filter((_, i) => i % 4 === 0)) {
    expect(await (await p.response).clone().json()).toMatchObject({
      state: "succeeded",
      cleanup: "done",
    });
    expect(getEventListeners(p.req.signal, "abort")).toHaveLength(0);
  }
  expect(vi.getTimerCount()).toBe(60);
  for (const p of pending.filter((_, i) => i % 4 === 1)) p.controller.abort();
  expect(vi.getTimerCount()).toBe(40);
  await vi.advanceTimersByTimeAsync(30_000);
  const replies = await Promise.all(
    pending.map(async (p) => Run.parse(await (await p.response).json())),
  );
  expect(replies.filter((r) => r.state === "succeeded")).toHaveLength(20);
  expect(replies.filter((r) => r.state === "running")).toHaveLength(60);
  expect(vi.getTimerCount()).toBe(0);
  for (const p of pending) expect(getEventListeners(p.req.signal, "abort")).toHaveLength(0);
  expect(remove).toHaveBeenCalledTimes(1);
  f.source.emit("change", { run: { ...f.run, state: "succeeded", cleanup: "done" } });
  expect(remove).toHaveBeenCalledTimes(1);
  expect(f.source.listenerCount("change")).toBe(1);
});

it("shares listeners across SSE subscribers and removes subscriptions on body cancellation and abort", async () => {
  const f = fixture();
  const pending = Array.from({ length: 30 }, () => f.request("/stream"));
  const responses = await Promise.all(pending.map((p) => p.response));
  const readers = responses.map((r) => {
    if (!r.body) throw new Error("SSE body missing");
    return r.body.getReader();
  });
  expect(f.source.listenerCount("change")).toBe(1);
  expect(f.source.listenerCount("deleted")).toBe(1);
  expect(vi.getTimerCount()).toBe(30);
  f.source.emit("change", { run: f.run });
  for (const reader of readers) {
    const text = new TextDecoder().decode((await reader.read()).value);
    expect(text).toContain("event: run\n");
    expect(text).toContain(JSON.stringify(f.run));
  }
  await Promise.all(readers.slice(0, 15).map((reader) => reader.cancel()));
  expect(vi.getTimerCount()).toBe(15);
  f.source.emit("deleted", [f.run.id]);
  for (const reader of readers.slice(15))
    expect(new TextDecoder().decode((await reader.read()).value)).toContain(
      'event: deleted\ndata: {"ids":["run-0"]}',
    );
  for (const p of pending.slice(15)) p.controller.abort();
  for (const reader of readers.slice(15)) expect((await reader.read()).done).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
  for (const p of pending) expect(getEventListeners(p.req.signal, "abort")).toHaveLength(0);
});

it("does not retain already aborted requests or waits for settled runs", async () => {
  const f = fixture();
  const wait = f.request(`/runs/${f.run.id}/wait`, true);
  expect(await (await wait.response).json()).toMatchObject({ state: "running" });
  const stream = f.request("/stream", true);
  expect(await (await stream.response).text()).toBe("");
  f.records.set(f.run.id, { ...f.run, state: "failed", cleanup: "failed" });
  const settled = f.request(`/runs/${f.run.id}/wait`);
  expect(await (await settled.response).json()).toMatchObject({
    state: "failed",
    cleanup: "failed",
  });
  expect(vi.getTimerCount()).toBe(0);
  for (const p of [wait, stream, settled])
    expect(getEventListeners(p.req.signal, "abort")).toHaveLength(0);
});
