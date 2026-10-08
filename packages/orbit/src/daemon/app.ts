import { accessSync, constants, createReadStream, existsSync, statSync } from "node:fs";
import { stat } from "node:fs/promises";
import { Readable } from "node:stream";
import { serveStatic } from "@hono/node-server/serve-static";
import { type Context, Hono } from "hono";
import { getCookie, setCookie } from "hono/cookie";
import { streamSSE } from "hono/streaming";
import { z } from "zod";
import { AuthError, type AuthStore } from "../auth/index.ts";
import type { BenchmarkRegistry } from "../bench/registry.ts";
import { loadResources, resolveResources } from "../bench/resources.ts";
import type { BenchService } from "../bench/service.ts";
import type { ClusterService } from "../cluster/service.ts";
import type { OrbitPaths } from "../config/paths.ts";
import {
  API_PREFIX,
  type AuthProfile,
  type AuthTestResult,
  type Benchmark,
  BenchmarkInput,
  type Dataset,
  DatasetInput,
  type ExposeStatus,
  FolderExport,
  type FolderList,
  FolderMove,
  type Health,
  isTerminal,
  type Ledger,
  NodeAddInput,
  type NodeStatus,
  NotifyPairInput,
  type NotifyTarget,
  type Run,
  type RunSessions,
  RunState,
} from "../contracts/index.ts";
import type { FeishuBots } from "../feishu/index.ts";
import { sameSecret, tokenMatches } from "../lib/tokens.ts";
import { VERSION } from "../lib/version.ts";
import type { Notifier, NotifyStore } from "../notify/index.ts";
import {
  decodePath,
  listArtifacts,
  outputFile,
  readDiff,
  readLog,
  readMetrics,
} from "../records/index.ts";
import { NotFoundError, type RunService, UserError } from "../runs/service.ts";
import { loadRunAgentTranscript, loadTranscript } from "../sessions/index.ts";
import type { Store } from "../store/index.ts";
import type { DatasetRegistry } from "../workspace/datasets.ts";
import { runDoctor } from "./doctor.ts";

export interface AppDeps {
  token: string;
  startedAt: string;
  runs: RunService;
  auth: AuthStore;
  notifyStore: NotifyStore;
  notifier: Notifier;
  feishu: FeishuBots;
  bench: BenchService;
  benchmarks: BenchmarkRegistry;
  cluster: ClusterService;
  datasets: DatasetRegistry;
  store: Store;
  paths: OrbitPaths;
  /** Built Web UI directory, or null when not built. */
  webDir: string | null;
}

const COOKIE = "orbit_token";

