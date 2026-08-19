// uat/tests/pending-vs-missing-reasons.spec.ts — the owner's Molbio complaint,
// pinned end to end.
//
// The live Complete Details screen for Molbio (ipo_id 1100) rendered
//   "Issue price — not available — Data is not available from the current V2 source."
// on an IPO that had simply not been priced yet. That sentence is the producer's
// DEFAULT for "no reason written", and it read like a defect report.
//
// These tests drive two records through the real screen: an unpriced, unlisted
// one (Molbio-shaped) and a listed, priced one. The pending sentence must be
// specific, the genuine-gap sentence must name the producer, and neither may
// change the state badge the payload shipped.
import { test, expect, noHorizontalOverflow } from "./_base";

const GENERIC = "Data is not available from the current V2 source.";
const ISIN = "INE00MOLB101";

/** Exactly what lib/v2/ipo-details.ts `field()` writes for an absent scalar. */
const producerMissing = (source: string) => ({ state: "MISSING", value: null, reason: GENERIC, source, as_of: null });
const outcomePending = (name: string) =>
  ({ state: "PENDING", value: null, reason: `Listing outcome ${name} is pending until the IPO lists.`, source: "listing_outcomes" });

// Molbio: announced, not yet priced, not yet listed. Every absence here is the
// lifecycle, not a broken source.
const unpriced = {
  schema_version: "ipo-details-v1",
  generated_at: "2026-08-19",
  intelligence_profile: null,
  identity: { isin: ISIN, symbol: "MOLBIO", company_name: "Molbio Diagnostics Ltd", listing_date: producerMissing("ipo") },
  issue: {
    issue_price: producerMissing("ipo_issue"),
    band_low: producerMissing("ipo_issue"),
    band_high: producerMissing("ipo_issue"),
    issue_size_cr: producerMissing("ipo_issue"),
    fresh_issue_cr: producerMissing("ipo_issue"),
    ofs_cr: producerMissing("ipo_issue"),
    lot_size: producerMissing("ipo_issue"),
    face_value: producerMissing("ipo_issue"),
    reservation_split: { state: "MISSING", value: null, reason: "Current NSE ingestion does not retain noOfSharesOffered.", source: "NSE ingestion" },
  },
  ai_analysis: { state: "PENDING", findings: null, model: null, prompt_version: null, confidence: null, analyzed_at: null, red_flag_count: null, junk_signals: [], reason: "AI analysis has not yet run." },
  verified_evidence: [],
  governance_and_risk: { litigation: { state: "PENDING", value: null, reason: "AI analysis has not yet run.", source: "rhp_findings.findings" } },
  decision: {
    verdict: producerMissing("decisions"),
    reasons: { state: "PENDING", value: null, reason: "A persisted decision is not yet available.", source: "decisions" },
    evidence: { state: "PENDING", value: null, reason: "A persisted decision is not yet available.", source: "decisions" },
    kill_reason: { state: "MISSING", value: null, reason: "kill_reason applies only to JUNK decisions.", source: "derived" },
  },
  valuation: {
    score: producerMissing("valuation"),
    band: producerMissing("valuation"),
    engine_version: producerMissing("valuation"),
    computed_at: producerMissing("valuation"),
    pe: { state: "MISSING", value: null, reason: "P/E could not be computed; see missing_inputs.", source: "valuation" },
    pb: { state: "MISSING", value: null, reason: "P/B could not be computed; see missing_inputs.", source: "valuation" },
    pe_source: producerMissing("valuation"),
    pb_source: producerMissing("valuation"),
    peer_median_pe: producerMissing("valuation"),
    fair_value_low: producerMissing("valuation"),
    fair_value_high: producerMissing("valuation"),
    inputs_used: producerMissing("valuation"),
    missing_inputs: producerMissing("valuation"),
    margin_of_safety: { state: "MISSING", value: null, reason: "Issue price and both fair-value bounds are required.", source: "derived" },
  },
  listing_outcome: {
    listing_open: outcomePending("listing_open"),
    gap_pct: outcomePending("gap_pct"),
    d1_close: outcomePending("d1_close"),
    best_close: outcomePending("best_close"),
    worst_close: outcomePending("worst_close"),
    computed_at: outcomePending("computed_at"),
  },
  gmp: { state: "STALE", available: false, last_updated: "2026-07-24", reason: "No maintained live source" },
};

// The same shapes on an IPO that HAS priced and listed: the lifecycle no longer
// explains anything, so the absences are real gaps and say so.
const listedWithGaps = {
  ...unpriced,
  identity: { ...unpriced.identity, listing_date: { state: "AVAILABLE", value: "2026-07-10", reason: null, source: "ipo" } },
  issue: { ...unpriced.issue, issue_price: { state: "AVAILABLE", value: 460, reason: null, source: "ipo_issue" } },
  listing_outcome: {
    listing_open: { state: "AVAILABLE", value: 470, reason: null, source: "listing_outcomes" },
    gap_pct: { state: "AVAILABLE", value: 2.2, reason: null, source: "listing_outcomes" },
    best_close: { state: "MISSING", value: null, reason: "Listing outcome best_close is unavailable because no computed outcome is stored.", source: "listing_outcomes" },
  },
};

