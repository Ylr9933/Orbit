import type { Hono } from "hono";
import { FolderExport, type FolderList, FolderMove } from "../../contracts/index.ts";
import type { AppDeps } from "../app.ts";

export function registerFoldersRoutes(api: Hono, deps: AppDeps): void {
  const { bench } = deps;
  api.get("/folders", (c) => c.json<FolderList>({ folders: deps.store.folders() }));
  api.post("/folders/move", async (c) => {
    const { folder, ids } = FolderMove.parse(await c.req.json());
    return c.json(bench.move(ids, folder));
  });
  api.post("/folders/export", async (c) => {
    const { folder, dest } = FolderExport.parse(await c.req.json());
    return c.json(await bench.exportFolder(folder, dest));
  });
}
