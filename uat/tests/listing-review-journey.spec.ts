// uat/tests/listing-review-journey.spec.ts — the Listing Review / journey
// screen. Two fixtures drive it: a DATA-RICH listed IPO (five daily sessions +
// a computed listing outcome + a fired top-structure observation) and an
// EMPTY/PENDING one (no candles, outcome pending pre-listing, no observation).
// Both are served by intercepting the two KV-only routes the screen consumes —
// /api/ipo/journey (sym -> ISIN + candles) and /api/ipo/details/<ISIN>.
import { test, expect, noHorizontalOverflow } from "./_base";

const ISIN = "INE000000045";
const available = (value: unknown, extra: Record<string, unknown> = {}) =>
  ({ state: "AVAILABLE", value, reason: null, source: "listing_outcomes", ...extra });

// A listed IPO with real candles. `series` mirrors computeJourney(): the route
// returns date/high/low/close per bar, and `entry` is the only open that survives.
const richJourney = {
  ok: true, hasData: true, sym: "UATPOST", isin: ISIN, entry: 470,
  series: [
    { date: "2026-07-10", high: 512, low: 448, close: 498 },
    { date: "2026-07-13T00:00:00.000Z", high: 521, low: 486, close: 515 },
    { date: "2026-07-14", high: 530, low: 495, close: 502 },
    { date: "2026-07-15", high: 508, low: 470, close: 476 },
    { date: "2026-07-16", high: 489, low: 462, close: 484 },
  ],
  level_observation: {
    ipo_id: 45,
    observed_at: "2026-07-16T10:00:00Z",
    payload: {
      detector_version: "topout-online-researched-v1",
      evaluated_through_bar: "2026-07-16T15:15:00+05:30",
      label: "DISCOVERY",
      state: "TOP", alert: true, alert_bar: 37, alert_price: 476, watch_kind: null,
      promoted: false, invalidated: false, max_state: "SOW_FIRE", fire_path: "SOW",
      trigger: { state: "SOW_FIRE", path: "SOW", bc_high: 530, ar_low: 495, retest_high: 508, volume_ratio: 0.62, bars_since_bc: 9, trigger_strength: 10.2 },
    },
  },
};

const richDetails = {
  schema_version: "ipo-details-v1",
  generated_at: "2026-07-18",
  identity: { isin: ISIN, symbol: "UATPOST", company_name: "UAT Listed Ltd", listing_date: { state: "AVAILABLE", value: "2026-07-10", source: "ipo" } },
  issue: { issue_price: { state: "AVAILABLE", value: 460, source: "ipo_issue" } },
  listing_outcome: {
    listing_open: available(470),
    gap_pct: available(2.2),
    d1_close: available(498),
    best_close: available(515),
    worst_close: available(476),
    ceiling_20: available(552, { label: "Historical ceiling indicator — non-executable" }),
    // Cohort / backtest-flavoured fields ARE in the contract and must stay off this screen.
    pool: available("2026H1"),
    winner_35: available(false),
    hold_positive_vs_open: available(true),
    computed_at: available("2026-07-18"),
    dataset_version: available("v2"),
  },
  gmp: { state: "STALE", available: false, last_updated: "2026-07-24", reason: "No maintained live source" },
};

// The honest-gap fixture: nothing has traded, nothing was detected.
const emptyJourney = {
  ok: true, sym: "UATPOST", hasData: false, isin: ISIN,
  note: "No candles yet — the journey begins once it lists and trades.",
  level_observation: null,
};

const pendingDetails = {
  ...richDetails,
  identity: { ...richDetails.identity, listing_date: { state: "AVAILABLE", value: "2026-09-01", source: "ipo" } },
  listing_outcome: {
    listing_open: { state: "PENDING", value: null, reason: "Listing outcome listing_open is pending until the IPO lists.", source: "listing_outcomes" },
    gap_pct: { state: "PENDING", value: null, reason: "Listing outcome gap_pct is pending until the IPO lists.", source: "listing_outcomes" },
    d1_close: { state: "PENDING", value: null, reason: "Listing outcome d1_close is pending until the IPO lists.", source: "listing_outcomes" },
    best_close: { state: "MISSING", value: null, reason: "Listing outcome best_close is unavailable because no computed outcome is stored.", source: "listing_outcomes" },
    worst_close: { state: "MISSING", value: null, reason: "Listing outcome worst_close is unavailable because no computed outcome is stored.", source: "listing_outcomes" },
    ceiling_20: { state: "PENDING", value: null, reason: "Listing outcome ceiling_20 is pending until the IPO lists.", source: "listing_outcomes", label: "Historical ceiling indicator — non-executable" },
  },
};

