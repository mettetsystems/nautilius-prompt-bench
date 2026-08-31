import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { isSpaNavigation } from "./vite.proxy";

const rootDir = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = path.resolve(rootDir, "../..");

function apiProxy(target: string) {
  return {
    target,
    bypass(req: { url?: string; method?: string; headers?: { accept?: string } }) {
      const url = req.url ?? "";
      const accept = req.headers?.accept ?? "";
      const method = req.method ?? "GET";
      if (isSpaNavigation(url, accept, method)) {
        return "/index.html";
      }
      return undefined;
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, "");
  const apiTarget = `http://${env.API_HOST ?? "127.0.0.1"}:${env.API_PORT ?? "8010"}`;

  return {
    envDir: repoRoot,
    plugins: [react()],
    resolve: {
      alias: {
        "@assets": path.resolve(repoRoot, "assets"),
      },
    },
    server: {
      host: "127.0.0.1",
      port: Number(env.WEB_PORT ?? 5174),
      strictPort: true,
      proxy: {
        "/health": apiProxy(apiTarget),
        "/sessions": apiProxy(apiTarget),
        "/registry": apiProxy(apiTarget),
        "/settings": apiProxy(apiTarget),
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
    },
  };
});
