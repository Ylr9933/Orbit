import { defineConfig } from "tsdown";

export default defineConfig({
  entry: { cli: "src/bin.ts" },
  format: "esm",
  platform: "node",
  target: "node24",
  dts: false,
  clean: true,
});
