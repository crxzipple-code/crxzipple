import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

const target = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const apiProxy = {
  "/api": {
    target,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
  "/health": target,
  "/about": target,
  "/access": target,
  "/agents": target,
  "/artifacts": target,
  "/authorization": target,
  "/browser": target,
  "/channels": target,
  "/conversations": target,
  "/daemon": target,
  "/dispatch": target,
  "/events": target,
  "/llms": target,
  "/memory": target,
  "/orchestration": target,
  "/sessions": target,
  "/skills": target,
  "/tools": target,
  "/turns": target,
  "/ui": target,
};

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("/vue") || id.includes("/pinia")) {
              return "vendor-vue";
            }
            if (id.includes("/lucide-vue-next")) {
              return "vendor-icons";
            }
            if (
              id.includes("/marked") ||
              id.includes("/dompurify") ||
              id.includes("/@types/dompurify")
            ) {
              return "vendor-markdown";
            }
            return "vendor";
          }
          if (id.includes("/src/pages/operations/modules/")) {
            const name = id
              .split("/src/pages/operations/modules/")[1]
              ?.replace(/\.vue.*$/, "")
              .replace(/OperationsPage$/, "")
              .replace(/([a-z])([A-Z])/g, "$1-$2")
              .toLowerCase();
            return name ? `operations-${name}` : "operations-module";
          }
          if (id.includes("/src/pages/operations/")) {
            return "page-operations";
          }
          if (id.includes("/src/pages/settings/")) {
            return "page-settings";
          }
          if (id.includes("/src/pages/workbench/")) {
            return "page-workbench";
          }
          if (id.includes("/src/pages/trace/")) {
            return "page-trace";
          }
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5174,
    proxy: apiProxy,
  },
  preview: {
    port: 4174,
    proxy: apiProxy,
  },
});
