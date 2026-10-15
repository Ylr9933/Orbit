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
