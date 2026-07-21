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
    await expect(page.locator("#ipocard-UATGOOD")).toBeVisible(); // navigated, not stuck
  });

  test("J2 · quality + lifecycle filters combine", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    const box = page.getByRole("combobox", { name: /search ipos/i });
    await box.click();
    await page.getByRole("button", { name: "GOOD" }).click();
    await expect(page.getByRole("option")).toHaveCount(1);
    await expect(page.getByRole("option").first()).toContainText("UAT Complete Ltd");
    await page.getByRole("button", { name: "Upcoming" }).click(); // combines
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
    await expect(complete).toContainText("RHP evidence · the document's own words");
    await expect(complete).toContainText("will not receive any proceeds"); // quoted excerpt renders
    const incomplete = page.locator("#ipocard-UATINC");
    await expect(incomplete).toContainText("SBI research note not available or not yet parsed.");
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
    await expect(page.getByText("Research incomplete")).toBeVisible();
    await expect(page.getByText("WATCH, not BUY")).toBeVisible();
  });

  test("J9 · Post-Listing view renders outcomes for listed IPOs", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await page.getByRole("button", { name: /switch to post-listing/i }).click();
    await expect(page.locator(`#postrow-${"UATPOST".toLowerCase() === "uatpost" ? "UATPOST" : "UATPOST"}`).first()
      .or(page.getByText("UAT Listed Ltd"))).toBeVisible();
  });

  test("J10 · rules disclose backtest sample sizes (n=) and win rates", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    // Existing disclosure: every graded band shows n= and win %. Full
    // table/date-range/version provenance is tracker item F3 (UAT_TRACKER).
    await expect(page.getByText(/n=\d+/).first()).toBeVisible();
    await expect(page.getByText(/\d+% /).first()).toBeVisible();
  });

  test("layout · no horizontal overflow on any project viewport", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2");
    await noHorizontalOverflow(page);
  });
});

test.describe("Complete Details + street news (2026-07-22)", () => {
  test("J11 · deep link opens details; missing fields render em-dash with source; news links out", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2?view=details&ipo=UATGOOD");
    await expect(page.getByText("Issue structure")).toBeVisible();
    await expect(page.getByText("Lot size")).toBeVisible();
    await expect(page.getByText(/pending \(Chittorgarh/).first()).toBeVisible(); // honest gap, named source
    const link = page.getByRole("link", { name: /debuts above expectations/i });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", /reuters\.com/);
    await expect(page.getByText("linked & summarized, never scraped")).toBeVisible();
  });

  test("J12 · details for the incomplete IPO invents nothing", async ({ watched: page }) => {
    await page.goto("/dashboard/ipo2?view=details&ipo=UATINC");
    await expect(page.getByText("QUALITY: INCOMPLETE")).toBeVisible();
    await expect(page.getByText("No street report available yet")).toBeVisible();
    await expect(page.getByText("pending analysis")).toBeVisible(); // evidence gap named
  });
});
