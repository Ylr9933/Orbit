import type { Run } from "@zjunlp/orbit/contracts";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("react", () => ({
  useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot(),
}));
vi.mock("../src/lib/browser-notify.ts", () => ({ notifyTransition: vi.fn() }));
class Source extends EventTarget {
  static CLOSED = 2;
  static latest: Source;
  readyState = 1;
  constructor() {
    super();
    Source.latest = this;
  }
  close() {}
  send(type: string, data: unknown) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
}
beforeEach(() => vi.resetModules());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const run = (id: string, state = "running") => ({ id, state, createdAt: id }) as Run;

it("preserves SSE upserts and deletion tombstones across full loads and reconnects", async () => {
  vi.stubGlobal("EventSource", Source);
  const { api } = await import("../src/lib/api.ts");
  const { promise, resolve } = Promise.withResolvers<Run[]>();
  const fetch = vi.spyOn(api, "allRuns").mockReturnValueOnce(promise);
  const { startRunsStore, useRunsState } = await import("../src/lib/runs-store.ts");
  startRunsStore();
  const source = Source.latest;
  source.dispatchEvent(new Event("open"));
  source.send("run", run("old", "succeeded"));
  source.send("run", run("new"));
  source.send("deleted", { ids: ["deleted"] });
  resolve([run("old"), run("deleted"), run("historical")]);
  await vi.waitFor(() => expect(useRunsState().loaded).toBe(true));
  expect([...useRunsState().runs.keys()]).toEqual(["old", "historical", "new"]);
  expect(useRunsState().runs.get("old")?.state).toBe("succeeded");
  fetch.mockResolvedValueOnce([run("after-reconnect")]);
  source.dispatchEvent(new Event("error"));
  source.dispatchEvent(new Event("open"));
  await vi.waitFor(() => expect(useRunsState().runs.has("after-reconnect")).toBe(true));
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("restarts pagination after a reconnect during a load to recover missed changes", async () => {
  vi.stubGlobal("EventSource", Source);
  const { api } = await import("../src/lib/api.ts");
  const first = Promise.withResolvers<Run[]>();
  const second = Promise.withResolvers<Run[]>();
  const fetch = vi
    .spyOn(api, "allRuns")
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  const { startRunsStore, useRunsState } = await import("../src/lib/runs-store.ts");
  startRunsStore();
  const source = Source.latest;
  source.dispatchEvent(new Event("open"));
  source.dispatchEvent(new Event("error"));
  source.dispatchEvent(new Event("open"));
  expect(fetch).toHaveBeenCalledTimes(1);
  first.resolve([run("updated-while-disconnected"), run("deleted-while-disconnected")]);
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  source.send("run", run("new-after-reconnect"));
  second.resolve([run("updated-while-disconnected", "succeeded")]);
  await vi.waitFor(() =>
    expect(useRunsState().runs.get("updated-while-disconnected")?.state).toBe("succeeded"),
  );
  expect([...useRunsState().runs.keys()]).toEqual([
    "updated-while-disconnected",
    "new-after-reconnect",
  ]);
});
