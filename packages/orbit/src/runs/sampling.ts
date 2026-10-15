import { isTerminal, type Run } from "../contracts/index.ts";
import * as docker from "../executor/docker.ts";
import type { RunContext } from "./context.ts";
import { cgroupOf, type Targets, UsageSampler } from "./usage.ts";

type Context = Pick<RunContext, "cgroupDirs" | "deps" | "samplers" | "store">;

export async function containerCgroups(ctx: Context, ids: string[]): Promise<string[]> {
  const out: string[] = [];
  for (const c of ids) {
    let dir = ctx.cgroupDirs.get(c);
    if (!dir) {
      const st = await docker.inspectContainer(c).catch(() => null);
      const found = st?.pid ? cgroupOf(st.pid) : null;
      if (!found) continue;
      dir = found;
      ctx.cgroupDirs.set(c, dir);
    }
    out.push(dir);
  }
  return out;
}

export function startUsage(ctx: Context, id: string, targets: () => Promise<Targets>): void {
  if (ctx.samplers.has(id)) return;
  const prev = ctx.store.getRun(id)?.usage ?? null;
  const sampler = new UsageSampler(
    prev,
    targets,
    (usage) => {
      const r = ctx.store.getRun(id);
      if (!r || isTerminal(r.state)) return;
      r.usage = { ...usage };
      ctx.store.putRun(r);
    },
    ctx.deps.usageMs ?? 5000,
  );
  ctx.samplers.set(id, sampler);
}

export async function stopUsage(ctx: Context, run: Run, oomKilled: boolean): Promise<void> {
  const sampler = ctx.samplers.get(run.id);
  ctx.samplers.delete(run.id);
  if (!sampler) return;
  const usage = await sampler.stop();
  // Too short to be seen (or nothing readable): no figures rather than zeros.
  if (sampler.meter.readings === 0 && !run.usage && !oomKilled) return;
  run.usage = { ...usage, oomKilled };
  if (oomKilled) run.usage.oomKills = Math.max(1, run.usage.oomKills);
  const u = run.usage;
  ctx.store.addEvent(
    run.id,
    "usage",
    `peak memory ${u.peakMemGB} GB of ${run.spec.resources.memGB} GB` +
      `, CPU peak ${u.peakCpus} / mean ${u.meanCpus} of ${run.spec.resources.cpus}` +
      (u.peakGpuMemGB !== null ? `, GPU memory peak ${u.peakGpuMemGB} GB` : "") +
      (u.oomKills ? `, ${u.oomKills} process(es) killed for memory` : ""),
  );
}
