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

    // Admin Operations (via the fixture-only preview harness). Healthy uses the
    // seeded snapshot; desktop + 380px.
    for (const [w, tag] of [[1440, "desktop"], [380, "380"]] as const) {
      test(`admin ops · ${tag} · healthy · ${mode}`, async ({ page }) => {
        await page.setViewportSize({ width: w, height: 900 });
        await setTheme(page, mode);
        await page.goto("/uat/ops-preview");
        await page.getByRole("heading", { name: /Admin · Operations/i }).waitFor();
        await page.waitForTimeout(500);
        await page.screenshot({ path: `${DIR}/admin-${tag}-healthy-${mode}.png`, fullPage: true });
      });
    }
  }

  // Screen states of the Admin overview (light desktop), driven by mocking the
  // KV snapshot response.
  test("admin ops · degraded snapshot → UNKNOWN", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setTheme(page, "light");
    await page.route("**/api/ipo-command", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ degraded: "snapshot unavailable", cards: [] }) }));
    await page.goto("/uat/ops-preview");
    await page.getByText(/UNKNOWN/).first().waitFor();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${DIR}/admin-desktop-degraded.png`, fullPage: true });
  });

  test("admin ops · request failed → UNAVAILABLE", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setTheme(page, "light");
    await page.route("**/api/ipo-command", (r) => r.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
    await page.goto("/uat/ops-preview");
    await page.getByText(/unavailable/i).first().waitFor();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${DIR}/admin-desktop-unavailable.png`, fullPage: true });
  });

  test("admin ops · loading", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setTheme(page, "light");
    // Hold the snapshot response so the loading state is on screen when captured.
    await page.route("**/api/ipo-command", async (r) => {
      await new Promise((res) => setTimeout(res, 2500));
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ cards: [] }) });
    });
    await page.goto("/uat/ops-preview");
    await page.getByText(/Loading operations snapshot/i).waitFor();
    await page.screenshot({ path: `${DIR}/admin-desktop-loading.png`, fullPage: true });
  });
});