export function createApp(deps: AppDeps): Hono {
  const { runs, auth, notifyStore, notifier, feishu, bench, benchmarks, cluster, datasets } = deps;
  const app = new Hono();
  const api = new Hono();

  api.use("*", async (c, next) => {
    if (tokenMatches(c.req.header("authorization"), deps.token)) return next();
    if (!sameSecret(getCookie(c, COOKIE), deps.token))
      return c.json({ error: "unauthorized" }, 401);
    // The cookie also rides on requests from other localhost ports (SameSite ignores ports):
    // changes must come from the Web UI's own origin.
    if (c.req.method !== "GET" && c.req.method !== "HEAD" && !sameOrigin(c))
      return c.json({ error: "cross-origin request refused" }, 403);
    await next();
  });

  api.get("/health", (c) =>
    c.json<Health>({ ok: true, version: VERSION, pid: process.pid, startedAt: deps.startedAt }),
  );
  api.get("/resources", async (c) => c.json(await runs.resources(true)));
  api.get("/doctor", async (c) => c.json(await runDoctor(deps.paths)));
  api.get("/ledger", async (c) =>
    c.json<Ledger>({
      resources: await runs.resources(),
      ...runs.ledger(),
      nodes: cluster.nodeStatus(),
    }),
  );

  api.get("/runs", (c) => {
    const states = c.req
      .query("state")
      ?.split(",")
      .filter(Boolean)
      .map((s) => RunState.parse(s));
    const limit = num(c.req.query("limit"), 500);
    const folder = c.req.query("folder") || undefined;
    return c.json({ runs: runs.storeList({ states, group: c.req.query("group"), folder, limit }) });
  });
  api.post("/runs", async (c) =>
    c.json(await runs.submit(await c.req.json(), { folder: c.req.query("folder") }), 201),
  );

  api.post("/runs/check", async (c) => c.json(await runs.check(await c.req.json())));

  api.get("/folders", (c) => c.json<FolderList>({ folders: deps.store.folders() }));
  api.post("/folders/move", async (c) => {
    const { folder, ids } = FolderMove.parse(await c.req.json());
    return c.json(bench.move(ids, folder));
  });
  api.post("/folders/export", async (c) => {
    const { folder, dest } = FolderExport.parse(await c.req.json());
    return c.json(await bench.exportFolder(folder, dest));
  });
  api.get("/runs/:id", (c) => c.json(must(runs.get(c.req.param("id")))));
  api.post("/runs/:id/cancel", async (c) => c.json(await runs.cancel(c.req.param("id"))));
  api.put("/runs/:id/note", async (c) => {
    const { note } = z.object({ note: z.string().max(100_000) }).parse(await c.req.json());
    return c.json(runs.setNote(c.req.param("id"), note));
  });

  /** Long-poll until the run is terminal or `timeout` seconds pass; returns the current run. */
  api.get("/runs/:id/wait", async (c) => {
    const id = c.req.param("id");
    const timeoutMs = Math.min(num(c.req.query("timeout"), 30), 120) * 1000;
    const run = must(runs.get(id));
    if (isTerminal(run.state) && run.cleanup !== "pending") return c.json(run);
    const done = await new Promise<Run>((resolve) => {
      const onChange = ({ run: r }: { run: Run }) => {
        if (r.id === id && isTerminal(r.state) && r.cleanup !== "pending") finish(r);
      };
      const t = setTimeout(() => finish(runs.get(id) ?? run), timeoutMs);
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
    return c.json({ events: runs.events(id, num(c.req.query("after"), 0)) });
  });

  api.get("/runs/:id/logs", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    const offset = num(c.req.query("offset"), 0);
    const limit = num(c.req.query("limit"), 256 * 1024);
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
    if (c.req.query("download")) c.header("content-disposition", attachment(`${run.id}.log`));
    // As for /logs: a running process run's log is not redacted on disk yet.
    if (run.spec.backend === "process" && !isTerminal(run.state))
      return c.body(
        Readable.toWeb(createReadStream(file).pipe(runs.redactor(run).stream())) as ReadableStream,
      );
    c.header("content-length", String(st.size));
    return c.body(Readable.toWeb(createReadStream(file)) as ReadableStream);
  });

  // Irreversible: the CLI and the Web UI ask for a typed confirmation before calling it.
  api.post("/runs/delete", async (c) => {
    const { ids } = z
      .object({ ids: z.array(z.string()).min(1).max(5000) })
      .parse(await c.req.json());
    return c.json(await runs.delete(ids));
  });

  api.get("/runs/:id/metrics", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    return c.json(await readMetrics(runs.dirs(run.id).metrics));
  });

  // Outputs of a run on another node stay there and are read through it on demand.
  api.get("/runs/:id/artifacts", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    if (run.remote) return c.json(must(await remoteRecords(() => cluster.artifacts(run))));
    return c.json(await listArtifacts(runs.dirs(run.id).output));
  });

  api.get("/runs/:id/files/*", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    const rel = decodePath(c.req.path, "/files/");
    // Run outputs are untrusted content on the daemon's origin: no script, no type sniffing.
    c.header("content-security-policy", ARTIFACT_CSP);
    c.header("x-content-type-options", "nosniff");
    c.header("content-type", contentType(rel));
    if (c.req.query("download")) c.header("content-disposition", attachment(rel));
    if (run.remote) {
      const res = await remoteRecords(() => cluster.file(run, rel));
      if (!res || res.status === 404) return c.json({ error: "not found" }, 404);
      c.header("content-length", res.headers.get("content-length") ?? undefined);
      return c.body(res.body as ReadableStream);
    }
    const f = await outputFile(runs.dirs(run.id).output, rel);
    if (!f) return c.json({ error: "not found" }, 404);
    c.header("content-length", String(f.size));
    return c.body(Readable.toWeb(createReadStream(f.file)) as ReadableStream);
  });

  api.get("/runs/:id/diff", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    return c.json(await readDiff(runs.dirs(run.id).diff));
  });

  api.get("/runs/:id/session", async (c) => {
    const run = must(runs.get(c.req.param("id")));
    const submitter = run.spec.agent ? await loadTranscript(run.spec.agent) : null;
    // A run executed on a worker keeps its Agent home there: only local runs have one here.
    const agent = run.remote ? null : await loadRunAgentTranscript(runs.dirs(run.id).agent);
    return c.json<RunSessions>({
      submitter,
      submitterError:
        run.spec.agent && !submitter ? "session transcript not found on this node" : null,
      agent,
    });
  });

  // Cluster: worker nodes this node places runs on, and this node's own listener for a primary.
  api.get("/cluster/nodes", (c) =>
    c.json<{ nodes: NodeStatus[] }>({ nodes: cluster.nodeStatus() }),
  );
  api.post("/cluster/nodes", async (c) => {
    const input = NodeAddInput.parse(await c.req.json());
    return c.json(await cluster.addNode(input.url, input.token), 201);
  });
  api.delete("/cluster/nodes/:name", (c) => {
    if (!cluster.removeNode(c.req.param("name"))) throw new NotFoundError("node not found");
    return c.json({ ok: true });
  });
  api.get("/cluster/expose", (c) => c.json<ExposeStatus>(cluster.exposeStatus()));
  api.post("/cluster/expose", async (c) => {
    const { listen } = z.object({ listen: z.string().nullable() }).parse(await c.req.json());
    return c.json<ExposeStatus>(await cluster.setExpose(listen));
  });
  /** The token a primary needs to add this node (local, daemon-token callers only). */
  api.get("/cluster/token", (c) => c.json({ token: cluster.clusterToken() }));
  api.post("/cluster/token/rotate", (c) => c.json({ token: cluster.clusterToken(true) }));

  api.get("/datasets", (c) => c.json<{ datasets: Dataset[] }>({ datasets: datasets.list() }));
  api.post("/datasets", async (c) => {
    const input = DatasetInput.parse(await c.req.json());
    try {
      return c.json(datasets.put(input), 201);
    } catch (e) {
      throw new UserError((e as Error).message);
    }
  });
  api.delete("/datasets/:name", (c) => {
    if (!datasets.remove(c.req.param("name"))) throw new NotFoundError("dataset not found");
    return c.json({ ok: true });
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

  const withConnection = (t: NotifyTarget): NotifyTarget =>
    t.kind === "feishu-app" ? { ...t, connection: feishu.connection(t.name) } : t;
  api.get("/notify", (c) =>
    c.json<{ targets: NotifyTarget[] }>({ targets: notifyStore.list().map(withConnection) }),
  );
  api.post("/notify", async (c) => {
    const t = notifyStore.put(await c.req.json());
    void feishu.sync();
    return c.json(withConnection(t), 201);
  });
  api.delete("/notify/:name", (c) => {
    if (!notifyStore.remove(c.req.param("name")))
      throw new NotFoundError("notify target not found");
    void feishu.sync();
    return c.json({ ok: true });
  });
  api.post("/notify/:name/pair", async (c) => {
    const { code } = NotifyPairInput.parse(await c.req.json());
    try {
      await feishu.pair(c.req.param("name"), code);
    } catch (e) {
      throw new UserError((e as Error).message);
    }
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
    if (input.adapter.startsWith("/")) {
      try {
        if (!statSync(input.adapter).isFile()) throw new Error();
        accessSync(input.adapter, constants.X_OK);
      } catch {
        throw new UserError(`adapter is not an executable file: ${input.adapter}`);
      }
    }
    // Listing the tasks once checks that the adapter answers (and the resources file fits) first.
    const { tasks } = await bench.infoOf({
      ...BenchmarkInput.parse(input),
      createdAt: "",
      updatedAt: "",
    });
    if (input.resources) {
      try {
        const ids = tasks.map((t) => t.id);
        resolveResources(loadResources(input.resources), ids, ids);
      } catch (e) {
        throw new UserError((e as Error).message);
      }
    }
    return c.json(benchmarks.put(input), 201);
  });
  api.delete("/benchmarks/:name", (c) => {
    if (!benchmarks.remove(c.req.param("name"))) throw new NotFoundError("benchmark not found");
    return c.json({ ok: true });
  });
  api.get("/benchmarks/:name/tasks", async (c) =>
    c.json({ tasks: await bench.tasks(c.req.param("name")) }),
  );
  api.get("/bench/jobs", (c) => c.json(bench.jobs(num(c.req.query("limit"), 200))));
  api.post("/bench/jobs", async (c) =>
    c.json(await bench.submit(await c.req.json(), { folder: c.req.query("folder") }), 201),
  );
  api.get("/bench/jobs/:id", (c) => c.json(bench.job(c.req.param("id"))));
  api.post("/bench/jobs/:id/cancel", async (c) => c.json(await bench.cancel(c.req.param("id"))));
  api.post("/bench/jobs/:id/rescore", async (c) =>
    c.json(bench.rescore(c.req.param("id"), await c.req.json().catch(() => ({})))),
  );
  api.delete("/bench/jobs/:id", async (c) => c.json(await bench.deleteJob(c.req.param("id"))));
  api.get("/bench/usage", (c) =>
    c.json(bench.usage((c.req.query("jobs") ?? "").split(",").filter(Boolean))),
  );
  api.get("/bench/compare", (c) =>
    c.json(bench.compare((c.req.query("jobs") ?? "").split(",").filter(Boolean))),
  );

  /** Server-sent events: `run` with the full Run on every change. */
  api.get("/stream", (c) =>
    streamSSE(c, async (stream) => {
      const onChange = ({ run }: { run: Run }) => {
        void stream.writeSSE({ event: "run", data: JSON.stringify(run) });
      };
      const onDeleted = (ids: string[]) => {
        void stream.writeSSE({ event: "deleted", data: JSON.stringify({ ids }) });
      };
      runs.on("change", onChange);
      runs.on("deleted", onDeleted);
      const ping = setInterval(() => void stream.writeSSE({ event: "ping", data: "" }), 15_000);
      await new Promise<void>((resolve) => stream.onAbort(resolve));
      clearInterval(ping);
      runs.off("change", onChange);
      runs.off("deleted", onDeleted);
    }),
  );

  app.route(API_PREFIX, api);

  // Web UI: `/login?token=...` sets an HttpOnly cookie, then the SPA uses the API with it.
  app.get("/login", (c) => {
    if (!sameSecret(c.req.query("token"), deps.token))
      return c.text("invalid token; run `orbit web`", 401);
    setCookie(c, COOKIE, deps.token, { httpOnly: true, sameSite: "Strict", path: "/" });
    // Only same-origin paths, so the login link cannot redirect elsewhere.
    const next = c.req.query("next") ?? "/";
    const origin = new URL(c.req.url).origin;
    const to = URL.canParse(next, origin) ? new URL(next, origin) : null;
    return c.redirect(to?.origin === origin ? to.pathname + to.search + to.hash : "/");
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

/** Call the run's node; an unreachable node is a 502 with the reason. */
async function remoteRecords<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    throw new BadGateway(`node unavailable: ${(e as Error).message}`);
  }
}

class BadGateway extends Error {}

function must<T>(v: T | null): T {
  if (v === null) throw new NotFoundError("not found");
  return v;
}

function errorResponse(c: Context, err: Error) {
  if (err instanceof NotFoundError) return c.json({ error: err.message }, 404);
  if (err instanceof BadGateway) return c.json({ error: err.message }, 502);
  if (err instanceof UserError || err instanceof AuthError)
    return c.json({ error: err.message }, 400);
  if (err instanceof z.ZodError) return c.json({ error: z.prettifyError(err) }, 400);
  if (err instanceof SyntaxError) return c.json({ error: `invalid JSON: ${err.message}` }, 400);
  console.error(err);
  return c.json({ error: err.message }, 500);
}

const ARTIFACT_CSP = "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'";

/** `Content-Disposition` for a download, with a UTF-8 name and an ASCII fallback. */
function attachment(path: string): string {
  const name = path.split("/").pop() || "download";
  const ascii = name.replace(/[^\x20-\x7e]|["\\]/g, "_");
  return `attachment; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(name)}`;
}

/** A request from the Web UI itself (browsers send these headers on every POST/PUT/DELETE). */
function sameOrigin(c: Context): boolean {
  const site = c.req.header("sec-fetch-site");
  if (site) return site === "same-origin" || site === "none";
  const origin = c.req.header("origin");
  return !origin || origin === new URL(c.req.url).origin;
}

/** A numeric query parameter, or the default when absent or not a number. */
function num(v: string | undefined, def: number): number {
  const n = v === undefined || v === "" ? Number.NaN : Number(v);
  return Number.isFinite(n) ? n : def;
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
