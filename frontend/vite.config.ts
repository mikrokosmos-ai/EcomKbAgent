/**
 * Vite 开发与构建配置
 * 双服务代理：/import-api → import 服务，/query-api → query 服务。
 * 后端「all」模式两路由都在 8000；拆分模式 import=8000、query=8001，用环境变量覆盖。
 */
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const importTarget = env.VITE_DEV_IMPORT_TARGET || "http://127.0.0.1:8000";
  const queryTarget = env.VITE_DEV_QUERY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/import-api": {
          target: importTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/import-api/, ""),
        },
        "/query-api": {
          target: queryTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/query-api/, ""),
        },
      },
    },
  };
});
