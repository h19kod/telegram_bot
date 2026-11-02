/**
 * End-to-end tests: real backend (own *_e2e database, reset and seeded per run) + Mini App +
 * dashboard dev servers. Run with `npm run e2e` (PostgreSQL and Redis must be up).
 */
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const BACKEND = resolve(__dirname, "../backend");
const API_PORT = 8100;
export const MINIAPP = "http://localhost:5180";
export const DASHBOARD = "http://localhost:5181";

function e2eDatabaseUrl(): string {
  if (process.env.E2E_DATABASE_URL) return process.env.E2E_DATABASE_URL;
  const env = readFileSync(resolve(__dirname, "../.env"), "utf8");
  const dev = /^DATABASE_URL=(.+)$/m.exec(env)?.[1]?.trim();
  if (!dev) throw new Error("DATABASE_URL missing from .env (or set E2E_DATABASE_URL)");
  return dev.replace(/\/[^/?]+(\?|$)/, "/sop_e2e$1");
}

// The config is evaluated by the runner and again by every worker: seed only once and hand the
// result to workers through the environment.
if (!process.env.SOP_E2E) {
  const password = `E2e-${randomBytes(9).toString("base64url")}`;
  const out = execFileSync(
    "uv",
    ["run", "python", "manage.py", "e2e_reset", "--owner-password", password],
    { cwd: BACKEND, env: { ...process.env, DATABASE_URL: e2eDatabaseUrl() }, encoding: "utf8" },
  );
  process.env.SOP_E2E = JSON.stringify({ ...JSON.parse(out), owner_password: password });
}
const seed = JSON.parse(process.env.SOP_E2E);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: { trace: "retain-on-failure", screenshot: "only-on-failure", locale: "en-US" },
  projects: [{ name: "chromium", use: { ...devices["Pixel 7"], browserName: "chromium" } }],
  webServer: [
    {
      command: `uv run uvicorn config.asgi:application --port ${API_PORT}`,
      cwd: BACKEND,
      env: { DATABASE_URL: e2eDatabaseUrl() },
      url: `http://127.0.0.1:${API_PORT}/readyz`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev -w @sop/miniapp -- --port 5180 --strictPort",
      env: {
        SOP_API_PROXY: `http://127.0.0.1:${API_PORT}`,
        VITE_DEV_INIT_DATA: seed.init_data,
        VITE_DEV_BUSINESS: seed.slug,
      },
      url: MINIAPP,
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -w @sop/dashboard -- --port 5181 --strictPort",
      env: { SOP_API_PROXY: `http://127.0.0.1:${API_PORT}` },
      url: DASHBOARD,
      reuseExistingServer: false,
    },
  ],
});