type Page = import("@playwright/test").Page;

/** How the OPTIONAL details request behaves. Journey is the required half. */
type DetailsMode = "ok" | "notFound" | "reject" | "malformed";

async function routeReview(page: Page, journey: unknown, details: unknown | null, mode: DetailsMode = "ok",
                           journeyMode: "ok" | "reject" = "ok") {
  await page.route("**/api/ipo/journey*", (r) =>
    journeyMode === "reject" ? r.abort("failed") : r.fulfill({ json: journey as object }));
  await page.route("**/api/ipo/details/*", (r) => {
    if (mode === "reject") return r.abort("failed");
    if (mode === "malformed") return r.fulfill({ status: 200, contentType: "application/json", body: '{"schema_version": "ipo-deta' });
    if (mode === "notFound" || !details)
      return r.fulfill({ status: 404, json: { state: "not_found", isin: ISIN, error: "Details snapshot not found" } });
    return r.fulfill({ json: details as object });
  });
  await page.goto("/dashboard/ipo2?ipo=UATPOST");
  await page.getByRole("button", { name: /Switch to Listing Review/i }).click();
}

async function openReview(page: Page, journey: unknown, details: unknown | null, mode: DetailsMode = "ok") {
  await routeReview(page, journey, details, mode);
  await expect(page.getByTestId("listing-review")).toBeVisible();
}

const review = (page: Page) => page.getByTestId("listing-review");

test.describe("Listing Review — data-rich listed IPO", () => {
  test("listing-day outcome renders the shipped values, gap included", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    const panel = review(page);
    await expect(panel.getByText("₹460", { exact: false }).first()).toBeVisible(); // issue price
    await expect(panel.getByText("₹470", { exact: false }).first()).toBeVisible(); // listing open
    await expect(panel.getByText("2.2%", { exact: false }).first()).toBeVisible();  // producer's own gap_pct
    await expect(panel.getByText("₹498", { exact: false }).first()).toBeVisible(); // day-1 close
    await expect(panel.getByText("₹515", { exact: false }).first()).toBeVisible(); // best close
    await expect(panel.getByText("₹476", { exact: false }).first()).toBeVisible(); // worst close
    // AVAILABLE renders the VALUE, never a stub.
    await expect(panel.getByText("AVAILABLE").first()).toBeVisible();
    await expect(panel.getByText("not available")).toHaveCount(0);
    // ceiling_20 keeps the producer's own non-executable label.
    await expect(panel.getByText("₹552", { exact: false }).first()).toBeVisible();
    await expect(panel.getByText("Historical ceiling indicator — non-executable").first()).toBeVisible();
    // The gap is shipped, so nothing is derived on top of it.
    await expect(panel.getByText("Gap (derived)")).toHaveCount(0);
  });

  test("cohort / backtest-flavoured outcome fields never reach this screen", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    const text = await review(page).innerText();
    for (const phrase of ["Winner", "winner_35", "Pool", "2026H1", "Held positive", "hold_positive_vs_open"]) {
      expect(text, `cohort field leaked onto the review screen: ${phrase}`).not.toContain(phrase);
    }
  });

  test("first-five-session tape renders daily bars and states what KV does not carry", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    const panel = review(page);
    for (const session of ["D0", "D1", "D2", "D3", "D4"]) {
      await expect(panel.getByRole("rowheader", { name: session })).toBeVisible();
    }
    await expect(panel.getByRole("cell", { name: "2026-07-10", exact: true })).toBeVisible();
    await expect(panel.getByRole("cell", { name: "2026-07-13", exact: true })).toBeVisible(); // ISO timestamp trimmed to the day
    await expect(panel.getByRole("cell", { name: "+8.3%", exact: true })).toBeVisible(); // 498 vs issue 460
    await expect(panel.getByRole("cell", { name: "+3.4%", exact: true })).toBeVisible(); // 515 vs previous close 498
    // The honest coverage line: no fabricated volume, no fake 15-minute bars.
    const note = panel.getByText(/per-bar open and volume are not in its response/);
    await expect(note).toBeVisible();
    await expect(note).toContainText("15-minute bars are not published to KV");
    // The tape's columns are exactly what the route carries — no invented volume
    // column. ("Volume ratio" elsewhere is the detector's own trigger field.)
    await expect(panel.locator("table thead th")).toHaveText(["Session", "Date", "High", "Low", "Close", "vs issue", "vs prev close"]);
    expect(await panel.locator("table").innerText(), "volume must not be invented in the tape").not.toContain("Volume");
  });

  test("top observations mirror the detector's own DISCOVERY label and stay non-executable", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    const panel = review(page);
    await expect(panel.getByText("Top observations", { exact: true })).toBeVisible();
    await expect(panel.getByText("DISCOVERY", { exact: true }).first()).toBeVisible();
    await expect(panel.getByText("TOP", { exact: true }).first()).toBeVisible();
    await expect(panel.getByText(/distribution structure/).first()).toBeVisible();
    // Trigger detail arrives as labeled rows, not a blob.
    await expect(panel.getByText("Trigger detail")).toBeVisible();
    await expect(panel.getByText("Bc high")).toBeVisible();
    await expect(panel.getByText("530").first()).toBeVisible();
    await expect(panel.getByText(/not executable signals/)).toBeVisible();
    // Top only — the bottom mirror is out of production scope.
    await expect(panel.getByText(/bottom mirror is out of production scope/)).toBeVisible();
    await expect(panel.getByText("topout-online-researched-v1", { exact: false })).toBeVisible();
  });

  test("no JSON blob or [object Object] reaches the DOM", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    const text = await review(page).innerText();
    expect(text, "[object Object] leaked").not.toContain("[object Object]");
    expect(text, "raw JSON object leaked").not.toContain('{"');
    expect(text, "raw key:value blob leaked").not.toContain('"trigger"');
    expect(text, "the trigger object renders as labeled rows").toContain("Volume ratio");
  });

  test("no win-rate / backtest percentage renders on the review screen", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    const panel = (await review(page).innerText()).toLowerCase();
    for (const phrase of ["% win", "win rate", "win-rate", "% edge", "of 10 worked", "backtest", "72.7%", "+17.2%", "expected win"]) {
      expect(panel, `forbidden performance phrase on the review screen: ${phrase}`).not.toContain(phrase);
    }
    // The measured-statistic strings pinned by the #334 regression must not
    // appear anywhere on the page either. (The page's own "cohort win-rates are
    // not shown" disclaimer is honest copy, not a statistic, so it stays.)
    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const phrase of ["% win", "of 10 worked", "72.7%", "+17.2%", "n=370"]) {
      expect(body, `forbidden performance statistic on the page: ${phrase}`).not.toContain(phrase);
    }
    const html = await page.content();
    for (const phrase of ["72.7% win", "+17.2%", "win ·"]) {
      expect(html, `forbidden phrase in rendered HTML (attr/tooltip): ${phrase}`).not.toContain(phrase);
    }
  });
});

