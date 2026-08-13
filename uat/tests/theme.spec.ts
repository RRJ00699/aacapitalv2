// uat/tests/theme.spec.ts — theme v1 contract: system / light / dark, no
// hydration flash, manual override persists across reload, OS changes honoured.
import { test, expect } from "./_base";

const KEY = "aac-theme";

async function dataTheme(page: import("@playwright/test").Page) {
  return page.evaluate(() => document.documentElement.getAttribute("data-theme"));
}

test.describe("theme v1", () => {
  test("manual Dark overrides and persists across reload", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    // The one theme control is an accessible radiogroup.
    const group = page.getByRole("radiogroup", { name: /theme/i });
    await expect(group).toBeVisible();
    await group.getByRole("radio", { name: /dark/i }).click();
    await expect.poll(() => dataTheme(page)).toBe("dark");
    await expect.poll(() => page.evaluate((k) => localStorage.getItem(k), KEY)).toBe("dark");

    await page.reload();
    // Persists — and the pre-paint boot script sets it before React hydrates.
    await expect.poll(() => dataTheme(page)).toBe("dark");
  });

  test("manual Light overrides the OS even in a dark-preferring browser", async ({ browser }) => {
    const ctx = await browser.newContext({ colorScheme: "dark" });
    const page = await ctx.newPage();
    await page.goto("/dashboard/ipo2");
    await page.getByRole("radiogroup", { name: /theme/i }).getByRole("radio", { name: /light/i }).click();
    await expect.poll(() => page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe("light");
    await ctx.close();
  });

  test("System mode follows prefers-color-scheme and stamps no data-theme", async ({ browser }) => {
    const ctx = await browser.newContext({ colorScheme: "dark" });
    const page = await ctx.newPage();
    await page.goto("/dashboard/ipo2");
    await page.getByRole("radiogroup", { name: /theme/i }).getByRole("radio", { name: /system/i }).click();
    // System removes the explicit attribute; the CSS media query drives the palette.
    await expect.poll(() => page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBeNull();
    // With a dark OS preference the effective color-scheme is dark.
    const scheme = await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
    expect(scheme).toContain("dark");
    await ctx.close();
  });

  test("no hydration mismatch: pre-set Dark shows no flash to light", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    // Seed the choice before the app ever loads (addInitScript runs pre-navigation).
    await page.addInitScript(() => localStorage.setItem("aac-theme", "dark"));
    await page.goto("/dashboard/ipo2");
    // The boot script runs in <head> before paint, so the very first observable
    // attribute is already dark — there is no light frame to reconcile.
    expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe("dark");
    await ctx.close();
  });
});
