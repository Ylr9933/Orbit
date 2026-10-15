import type { Hono } from "hono";
import { z } from "zod";
import {
  type Dataset,
  DatasetInput,
  type ExposeStatus,
  NodeAddInput,
  type NodeStatus,
} from "../../contracts/index.ts";
import { NotFoundError, UserError } from "../../runs/service.ts";
import type { AppDeps } from "../app.ts";

export function registerClusterRoutes(api: Hono, deps: AppDeps): void {
  const { cluster, datasets } = deps;
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
}