type Page = import("@playwright/test").Page;
async function open(page: Page, body: unknown) {
  await page.route(`**/api/ipo/details/${ISIN}`, (r) => r.fulfill({ json: body as object }));
  await page.goto(`/dashboard/ipo2/details/${ISIN}`);
  await expect(page.getByTestId("complete-details")).toBeVisible();
}
const record = (page: Page) => page.getByTestId("complete-details");

test.describe("Complete Details — an unpriced, unlisted IPO", () => {
  test("the issue price reads as pending with its own reason, not the generic V2 line", async ({ watched: page }) => {
    await open(page, unpriced);
    await expect(record(page).getByText("pending — set when the issue is priced").first()).toBeVisible();
    const text = await record(page).innerText();
    expect(text, "the producer's generic default must not reach the screen").not.toContain(GENERIC);
    expect(text, "an unpriced issue must never render as a zero").not.toContain("₹0");
  });

  test("every lifecycle-explainable absence gets its own sentence", async ({ watched: page }) => {
    await open(page, unpriced);
    const text = await record(page).innerText();
    for (const sentence of [
      "pending — set when the issue is priced",
      "pending — set when the price band is announced",
      "pending — set when the issue size is filed with the offer document",
      "pending — the fresh-issue amount is set when the offer document is filed",
      "pending — the offer-for-sale amount is set when the offer document is filed",
      "pending — fixed with the price band",
      "pending — carried with the issue terms once they are filed",
      "pending — set when the exchange confirms the listing date",
      "pending — the v2 scoring engine runs on the issue price, which is not set yet",
      "pending — a persisted decision is not yet available",
    ]) {
      expect(text, `missing honest reason: ${sentence}`).toContain(sentence);
    }
  });

  test("the payload's own state badge is never rewritten by the copy", async ({ watched: page }) => {
    await open(page, unpriced);
    // issue_price ships MISSING and still shows MISSING, even though the row
    // now reads "pending — …". Only the sentence is the UI's.
    const row = record(page).locator(".drow", { hasText: "pending — set when the issue is priced" }).first();
    await expect(row.getByText("MISSING", { exact: true })).toBeVisible();
    // A field the producer itself marked PENDING keeps its PENDING badge.
    await expect(record(page).getByText("PENDING").first()).toBeVisible();
  });

  test("a reason the producer wrote itself is left alone", async ({ watched: page }) => {
    await open(page, unpriced);
    await expect(record(page).getByText("Current NSE ingestion does not retain noOfSharesOffered.").first()).toBeVisible();
    await expect(record(page).getByText("P/E could not be computed; see missing_inputs.").first()).toBeVisible();
  });

  test("the screen states how pending is decided, and no blob reaches the DOM", async ({ watched: page }) => {
    await open(page, unpriced);
    const text = await record(page).innerText();
    expect(text).toContain("No issue open / close date ships in v1");
    expect(text, "[object Object] leaked").not.toContain("[object Object]");
    expect(text, "raw JSON object leaked").not.toContain('{"');
  });

  test("the missing-data register repeats the same sentences, with the producer", async ({ watched: page }) => {
    await open(page, unpriced);
    const reg = page.getByRole("heading", { name: "Missing-data register" });
    await reg.click();
    const text = await record(page).innerText();
    expect(text).toContain("pending — set when the issue is priced");
    expect(text, "the register must not quote the generic default either").not.toContain(GENERIC);
    expect(text).toContain("ipo_issue");
  });
});

test.describe("Complete Details — a priced, listed IPO", () => {
  test("the same absent fields become real gaps, each naming its producer", async ({ watched: page }) => {
    await open(page, listedWithGaps);
    const text = await record(page).innerText();
    expect(text).toContain("No price band is recorded for this IPO in the issue record.");
    expect(text).toContain("No v2-score valuation row is stored for this IPO.");
    expect(text).toContain("producer: ipo_issue");
    expect(text).toContain("producer: valuation");
    // The lifecycle no longer excuses the price band, so nothing claims it is pending.
    expect(text).not.toContain("pending — set when the price band is announced");
    expect(text, "the generic default has no path to the screen").not.toContain(GENERIC);
  });

  test("AVAILABLE still renders its value, not a reason", async ({ watched: page }) => {
    await open(page, listedWithGaps);
    await expect(record(page).getByText("₹460").first()).toBeVisible();
    await expect(record(page).getByText("₹470").first()).toBeVisible();
  });
});

test.describe("honest reasons at 380px", () => {
  test.use({ viewport: { width: 380, height: 900 } });
  test("the pending record has no horizontal overflow at 380px", async ({ watched: page }) => {
    await open(page, unpriced);
    await noHorizontalOverflow(page);
    await expect(record(page).getByText("pending — set when the issue is priced").first()).toBeVisible();
  });
});