test.describe("Listing Review — honest gaps", () => {
  test("no candles gives ONE honest line, never a blank chart", async ({ watched: page }) => {
    await openReview(page, emptyJourney, pendingDetails);
    const panel = review(page);
    await expect(panel.getByText("Candle data not yet available.")).toBeVisible();
    await expect(panel.getByText(/No candles yet/)).toBeVisible();
    await expect(panel.locator("table")).toHaveCount(0);
    await expect(panel.getByRole("rowheader", { name: "D0" })).toHaveCount(0);
  });

  test("PENDING and MISSING outcomes render their reason, never a zero", async ({ watched: page }) => {
    await openReview(page, emptyJourney, pendingDetails);
    const panel = review(page);
    await expect(panel.getByText("Listing outcome listing_open is pending until the IPO lists.", { exact: false })).toBeVisible();
    await expect(panel.getByText("no computed outcome is stored", { exact: false }).first()).toBeVisible();
    await expect(panel.getByText("PENDING").first()).toBeVisible();
    await expect(panel.getByText("MISSING").first()).toBeVisible();
    const text = await panel.innerText();
    expect(text, "a pending price must not render as ₹0").not.toContain("₹0");
    // With no shipped gap and no listed open, the derived gap refuses too.
    expect(text).toContain("Gap (derived)");
    expect(text).toContain("not available —");
  });

  test("no observation gives an honest empty state, not an invented signal", async ({ watched: page }) => {
    await openReview(page, emptyJourney, pendingDetails);
    const panel = review(page);
    await expect(panel.getByText(/No top-structure observation is recorded/)).toBeVisible();
    await expect(panel.getByText("Trigger detail")).toHaveCount(0);
    await expect(panel.getByText(/bottom mirror is out of production scope/)).toBeVisible();
  });

  // The raw `page` fixture, not `watched`: a 404 from the details route is the
  // expected honest-gap path, and the browser logs every 404 to the console.
  test("a missing details snapshot is stated, and the tape still renders", async ({ page }) => {
    await openReview(page, richJourney, null);
    const panel = review(page);
    await expect(panel.getByText(/No ipo-details-v1 snapshot is published for INE000000045/)).toBeVisible();
    // Candles are independent of the details record, so the tape survives.
    await expect(panel.getByRole("rowheader", { name: "D0" })).toBeVisible();
    // Without an issue price, the vs-issue column stays blank rather than assuming one.
    await expect(panel.getByText(/vs-issue column stays blank/)).toBeVisible();
  });
});

