import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readdirSync, readFileSync } from "node:fs";
import { buildHomeLocators } from "./scripts/home-index";
import { join } from "node:path";

function checkBuiltCopy(folder = "dist") {
  for (const file of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, file.name);
    if (file.isDirectory()) checkBuiltCopy(path);
    else if (/\.(js|html)$/.test(file.name) && /\b(fair value|good deal|overpriced|worth)\b/i.test(readFileSync(path, "utf8")))
      throw new Error("Built site contains prohibited home-value wording");
  }
}

// base "./" so the built site works under the GitHub Pages project path.
export default defineConfig({
  base: "./",
  plugins: [react(), { name: "home-locators", buildStart: () => { buildHomeLocators(); }, configureServer: () => { buildHomeLocators(); } }, { name: "home-copy-check", apply: "build", closeBundle: () => checkBuiltCopy() }],
  // MapLibre is most of the bundle; keep it in its own long-cached chunk.
  build: { rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } }, chunkSizeWarningLimit: 1200 },
  server: { host: "127.0.0.1", port: 5173 },
  preview: { host: "127.0.0.1", port: 4173 },
  test: { environment: "jsdom" },
});
