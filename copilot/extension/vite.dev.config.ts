import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Standalone dev harness: renders the panel on a mock TradingView-like page
// and connects directly to the local backend (no Chrome APIs needed).
export default defineConfig({
  plugins: [react()],
  root: "src/dev",
  server: { port: 5173, strictPort: true },
});
