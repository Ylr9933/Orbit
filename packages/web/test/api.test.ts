import { afterEach, expect, it, vi } from "vitest";
import { api } from "../src/lib/api.ts";

afterEach(() => vi.unstubAllGlobals());

it("carries the consolidation preview digest through the Web API", async () => {
  const plan = {
    digest: "a".repeat(64),
    dryRun: true,
    adopted: [],
    reclassified: [],
    removedJobs: [],
    removedRuns: [],
    leftovers: [],
  };
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(plan)));
  vi.stubGlobal("fetch", fetch);
  const preview = await api.benchConsolidate("target", { sources: ["source"] });
  fetch.mockResolvedValue(new Response(JSON.stringify({ ...plan, dryRun: false })));
  await api.benchConsolidate("target", {
    sources: ["source"],
    dryRun: false,
    expect: preview.digest,
  });
  expect(JSON.parse(fetch.mock.calls[1]?.[1].body)).toEqual({
    sources: ["source"],
    dryRun: false,
    expect: plan.digest,
  });
});

it("loads every cursor page instead of silently capping the run list", async () => {
  const runs = Array.from({ length: 1125 }, (_, i) => ({ id: `run-${i}` }));
  const cursor = { id: "run-999", createdAt: "2026-10-16T00:00:00.000Z" };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ runs: runs.slice(0, 1000), next: cursor })),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ runs: runs.slice(1000), next: null })));
  vi.stubGlobal("fetch", fetch);
  expect(await api.allRuns()).toEqual(runs);
  expect(fetch).toHaveBeenCalledTimes(2);
  const url = new URL(fetch.mock.calls[1]?.[0], "http://orbit.test");
  expect(JSON.parse(url.searchParams.get("before") ?? "")).toEqual(cursor);
});
