import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: { rollupOptions: { output: { manualChunks: { echarts: ["echarts"] } } }, chunkSizeWarningLimit: 1200 },
  server: {
    port: 5173,
    proxy: { "/api": backend, "/health": backend },
  },
});
