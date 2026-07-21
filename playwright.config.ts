import { defineConfig, devices } from "@playwright/test";

// AACapital UAT — deterministic, fixture-served, zero Neon / paid APIs.
// `npm run uat:all` drives this; CI installs Chromium and blocks merges.
const PORT = Number(process.env.UAT_PORT || 4123);
const BASE = process.env.UAT_BASE_URL || `http://localhost:${PORT}`;
const isSmoke = !!process.env.UAT_BASE_URL; // smoke = external URL, read-only

export default defineConfig({
  testDir: "uat/tests",
  outputDir: "uat-report/artifacts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["html", { outputFolder: "uat-report", open: "never" }], ["list"]],
  use: {
    baseURL: BASE,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
  // Fixture server for PR runs; smoke runs point UAT_BASE_URL at a deploy.
  webServer: isSmoke ? undefined : {
    command: "node uat/serve.mjs",
    url: `${BASE}/api/ipo-command`,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { ...devices["iPad (gen 7)"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
  ],
});
