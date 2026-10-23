import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// base "./" so the built site works under the GitHub Pages project path.
export default defineConfig({
  base: "./",
  plugins: [react()],
  // MapLibre is most of the bundle; keep it in its own long-cached chunk.
  build: { rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } }, chunkSizeWarningLimit: 1200 },
  server: { host: "127.0.0.1", port: 5173 },
  preview: { host: "127.0.0.1", port: 4173 },
  test: { environment: "jsdom" },
});
