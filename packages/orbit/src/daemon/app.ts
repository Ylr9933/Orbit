import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { Readable } from "node:stream";
import { serveStatic } from "@hono/node-server/serve-static";
import { type Context, Hono } from "hono";
import { getCookie, setCookie } from "hono/cookie";
import { streamSSE } from "hono/streaming";
import { z } from "zod";
import {
  API_PREFIX,
  type Health,
  isTerminal,
  type Ledger,
  type Run,
  RunState,
} from "../contracts/index.ts";
import { VERSION } from "../lib/version.ts";
import { listArtifacts, readDiff, readLog, readMetrics, safeJoin } from "../records/index.ts";
import { NotFoundError, type RunService, UserError } from "../runs/service.ts";
import { loadTranscript } from "../sessions/index.ts";
import { runDoctor } from "./doctor.ts";

export interface AppDeps {
  token: string;
  startedAt: string;
  runs: RunService;
  /** Built Web UI directory, or null when not built. */
  webDir: string | null;
}

const COOKIE = "orbit_token";

export function createApp(deps: AppDeps): Hono {
  const { runs } = deps;
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
    return c.json(await readLog(runs.dirs(run.id).log, offset, limit, isTerminal(run.state)));
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
    return c.redirect("/");
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
  if (err instanceof UserError) return c.json({ error: err.message }, 400);
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
