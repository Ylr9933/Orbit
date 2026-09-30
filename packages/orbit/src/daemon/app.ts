import { Hono } from "hono";
import { API_PREFIX, type Health } from "../contracts/index.ts";
import { VERSION } from "../lib/version.ts";
import { probeNode } from "../resources/probe.ts";
import { runDoctor } from "./doctor.ts";

export interface AppDeps {
  token: string;
  diskPath: string;
  startedAt: string;
}

export function createApp(deps: AppDeps): Hono {
  const app = new Hono();
  const api = new Hono();

  api.use("*", async (c, next) => {
    if (c.req.header("authorization") !== `Bearer ${deps.token}`) {
      return c.json({ error: "unauthorized" }, 401);
    }
    await next();
  });

  api.get("/health", (c) =>
    c.json<Health>({ ok: true, version: VERSION, pid: process.pid, startedAt: deps.startedAt }),
  );
  api.get("/resources", async (c) => c.json(await probeNode(deps.diskPath)));
  api.get("/doctor", async (c) => c.json(await runDoctor()));

  app.route(API_PREFIX, api);
  app.onError((err, c) => c.json({ error: err.message }, 500));
  return app;
}
