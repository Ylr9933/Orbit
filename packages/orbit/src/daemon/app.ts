import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { Readable } from "node:stream";
import { serveStatic } from "@hono/node-server/serve-static";
import { type Context, Hono } from "hono";
import { getCookie, setCookie } from "hono/cookie";
import { streamSSE } from "hono/streaming";
import { z } from "zod";
import { AuthError, type AuthStore } from "../auth/index.ts";
import type { BenchmarkRegistry } from "../bench/registry.ts";
import type { BenchService } from "../bench/service.ts";
import {
  API_PREFIX,
  type AuthProfile,
  type AuthTestResult,
  type Benchmark,
  BenchmarkInput,
  type Health,
  isTerminal,
  type Ledger,
  type NotifyTarget,
  type Run,
  RunState,
} from "../contracts/index.ts";
import { VERSION } from "../lib/version.ts";
import type { Notifier, NotifyStore } from "../notify/index.ts";
import { listArtifacts, readDiff, readLog, readMetrics, safeJoin } from "../records/index.ts";
import { NotFoundError, type RunService, UserError } from "../runs/service.ts";
import { loadTranscript } from "../sessions/index.ts";
import { runDoctor } from "./doctor.ts";

export interface AppDeps {
  token: string;
  startedAt: string;
  runs: RunService;
  auth: AuthStore;
  notifyStore: NotifyStore;
  notifier: Notifier;
  bench: BenchService;
  benchmarks: BenchmarkRegistry;
  /** Built Web UI directory, or null when not built. */
  webDir: string | null;
}

const COOKIE = "orbit_token";

