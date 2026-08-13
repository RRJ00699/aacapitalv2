// uat/tests/journeys.spec.ts — the 10 real user journeys from the owner's
// UAT brief, driven against the seeded fixture server (zero Neon).
import { test, expect, noHorizontalOverflow } from "./_base";

test.describe("AACapital user journeys", () => {
  test("J1+J4 · search finds an IPO and the row click opens the stage destination", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    const box = page.getByRole("combobox", { name: /search ipos/i });
    await box.click();
    await box.fill("UATGOOD");
    const option = page.getByRole("option").first();
    await expect(option).toContainText("UAT Complete Ltd");
    await expect(option).toContainText("Open Command Center"); // stage-aware, never generic View
    await option.click();
    // pick() navigates via the aac:focus-ipo custom event — the URL NEVER
    // changes (components/features/ipo-search.tsx pick -> onSelect -> event).
    // Assert the outcome: the command card (or its title) becomes visible.
    await expect(page.locator("#ipocard-UATGOOD")).toBeVisible({ timeout: 10_000 });
  });

  test("J2 · quality + lifecycle filters combine", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    const box = page.getByRole("combobox", { name: /search ipos/i });
    await box.click();
    await page.getByRole("button", { name: "GOOD" }).click();
    await expect(page.getByRole("option")).toHaveCount(1);
    await expect(page.getByRole("option").first()).toContainText("UAT Complete Ltd");
    await page.getByRole("button", { name: "Upcoming", exact: true }).click(); // combines (strict: pill vs chip)
    await expect(page.getByRole("option").first()).toContainText("UAT Complete Ltd");
  });

  test("J3 · incomplete research NEVER surfaces as GOOD", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    const box = page.getByRole("combobox", { name: /search ipos/i });
    await box.click();
    await box.fill("UATINC");
    const option = page.getByRole("option").first();
    await expect(option).toContainText("QUALITY: INCOMPLETE");
    await expect(option).not.toContainText(/\bGOOD\b/);
    await box.fill("");
    await page.getByRole("button", { name: "GOOD" }).click();
    await expect(page.getByRole("listbox")).not.toContainText("UAT Incomplete Ltd");
  });

  test("J5 · Command Center: research states, fair value, evidence with source", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    const complete = page.locator("#ipocard-UATGOOD");
    const exp1 = complete.getByRole("button", { name: /RHP \+ SBI research/ });
    if (await exp1.count()) { await exp1.first().scrollIntoViewIfNeeded(); await exp1.first().click(); } // expander (skip if already open)
    await expect(complete.getByText("RHP · quoted").first()).toBeVisible();
    await expect(complete.locator('[title*="will not receive any proceeds"]').first()).toBeVisible();
    const incomplete = page.locator("#ipocard-UATINC");
    const exp2 = incomplete.getByRole("button", { name: /RHP \+ SBI research/ });
    if (await exp2.count()) { await exp2.first().scrollIntoViewIfNeeded(); await exp2.first().click(); }
    // card copy evolved (CI evidence 2026-07-24): incompleteness now reads as
    // the honest inline verdict, not the old SBI-note sentence
    await expect(incomplete).toContainText("research signal, not a buy call");
    await expect(incomplete).toContainText("RHP not yet read");
    await expect(incomplete).toContainText("awaiting"); // FV never fakes a number
  });

  test("J6 · raw OFS fact stays neutral without evidence", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    const incomplete = page.locator("#ipocard-UATINC");
    await expect(incomplete).toContainText("pending RHP analysis"); // the pending lane
    await expect(incomplete).not.toContainText(/cash-?out/i); // never invented intent
  });

  test("J7+J8 · Live blocks on incomplete research; issue-price floor never yields MoS", async ({ watched: page }) => {
    const res = await page.request.get("/api/ipo/live-preopen");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    const l = (body.listings || [])[0];
    expect(l, "fixture LISTING row must be served").toBeTruthy();
    expect(l.research_ready).toBe(false);
    expect(l.research_missing.join(" ")).toContain("fair value inputs");
    expect(l.mos.anchor_source).toBe("issue-price-floor");
    expect(l.mos.pct).toBeNull(); // labeled floor, never a margin
    await page.goto("/dashboard/ipo2");
    await page.getByRole("button", { name: /switch to live/i }).click();
    // stage 1: does fixture-Live serve the listing at all?
    await expect(page.getByText("UAT Listing Ltd").first(), "fixture-Live must serve the IST-today listing")
      .toBeVisible({ timeout: 10_000 });
    // stage 2: the safety banner on that listing
    await expect(page.getByText("Research incomplete")).toBeVisible();
    await expect(page.getByText("WATCH, not BUY")).toBeVisible();
  });

  test("J9 · Post-Listing view renders outcomes for listed IPOs", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await page.getByRole("button", { name: /switch to post-listing/i }).click();
    await expect(page.locator("#postrow-UATPOST")
      .or(page.getByText("UAT Listed Ltd")).first()).toBeVisible(); // .first AFTER the union (strict mode)
  });

  test("J10 · grade ladder is shown; no fabricated backtest n=/win-rates in the engine strip", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    // W4 truthfulness: the pre-listing grade is explained qualitatively. Cohort
    // win-rates and hard-coded sample sizes (n=) are NOT displayed until a
    // validated backtest field ships in the payload (docs/runbooks/PROJECT_CONTROL.md).
    await expect(page.getByText(/Every IPO gets a grade before it lists/i)).toBeVisible();
    await expect(page.getByText(/of 10 worked/i)).toHaveCount(0);
    await expect(page.getByText(/based on how 370/i)).toHaveCount(0);
    await expect(page.getByText(/Validated cohort win-rates are not shown/i)).toBeVisible();
  });

  test("layout · no horizontal overflow on any project viewport", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await noHorizontalOverflow(page);
  });
});

test.describe("Complete Details + street news (2026-07-22)", () => {
  test("J11 · legacy deep link resolves to the immutable ISIN-backed Details page", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2?view=details&ipo=UATGOOD");
    const link = page.getByRole("link", { name: /Open Complete Details/i });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/dashboard/ipo2/details/INE000000011");
  });

  test("J12 · incomplete IPO still resolves by exact ISIN without inventing a record", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2?view=details&ipo=UATINC");
    const link = page.getByRole("link", { name: /Open Complete Details/i });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/dashboard/ipo2/details/INE000000029");
  });
});
