// Builds the MV3 extension into dist/.
// Content scripts cannot be ES modules, so each entry is built separately:
//   content.js    - IIFE, injected into TradingView (shadow-DOM panel)
//   background.js - ES module service worker (owns the backend WebSocket)
//   options.html  - options page
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { cpSync, rmSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(root, "dist");
rmSync(out, { recursive: true, force: true });

const common = {
  root,
  configFile: false,
  plugins: [react()],
  logLevel: "warn",
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
};

const lib = (entry, name, format) =>
  build({
    ...common,
    publicDir: false,
    build: {
      outDir: out,
      emptyOutDir: false,
      sourcemap: false,
      lib: { entry: resolve(root, entry), name, formats: [format], fileName: () => `${name}.js` },
      rollupOptions: { output: { inlineDynamicImports: true } },
    },
  });

await lib("src/content/index.tsx", "content", "iife");
await lib("src/background/index.ts", "background", "es");
await build({
  ...common,
  root: resolve(root, "src/options"),
  base: "./",
  publicDir: false,
  build: { outDir: out, emptyOutDir: false, rollupOptions: { input: resolve(root, "src/options/options.html") } },
});
cpSync(resolve(root, "public"), out, { recursive: true });
console.log("Built extension into", out);
