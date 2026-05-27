import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          mantine: ["@mantine/core", "@mantine/hooks", "@tabler/icons-react"],
          tauri: ["@tauri-apps/api", "@tauri-apps/plugin-opener", "@tauri-apps/plugin-positioner"],
        },
      },
    },
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    proxy: {
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
        changeOrigin: false,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
