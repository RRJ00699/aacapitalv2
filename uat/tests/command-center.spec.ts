// uat/tests/command-center.spec.ts — W4 truthfulness + mobile-first (380px) +
// screen-state honesty, driven against the seeded fixture server.
import { test, expect, noHorizontalOverflow } from "./_base";

// Uncontracted historical-performance claims that must NOT appear anywhere in
// the UI until strategy_backtest{cohort,win_rate,n,median} ships as an evidenced
// producer field (docs/runbooks/PROJECT_CONTROL.md §4c). Includes the reworded
// "X of 10 worked" grade-card stats and the band-percentage line.
const FORBIDDEN = [
  "77% edge",
  "77% win",
  "92% win",
  "85% with a near-zero",
  "8.1 of 10 worked",
  "72.7%",
  "respected 78",
  "based on how 370",
  "of 10 worked",
  "n=370",
  "70%",
  "73%",
  "79%",
  "81%",
  "15 years",
  "370 IPOs",
];

test.describe("Command Center — truthfulness", () => {
  test("no fabricated win-rate / edge claims on the main view", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await expect(page.getByRole("heading", { name: /IPO Command Center/i })).toBeVisible();
    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const phrase of FORBIDDEN) {
      expect(body, `forbidden phrase present: ${phrase}`).not.toContain(phrase.toLowerCase());
    }
  });

  test("no fabricated stats in the Playbook view", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await page.getByRole("button", { name: /Switch to Playbook/i }).click();
    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const phrase of FORBIDDEN) {
      expect(body, `forbidden phrase present: ${phrase}`).not.toContain(phrase.toLowerCase());
    }
    // The playbook still exists — it just describes setups qualitatively.
    await expect(page.getByText(/House Rules/i)).toBeVisible();
  });

  test("three-verdict separation is preserved (filter pills)", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    // Command view is default; the verdict filter row carries the distinct verdicts.
    for (const v of ["TRADE", "WATCH", "CAUTION", "AVOID"]) {
      await expect(page.getByRole("button", { name: v, exact: true }).first()).toBeVisible();
    }
  });
});

test.describe("Command Center — mobile-first at 380px", () => {
  test.use({ viewport: { width: 380, height: 780 } });

  test("no horizontal overflow at 380px on the command view", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await expect(page.getByRole("heading", { name: /IPO Command Center/i })).toBeVisible();
    await noHorizontalOverflow(page);
  });

  test("no horizontal overflow at 380px on the Playbook view", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await page.getByRole("button", { name: /Switch to Playbook/i }).click();
    await noHorizontalOverflow(page);
  });
});
