import { Command } from "commander";
import { expect, it, vi } from "vitest";
import { registerBench } from "../src/cli/bench.ts";
import { OrbitClient } from "../src/client/index.ts";

it("passes the confirmed preview digest when the CLI applies consolidation", async () => {
  const client = new OrbitClient({ url: "http://unused", token: "fixture", pid: 0 });
  const plan = {
    digest: "a".repeat(64),
    dryRun: true,
    adopted: [],
    reclassified: [],
    removedJobs: [],
    removedRuns: [],
    leftovers: [],
  };
  const call = vi.spyOn(client, "benchConsolidate").mockResolvedValue(plan);
  const program = new Command();
  registerBench(program, async () => client, vi.fn());
  await program.parseAsync(["bench", "consolidate", "target", "source", "--apply", "--yes"], {
    from: "user",
  });
  expect(call).toHaveBeenCalledTimes(2);
  expect(call.mock.calls[0]?.[1]).toMatchObject({ dryRun: true, sources: ["source"] });
  expect(call.mock.calls[1]?.[1]).toMatchObject({ dryRun: false, expect: plan.digest });
});
