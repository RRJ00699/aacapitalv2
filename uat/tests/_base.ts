// Shared UAT harness: every test auto-fails on console errors, page
// exceptions, failed API requests and layout overflow — the silent killers.
import { test as base, expect, type Page } from "@playwright/test";

export const test = base.extend<{ watched: Page }>({
  watched: async ({ page }, use) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const failedRequests: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300)); });
    page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 300)));
    page.on("response", (r) => {
      if (r.url().includes("/api/") && r.status() >= 500) failedRequests.push(`${r.status()} ${r.url()}`);
    });
    await use(page);
    expect(pageErrors, "unhandled page exceptions").toEqual([]);
    expect(failedRequests, "failed API requests (5xx)").toEqual([]);
    const known = consoleErrors.filter((e) => !/favicon|manifest|hydrat/i.test(e));
    expect(known, "browser console errors").toEqual([]);
  },
});
export { expect };

export async function noHorizontalOverflow(page: Page) {
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "layout overflow (horizontal scroll)").toBeLessThanOrEqual(1);
}
