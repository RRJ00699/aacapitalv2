// Visual regression — gated behind UAT_VISUAL=1 because baselines must be
// generated once (npx playwright test uat/tests/visual --update-snapshots)
// and committed; PR runs then fail on unexpected pixel drift (>2%).
import { test, expect } from "./_base";

test.skip(!process.env.UAT_VISUAL, "set UAT_VISUAL=1 after committing baselines");

test("visual · command center", async ({ watched: page }) => {
  await page.goto("/dashboard/ipo2");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveScreenshot("command-center.png", { fullPage: true });
});
