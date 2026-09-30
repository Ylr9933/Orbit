// Bundle the built Web UI next to dist/cli.mjs so `orbit` serves it (see daemon/server.ts findWebDir).
import { cpSync, existsSync, rmSync } from "node:fs";
import { join } from "node:path";

const pkg = join(import.meta.dirname, "..");
const from = join(pkg, "../web/dist");
const to = join(pkg, "dist/web");
if (!existsSync(join(from, "index.html"))) {
  console.error("copy-web: packages/web/dist is missing; run `pnpm build` at the repo root");
  process.exit(1);
}
rmSync(to, { recursive: true, force: true });
cpSync(from, to, { recursive: true });
console.log("copy-web: dist/web ready");
