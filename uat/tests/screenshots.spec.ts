// uat/tests/screenshots.spec.ts — OWNER-CHECK evidence generator.
// Gated behind UAT_SHOTS=1 so it never runs in the normal merge gate. Produces
// the Command Center in light + dark at 380px and desktop, plus the Playbook
// (truthfulness) view. Output lands in uat-shots/ (override with UAT_SHOTS_DIR).
//   UAT_SHOTS=1 npx playwright test uat/tests/screenshots.spec.ts --project=desktop
import { test } from "@playwright/test";

const RUN = process.env.UAT_SHOTS === "1";
const DIR = process.env.UAT_SHOTS_DIR || "uat-shots";

async function setTheme(page: import("@playwright/test").Page, mode: "light" | "dark" | "system") {
  await page.addInitScript((m) => localStorage.setItem("aac-theme", m), mode);
}

test.describe(RUN ? "screenshots" : "screenshots (skipped — set UAT_SHOTS=1)", () => {
  test.skip(!RUN, "set UAT_SHOTS=1 to generate");

  for (const mode of ["light", "dark"] as const) {
    test(`command center · desktop · ${mode}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await setTheme(page, mode);
      await page.goto("/dashboard/ipo2");
      await page.getByRole("heading", { name: /IPO Command Center/i }).waitFor();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${DIR}/command-desktop-${mode}.png`, fullPage: true });
    });

    test(`command center · 380px · ${mode}`, async ({ page }) => {
      await page.setViewportSize({ width: 380, height: 820 });
      await setTheme(page, mode);
      await page.goto("/dashboard/ipo2");
      await page.getByRole("heading", { name: /IPO Command Center/i }).waitFor();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${DIR}/command-380-${mode}.png`, fullPage: true });
    });

    test(`playbook · desktop · ${mode}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await setTheme(page, mode);
      await page.goto("/dashboard/ipo2");
      await page.getByRole("button", { name: /Switch to Playbook/i }).click();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${DIR}/playbook-desktop-${mode}.png`, fullPage: true });
    });
  }
});
