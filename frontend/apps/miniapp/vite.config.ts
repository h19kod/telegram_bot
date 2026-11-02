import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Backend for the dev proxy (end-to-end tests point it at their own server).
const API = process.env.SOP_API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    proxy: {
      "/api": API,
      "/media": API,
    },
  },
  build: { target: "es2022", sourcemap: true },
  test: { environment: "jsdom", globals: true },
});
