import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    server: {
      host: env.VITE_DEV_HOST || "0.0.0.0",
      port: Number(env.VITE_DEV_PORT || 5173),
      proxy: env.VITE_API_BASE_URL
        ? {
            "/command": {
              target: env.VITE_API_BASE_URL,
              changeOrigin: true
            },
            "/tanks": {
              target: env.VITE_API_BASE_URL,
              changeOrigin: true
            },
            "/health": {
              target: env.VITE_API_BASE_URL,
              changeOrigin: true
            }
          }
        : undefined
    }
  };
});
