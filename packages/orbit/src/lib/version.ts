import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// src/lib/version.ts in development, dist/cli.js when bundled.
function readVersion(): string {
  for (const p of ["../../package.json", "../package.json"]) {
    try {
      const pkg = require(p) as { name?: string; version?: string };
      if (pkg.name === "@zjunlp/orbit" && pkg.version) return pkg.version;
    } catch {}
  }
  return "0.0.0";
}

export const VERSION: string = readVersion();
