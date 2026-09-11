import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 本地开发：vite (5173) 代理到 FastAPI (8000)
// 生产部署：相对路径 /api 由 Vercel rewrite 到 serverless 函数
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { "/api": "http://localhost:8000" }, allowedHosts: true },
  preview: { proxy: { "/api": "http://localhost:8000" }, allowedHosts: true },
});
