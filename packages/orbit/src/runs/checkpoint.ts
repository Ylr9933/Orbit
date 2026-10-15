import { existsSync, mkdirSync, rmSync } from "node:fs";
import { cp } from "node:fs/promises";
import { join } from "node:path";
import type { Run, RunCheckpoint, RunSpecInput } from "../contracts/index.ts";
import * as docker from "../executor/docker.ts";
import { finishHarness, resumeAgentCommand } from "../harness/index.ts";
import { nowIso } from "../lib/ids.ts";
import { dirBytes } from "../records/index.ts";
import { loadRunAgentTranscript } from "../sessions/index.ts";
import type { RunContext } from "./context.ts";
import { UserError } from "./errors.ts";

type Context = Pick<RunContext, "dirs" | "homeLabel" | "mustGet" | "save" | "redactor">;

export const checkpointTag = (id: string) => `orbit-checkpoint/${id}:saved`;
export const checkpointDir = (ctx: Pick<Context, "dirs">, id: string) =>
  join(ctx.dirs(id).root, "checkpoint");

export async function capture(
  ctx: Context,
  id: string,
  containerId: string,
  executionMin?: number,
): Promise<void> {
  const run = ctx.mustGet(id);
  if (!run.spec.checkpoint || run.checkpoint) return;
  const root = checkpointDir(ctx, id);
  const tag = checkpointTag(id);
  let committed = false;
  let checkpoint: RunCheckpoint;
  try {
    const status = await docker.inspectContainer(containerId);
    if (!status || status.running) throw new Error("checkpoint requires a stopped container");
    const limit = run.spec.checkpoint.maxSizeGB * 1024 ** 3;
    const layerBytes = await docker.writableSize(containerId);
    if (layerBytes > limit)
      throw new Error("container writable layer exceeds checkpoint size limit");
    const dirs = ctx.dirs(id);
    let estimatedBytes = layerBytes;
    for (const path of [
      dirs.orbit,
      ...(run.code ? [dirs.workspace] : []),
      dirs.diff,
      ...(run.spec.after?.copy ?? []).map((c) => c.source),
    ]) {
      estimatedBytes += (await dirBytes(path)) ?? 0;
      if (estimatedBytes > limit) throw new Error("checkpoint files exceed checkpoint size limit");
    }
    rmSync(root, { recursive: true, force: true });
    mkdirSync(root, { recursive: true, mode: 0o700 });
    for (const [src, dest] of [
      ["/orbit", join(root, "orbit")],
      ...(run.code ? [["/workspace", join(root, "workspace")]] : []),
    ]) {
      const error = await docker.copyFromContainer(containerId, src as string, dest as string);
      if (error) throw new Error(`checkpoint file copy failed: ${error}`);
    }
    finishHarness(null, join(root, "orbit", "agent"));
    rmSync(join(root, "orbit", "phases"), { recursive: true, force: true });
    if (existsSync(ctx.dirs(id).diff)) await cp(ctx.dirs(id).diff, join(root, "code.diff"));
    for (const [i, c] of (run.spec.after?.copy ?? []).entries()) {
      const dest = join(root, "after", String(i));
      mkdirSync(join(root, "after"), { recursive: true });
      await cp(c.source, dest, { recursive: true, verbatimSymlinks: true });
    }
    const filesBytes = await dirBytes(root);
    if (filesBytes === null || layerBytes + filesBytes > limit)
      throw new Error("checkpoint files exceed checkpoint size limit");
    const transcript = await loadRunAgentTranscript(join(root, "orbit", "agent"));
    const clearEnv = [
      ...new Set([
        ...run.spec.passEnv,
        "OPENAI_API_KEY",
        "ORBIT_RELAY_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
      ]),
    ];
    const imageId = await docker.commitCheckpoint(containerId, tag, clearEnv, {
      "orbit.checkpoint": id,
      [docker.LABEL_HOME]: ctx.homeLabel,
    });
    committed = true;
    checkpoint = {
      state: "ready",
      imageId,
      sizeBytes: layerBytes + filesBytes,
      executionMin,
      session:
        transcript && (transcript.harness === "codex" || transcript.harness === "claude-code")
          ? { harness: transcript.harness, sessionId: transcript.sessionId }
          : null,
      createdAt: nowIso(),
      reason: null,
    };
  } catch (e) {
    if (committed) await docker.removeCheckpoint(tag);
    rmSync(root, { recursive: true, force: true });
    checkpoint = {
      state: "failed",
      imageId: null,
      sizeBytes: null,
      session: null,
      createdAt: nowIso(),
      reason: ctx.redactor(run).apply((e as Error).message),
    };
  }
  const fresh = ctx.mustGet(id);
  fresh.checkpoint = checkpoint;
  ctx.save(
    fresh,
    "checkpoint",
    checkpoint.state === "ready"
      ? `saved ${checkpoint.sizeBytes} bytes; filesystem and session only`
      : `checkpoint failed: ${checkpoint.reason}`,
  );
}

export function resumeSpec(run: Run, command?: string[]): RunSpecInput {
  const checkpoint = run.checkpoint;
  if (checkpoint?.state !== "ready" || !checkpoint.imageId)
    throw new UserError("run has no usable checkpoint");
  const elapsed =
    checkpoint.executionMin ??
    (run.startedAt && run.endedAt
      ? Math.max(0, Date.parse(run.endedAt) - Date.parse(run.startedAt)) / 60_000
      : 0);
  const remaining = run.spec.timeoutMin === undefined ? undefined : run.spec.timeoutMin - elapsed;
  if (remaining !== undefined && remaining <= 0)
    throw new UserError("run exhausted its execution time budget");
  if (!command && !checkpoint.session)
    throw new UserError(
      "checkpoint has no native Agent session; provide a command to restore files",
    );
  return {
    ...run.spec,
    image: checkpoint.imageId,
    dockerfile: undefined,
    project: undefined,
    agent: undefined,
    agentBundle: undefined,
    command:
      command ??
      resumeAgentCommand(
        run.spec.command,
        checkpoint.session as NonNullable<typeof checkpoint.session>,
      ),
    parentId: run.id,
    name: `Resume ${run.spec.name ?? run.id}`.slice(0, 200),
    group: undefined,
    tags: { resumedFrom: run.id },
    params: {},
    ...(command ? { after: undefined, hooks: [] } : {}),
    resources: { ...run.spec.resources, node: run.node },
    timeoutMin: remaining,
  };
}

/** Copy immutable checkpoint files into a new run before it becomes visible to the scheduler. */
export async function restore(ctx: Pick<Context, "dirs">, source: Run, run: Run): Promise<void> {
  const root = checkpointDir(ctx, source.id);
  const dirs = ctx.dirs(run.id);
  for (const [from, dest] of [
    ["orbit", dirs.orbit],
    ["workspace", dirs.workspace],
  ]) {
    const src = join(root, from as string);
    if (existsSync(src)) await cp(src, dest as string, { recursive: true, verbatimSymlinks: true });
  }
  if (existsSync(join(root, "code.diff"))) await cp(join(root, "code.diff"), dirs.diff);
  if (source.code) run.code = structuredClone(source.code);
  if (run.spec.after)
    run.spec.after.copy = run.spec.after.copy.map((c, i) => ({
      ...c,
      source: join(dirs.root, "after-inputs", String(i)),
    }));
  for (const [i, c] of (run.spec.after?.copy ?? []).entries()) {
    mkdirSync(join(dirs.root, "after-inputs"), { recursive: true });
    await cp(join(root, "after", String(i)), c.source, { recursive: true, verbatimSymlinks: true });
  }
}
