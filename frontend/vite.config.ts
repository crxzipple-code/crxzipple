import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("/vue/") || id.includes("@vue")) {
              return "vendor-vue";
            }
            if (
              id.includes("markdown-it") ||
              id.includes("markdown-it-texmath") ||
              id.includes("/katex/")
            ) {
              return "vendor-markdown";
            }
            return "vendor";
          }
          return undefined;
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
  server: {
    port: 4173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/about": "http://127.0.0.1:8000",
      "/turns": "http://127.0.0.1:8000",
      "/conversations": "http://127.0.0.1:8000",
      "/memory": "http://127.0.0.1:8000",
      "/agents": "http://127.0.0.1:8000",
      "/llms": "http://127.0.0.1:8000",
    },
  },
});
