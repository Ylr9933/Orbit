// Package the Web UI and the canonical skills alongside the compiled entrypoints.
import { cpSync, existsSync, rmSync } from "node:fs";
import { join } from "node:path";

const pkg = join(import.meta.dirname, "..");
const from = join(pkg, "../web/dist");
const to = join(pkg, "dist/web");
if (!existsSync(join(from, "index.html"))) {
  console.error("copy-assets: packages/web/dist is missing; run `pnpm build` at the repo root");
  process.exit(1);
}
rmSync(to, { recursive: true, force: true });
cpSync(from, to, { recursive: true });
cpSync(join(pkg, "../../LICENSE"), join(pkg, "LICENSE"));
const plugin = join(pkg, "../../plugin");
cpSync(join(plugin, "skills"), join(pkg, "dist/plugin/skills"), { recursive: true });
cpSync(join(plugin, "cordis.patch.yml"), join(pkg, "dist/plugin/cordis.patch.yml"));
console.log("copy-assets: dist/web and dist/plugin ready");