export function createApp(deps: AppDeps): Hono {
  const { runs, auth, notifyStore, notifier, bench, benchmarks } = deps;
  const app = new Hono();
  const api = new Hono();

  api.use("*", async (c, next) => {
    const bearer = c.req.header("authorization") === `Bearer ${deps.token}`;
    if (!bearer && getCookie(c, COOKIE) !== deps.token)
      return c.json({ error: "unauthorized" }, 401);
    await next();
  });

  api.get("/health", (c) =>
    c.json<Health>({ ok: true, version: VERSION, pid: process.pid, startedAt: deps.startedAt }),
  );
  api.get("/resources", async (c) => c.json(await runs.resources(true)));
  api.get("/doctor", async (c) => c.json(await runDoctor()));
  api.get("/ledger", async (c) =>
    c.json<Ledger>({ resources: await runs.resources(), ...runs.ledger() }),
  );

  api.get("/runs", (c) => {
    const states = c.req
      .query("state")
      ?.split(",")
      .filter(Boolean)
      .map((s) => RunState.parse(s));
    const limit = Number(c.req.query("limit") ?? 500);
    return c.json({ runs: runs.storeList({ states, group: c.req.query("group"), limit }) });
  });
  api.post("/runs", async (c) => c.json(await runs.submit(await c.req.json()), 201));
  api.get("/runs/:id", (c) => c.json(must(runs.get(c.req.param("id")))));
  api.post("/runs/:id/cancel", async (c) => c.json(await runs.cancel(c.req.param("id"))));
  api.put("/runs/:id/note", async (c) => {
    const { note } = z.object({ note: z.string().max(100_000) }).parse(await c.req.json());
    return c.json(runs.setNote(c.req.param("id"), note));
  });

  /** Long-poll until the run is terminal or `timeout` seconds pass; returns the current run. */
  api.get("/runs/:id/wait", async (c) => {
    const id = c.req.param("id");
    const timeoutMs = Math.min(Number(c.req.query("timeout") ?? 30), 120) * 1000;
    const run = must(runs.get(id));
    if (isTerminal(run.state)) return c.json(run);
    const done = await new Promise<Run>((resolve) => {
      const onChange = ({ run: r }: { run: Run }) => {
        if (r.id === id && isTerminal(r.state) && r.cleanup !== "pending") finish(r);
      };
      const t = setTimeout(() => finish(must(runs.get(id))), timeoutMs);
      const finish = (r: Run) => {
        clearTimeout(t);
        runs.off("change", onChange);
        resolve(r);
      };
      runs.on("change", onChange);
      c.req.raw.signal.addEventListener("abort", () => finish(run));
    });
    return c.json(done);
  });

  api.get("/runs/:id/events", (c) => {
    const id = c.req.param("id");
    must(runs.get(id));
    return c.json({ events: runs.events(id, Number(c.req.query("after") ?? 0)) });
  });

  api.get("/runs/:id/logs", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    const offset = Number(c.req.query("offset") ?? 0);
    const limit = Number(c.req.query("limit") ?? 256 * 1024);
    const chunk = await readLog(runs.dirs(run.id).log, offset, limit, isTerminal(run.state));
    // Process runs write straight to the log; it is redacted in place only when they end.
    if (run.spec.backend === "process" && !isTerminal(run.state))
      chunk.text = runs.redactor(run).apply(chunk.text);
    return c.json(chunk);
  });

  /** The whole combined log as plain text (for download). */
  api.get("/runs/:id/log.txt", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    const file = runs.dirs(run.id).log;
    const st = await stat(file).catch(() => null);
    if (!st) return c.text("");
    c.header("content-type", "text/plain; charset=utf-8");
    c.header("content-length", String(st.size));
    if (c.req.query("download"))
      c.header("content-disposition", `attachment; filename="${run.id}.log"`);
    return c.body(Readable.toWeb(createReadStream(file)) as ReadableStream);
  });

  api.get("/runs/:id/metrics", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    return c.json(await readMetrics(runs.dirs(run.id).metrics));
  });

  api.get("/runs/:id/artifacts", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    return c.json(await listArtifacts(runs.dirs(run.id).output));
  });

  api.get("/runs/:id/files/*", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    const rel = decodeURIComponent(c.req.path.split("/files/")[1] ?? "");
    const file = safeJoin(runs.dirs(run.id).output, rel);
    const st = file ? await stat(file).catch(() => null) : null;
    if (!file || !st?.isFile()) return c.json({ error: "not found" }, 404);
    c.header("content-length", String(st.size));
    c.header("content-type", contentType(file));
    if (c.req.query("download"))
      c.header("content-disposition", `attachment; filename="${rel.split("/").pop()}"`);
    return c.body(Readable.toWeb(createReadStream(file)) as ReadableStream);
  });

  api.get("/runs/:id/diff", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    return c.json(await readDiff(runs.dirs(run.id).diff));
  });

  api.get("/runs/:id/session", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    if (!run.spec.agent) return c.json({ error: "run has no linked agent session" }, 404);
    const t = await loadTranscript(run.spec.agent);
    return t ? c.json(t) : c.json({ error: "session transcript not found on this node" }, 404);
  });

  // Credentials: secrets go in once and never come back out.
  api.get("/auth", (c) => c.json<{ profiles: AuthProfile[] }>({ profiles: auth.list() }));
  api.post("/auth", async (c) => c.json(auth.put(await c.req.json()), 201));
  api.delete("/auth/:name", (c) => {
    if (!auth.remove(c.req.param("name"))) throw new NotFoundError("auth profile not found");
    return c.json({ ok: true });
  });
  api.post("/auth/:name/test", async (c) => {
    const body = (await c.req.json().catch(() => ({}))) as { image?: string };
    return c.json<AuthTestResult>(await runs.testAuth(c.req.param("name"), body.image));
  });

  api.get("/notify", (c) => c.json<{ targets: NotifyTarget[] }>({ targets: notifyStore.list() }));
  api.post("/notify", async (c) => c.json(notifyStore.put(await c.req.json()), 201));
  api.delete("/notify/:name", (c) => {
    if (!notifyStore.remove(c.req.param("name")))
      throw new NotFoundError("notify target not found");
    return c.json({ ok: true });
  });
  api.post("/notify/:name/test", async (c) => {
    const name = c.req.param("name");
    if (!notifyStore.targets().some((t) => t.name === name))
      throw new NotFoundError("notify target not found");
    try {
      await notifier.test(name);
    } catch (e) {
      throw new UserError(`sending failed: ${(e as Error).message}`);
    }
    return c.json({ ok: true });
  });

  // Benchmarks: registered checkouts, jobs of trials, and method comparison.
  api.get("/benchmarks", (c) =>
    c.json<{ benchmarks: Benchmark[] }>({ benchmarks: benchmarks.list() }),
  );
  api.post("/benchmarks", async (c) => {
    const input = BenchmarkInput.parse(await c.req.json());
    if (!existsSync(input.path)) throw new UserError(`benchmark path not found: ${input.path}`);
    return c.json(benchmarks.put(input), 201);
  });
  api.delete("/benchmarks/:name", (c) => {
    if (!benchmarks.remove(c.req.param("name"))) throw new NotFoundError("benchmark not found");
    return c.json({ ok: true });
  });
  api.get("/benchmarks/:name/tasks", (c) => c.json({ tasks: bench.tasks(c.req.param("name")) }));
  api.get("/bench/jobs", (c) => c.json(bench.jobs(Number(c.req.query("limit") ?? 200))));
  api.post("/bench/jobs", async (c) => c.json(await bench.submit(await c.req.json()), 201));
  api.get("/bench/jobs/:id", (c) => c.json(bench.job(c.req.param("id"))));
  api.post("/bench/jobs/:id/cancel", async (c) => c.json(await bench.cancel(c.req.param("id"))));
  api.get("/bench/compare", (c) =>
    c.json(bench.compare((c.req.query("jobs") ?? "").split(",").filter(Boolean))),
  );

  /** Server-sent events: `run` with the full Run on every change. */
  api.get("/stream", (c) =>
    streamSSE(c, async (stream) => {
      const onChange = ({ run }: { run: Run }) => {
        void stream.writeSSE({ event: "run", data: JSON.stringify(run) });
      };
      runs.on("change", onChange);
      const ping = setInterval(() => void stream.writeSSE({ event: "ping", data: "" }), 15_000);
      await new Promise<void>((resolve) => stream.onAbort(resolve));
      clearInterval(ping);
      runs.off("change", onChange);
    }),
  );

  app.route(API_PREFIX, api);

  // Web UI: `/login?token=...` sets an HttpOnly cookie, then the SPA uses the API with it.
  app.get("/login", (c) => {
    if (c.req.query("token") !== deps.token) return c.text("invalid token; run `orbit web`", 401);
    setCookie(c, COOKIE, deps.token, { httpOnly: true, sameSite: "Strict", path: "/" });
    // Only same-origin paths, so the login link cannot redirect elsewhere.
    const next = c.req.query("next") ?? "/";
    return c.redirect(/^\/(?![/\\])/.test(next) ? next : "/");
  });
  if (deps.webDir && existsSync(deps.webDir)) {
    const root = deps.webDir;
    app.use("/assets/*", serveStatic({ root }));
    app.get("*", serveStatic({ root, path: "index.html" }));
  } else {
    app.get("/", (c) => c.text("Orbit Web UI is not built. Run `pnpm build` in the repository."));
  }

  app.onError((err, c) => errorResponse(c, err));
  return app;
}

function must<T>(v: T | null): T {
  if (v === null) throw new NotFoundError("not found");
  return v;
}

function errorResponse(c: Context, err: Error) {
  if (err instanceof NotFoundError) return c.json({ error: err.message }, 404);
  if (err instanceof UserError || err instanceof AuthError)
    return c.json({ error: err.message }, 400);
  if (err instanceof z.ZodError) return c.json({ error: z.prettifyError(err) }, 400);
  if (err instanceof SyntaxError) return c.json({ error: `invalid JSON: ${err.message}` }, 400);
  console.error(err);
  return c.json({ error: err.message }, 500);
}

const TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  svg: "image/svg+xml",
  webp: "image/webp",
  pdf: "application/pdf",
  json: "application/json",
  jsonl: "text/plain; charset=utf-8",
  html: "text/plain; charset=utf-8",
};

function contentType(file: string): string {
  const ext = file.split(".").pop()?.toLowerCase() ?? "";
  return TYPES[ext] ?? "text/plain; charset=utf-8";
}
