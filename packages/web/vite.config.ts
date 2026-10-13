import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `pnpm dev` proxies the API to a running daemon; open /login?token=... once to set the cookie.
const target = process.env.ORBIT_URL ?? `http://127.0.0.1:${process.env.ORBIT_PORT ?? 7717}`;

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": target, "/login": target } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 600,
    license: { fileName: "THIRD_PARTY_LICENSES.md" },
  },
});
