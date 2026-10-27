import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a real stack: this config starts the Vite dev
// server, but Postgres, Redis and the API must already be up (`make up`). That
// split is deliberate — Playwright can start a dev server, it cannot bring up a
// database, and a suite that silently tests a half-running system is worse than
// one that refuses to start. `e2e/global-setup.ts` enforces it.

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // These tests share one seeded tenant and some of them write to it, so they run
  // serially. Parallelism here would make the budget spec flake against itself.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "pnpm dev",
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