test.describe("Listing Review — the details request has its OWN failure boundary", () => {
  // The details record fills ONE section. A failure there must never discard the
  // journey candles and the top-structure observation the screen already holds;
  // only a failed/malformed JOURNEY request may fail the whole screen.
  // These three use the raw `page` fixture, not `watched`: an aborted request is
  // logged to the browser console by design, and that noise is the simulation,
  // not an app error. Every other test in this file keeps the console guard.
  async function expectJourneyHalfIntact(page: Page) {
    const panel = review(page);
    await expect(panel.getByTestId("listing-review")).toHaveCount(0); // sanity: `panel` IS the record
    for (const session of ["D0", "D1", "D2", "D3", "D4"]) {
      await expect(panel.getByRole("rowheader", { name: session })).toBeVisible();
    }
    await expect(panel.getByRole("cell", { name: "₹498", exact: true })).toBeVisible();
    await expect(panel.getByText("DISCOVERY", { exact: true }).first()).toBeVisible();
    await expect(panel.getByText("TOP", { exact: true }).first()).toBeVisible();
    await expect(panel.getByText(/distribution structure/).first()).toBeVisible();
    // Nothing outcome-dependent is invented in the details record's absence.
    // (₹470 / ₹476 are NOT listed here: those are candle values the journey
    // snapshot itself carries, and they must keep rendering.)
    const text = await panel.innerText();
    for (const fabricated of ["₹460", "₹552", "2.2%", "₹0", "AVAILABLE"]) {
      expect(text, `outcome value invented with no details record: ${fabricated}`).not.toContain(fabricated);
    }
  }

  test("details fetch REJECTS → tape and TOP observation survive", async ({ page }) => {
    await openReview(page, richJourney, richDetails, "reject");
    await expect(review(page).getByText(/could not be read/)).toBeVisible();
    await expect(review(page).getByText(/Nothing below is affected/)).toBeVisible();
    await expectJourneyHalfIntact(page);
    // The whole-screen error must NOT have been rendered.
    await expect(page.getByText("Listing review unavailable")).toHaveCount(0);
  });

  test("details returns MALFORMED JSON → tape and TOP observation survive", async ({ page }) => {
    await openReview(page, richJourney, richDetails, "malformed");
    await expect(review(page).getByText(/could not be read/)).toBeVisible();
    await expectJourneyHalfIntact(page);
    await expect(page.getByText("Listing review unavailable")).toHaveCount(0);
  });

  test("a failed JOURNEY request — and only that — fails the whole screen", async ({ page }) => {
    await routeReview(page, richJourney, richDetails, "ok", "reject");
    await expect(page.getByText("Listing review unavailable")).toBeVisible();
    await expect(page.getByTestId("listing-review")).toHaveCount(0);
  });
});

test.describe("Listing Review at 380px", () => {
  test.use({ viewport: { width: 380, height: 900 } });

  test("the data-rich review has no horizontal overflow at 380px", async ({ watched: page }) => {
    await openReview(page, richJourney, richDetails);
    await noHorizontalOverflow(page);
    // Content stays present at mobile width — narrowed, not truncated.
    await expect(review(page).getByRole("rowheader", { name: "D0" })).toBeVisible();
    await expect(review(page).getByText("₹470", { exact: false }).first()).toBeVisible();
  });

  test("the empty review has no horizontal overflow at 380px", async ({ watched: page }) => {
    await openReview(page, emptyJourney, pendingDetails);
    await noHorizontalOverflow(page);
    await expect(review(page).getByText("Candle data not yet available.")).toBeVisible();
  });

  test("the details-degraded review has no horizontal overflow at 380px", async ({ page }) => {
    await openReview(page, richJourney, richDetails, "reject");
    await noHorizontalOverflow(page);
    await expect(review(page).getByRole("rowheader", { name: "D0" })).toBeVisible();
  });
});
