// Post-deploy smoke: READ-ONLY. `npm run uat:smoke -- --base-url=<URL>`
// (UAT_BASE_URL env). GETs only — never mutates production data.
import { test, expect } from "./_base";

test.skip(!process.env.UAT_BASE_URL, "smoke runs only against an explicit base URL");

test("smoke · dashboard renders and the API answers", async ({ watched: page }) => {
  await page.goto("/dashboard/ipo2");
  await expect(page.getByText("IPO Command Center")).toBeVisible();
  const res = await page.request.get("/api/ipo-command");
  expect([200, 401]).toContain(res.status()); // edge answered; auth gate ok
});
