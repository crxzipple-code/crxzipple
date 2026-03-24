import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 4173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/about": "http://127.0.0.1:8000",
      "/turns": "http://127.0.0.1:8000",
      "/conversations": "http://127.0.0.1:8000",
      "/agents": "http://127.0.0.1:8000",
      "/llms": "http://127.0.0.1:8000",
    },
  },
});
