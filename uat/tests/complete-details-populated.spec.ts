// uat/tests/complete-details-populated.spec.ts — proves the POPULATED path of
// the Complete Details record screen (Ardee-like: intelligence_profile
// non-null, RHP + SBI verbatim evidence, valuation computed, decision stored,
// listing pending). Complements complete-details.spec.ts (the empty/edge path).
import { test, expect, noHorizontalOverflow } from "./_base";

const ISIN = "INE00ARDEE1";
const rich = {
  schema_version: "ipo-details-v1",
  generated_at: "2026-08-13",
  identity: { isin: ISIN, symbol: "ARDEE", company_name: "Ardee Engineering Ltd", listing_date: { state: "AVAILABLE", value: "2026-08-25", reason: null, source: "ipo" } },
  issue: {
    issue_price: { state: "AVAILABLE", value: 425, source: "ipo_issue" },
    band_low: { state: "AVAILABLE", value: 404, source: "ipo_issue" },
    band_high: { state: "AVAILABLE", value: 425, source: "ipo_issue" },
    issue_size_cr: { state: "AVAILABLE", value: 1101.28, source: "ipo_issue" },
    fresh_issue_cr: { state: "AVAILABLE", value: 120, source: "ipo_issue" },
    ofs_cr: { state: "AVAILABLE", value: 981.28, source: "ipo_issue" },
    lot_size: { state: "AVAILABLE", value: 35, source: "ipo_issue" },
    face_value: { state: "AVAILABLE", value: 2, source: "ipo_issue" },
    reservation_split: { state: "MISSING", value: null, reason: "Current NSE ingestion does not retain noOfSharesOffered.", source: "NSE ingestion" },
  },
  intelligence_profile: {
    schema_version: "ipo-profile:v1",
    financials: { reported_pat_cr: 181.28, reported_debt_cr: 200, cash_cr: 50, ebitda_cr: 260 },
    valuation: {
      status: "AVAILABLE", classification: "DETERMINISTIC_PRO_FORMA",
      reported_pat_cr: 181.28, pro_forma_pat_cr: 190.5, reported_debt_cr: 200, post_ipo_debt_cr: 150, cash_cr: 50, net_debt_cr: 100,
      reported_eps: 15.06, pro_forma_eps: 15.8, reported_pe: 28.2, pro_forma_pe: 26.9, ev_ebitda: 18.4, roe: 21.3, roce: 24.5, fcf_cr: 88,
      post_issue_shares_cr: 12, fair_value: 505, margin_of_safety_pct: 15.8, missing_inputs: [],
      formulas: { pe: "issue_price / EPS", eps: "PAT / post_issue_shares" },
    },
    provenance: { financial_period: "31-Mar-25", financial_basis: "consolidated", post_issue_shares_cr: { rhp_eps_field: "eps_post", alignment_warning: "PAT period/basis and RHP EPS period may not be perfectly aligned." } },
  },
  ai_analysis: { state: "AVAILABLE", findings: { summary: "Established engineering franchise with improving return ratios.", risks: ["client concentration", "working-capital intensity"] }, model: "sonnet", prompt_version: "v2-full", confidence: 0.88, analyzed_at: "2026-08-10", red_flag_count: 1, junk_signals: [] },
  verified_evidence: [
    { excerpt: "The objects of the issue include repayment of borrowings aggregating to Rs. 120 crore.", page_number: 42, doc_id: 1, document: { doc_type: "rhp", url: "https://example.test/rhp.pdf" }, category: "objects", direction: "neutral", source_type: "RHP" },
    { excerpt: "We assign a fair value of Rs. 505 based on 32x FY25 earnings, in line with listed peers.", page_number: 7, doc_id: 2, document: { doc_type: "sbi_note", url: "https://example.test/sbi.pdf" }, category: "valuation", direction: "positive", source_type: "SBI" },
  ],
  governance_and_risk: {
    sebi_actions: { state: "AVAILABLE", value: ["No SEBI action on record for the promoter group."], reason: null, source: "rhp_findings.findings", as_of: "2026-08-10" },
    litigation: { state: "AVAILABLE", value: ["Two pending civil matters below materiality threshold."], reason: null, source: "rhp_findings.findings" },
    related_party: { state: "AVAILABLE", value: ["Related-party lease with promoter entity disclosed."], reason: null, source: "rhp_findings.findings" },
    auditor_qualifications: { state: "AVAILABLE", value: ["No finding extracted for auditor qualifications."], reason: null, source: "rhp_findings.findings" },
    going_concern: { state: "AVAILABLE", value: ["No finding extracted for going concern."], reason: null, source: "rhp_findings.findings" },
    contingent_liabilities: { state: "AVAILABLE", value: ["Contingent liabilities at 4% of net worth."], reason: null, source: "rhp_findings.findings" },
    promoter_concerns: { state: "AVAILABLE", value: ["No finding extracted for promoter concerns."], reason: null, source: "rhp_findings.findings" },
  },
  decision: {
    verdict: { state: "AVAILABLE", value: "GOOD", reason: null, source: "decisions", as_of: "2026-08-11" },
    reasons: { state: "AVAILABLE", value: ["quality_score above threshold", "clean RHP gate"], reason: null, source: "decisions" },
    evidence: { state: "AVAILABLE", value: { quality_score: 31, rhp_gate: "accept" }, reason: null, source: "decisions" },
    kill_reason: { state: "MISSING", value: null, reason: "kill_reason applies only to JUNK decisions.", source: "derived" },
  },
  valuation: {
    score: { state: "AVAILABLE", value: 3, source: "valuation", as_of: "2026-08-06" },
    band: { state: "AVAILABLE", value: "FAVOURABLE", source: "valuation" },
    engine_version: { state: "AVAILABLE", value: "v2-score-2", source: "valuation" },
    computed_at: { state: "AVAILABLE", value: "2026-08-06", source: "valuation" },
    pe: { state: "VENDOR_FALLBACK", value: 23, reason: "Issue-size-derived proxy; not a disclosed or reported company ratio.", source: "valuation", provenance: { label: "Issue-size-derived proxy" } },
    pb: { state: "AVAILABLE", value: 3.2, source: "valuation" },
    pe_source: { state: "AVAILABLE", value: "proxy:issue_size/pat", source: "valuation" },
    pb_source: { state: "AVAILABLE", value: "rhp_computed:price/nav_per_share", source: "valuation" },
    peer_median_pe: { state: "AVAILABLE", value: 22, source: "valuation" },
    fair_value_low: { state: "AVAILABLE", value: 480, source: "valuation" },
    fair_value_high: { state: "AVAILABLE", value: 540, source: "valuation" },
    inputs_used: { state: "AVAILABLE", value: { rhp_eps: 15.06, peer_median_pe: 22 }, source: "valuation" },
    missing_inputs: { state: "AVAILABLE", value: [], source: "valuation" },
    margin_of_safety: { state: "AVAILABLE", value: { mos_low_pct: 12.9, mos_high_pct: 27.1, formula: "(fair_value - issue_price) / issue_price * 100" }, reason: null, source: "derived" },
  },
  listing_outcome: {
    listing_open: { state: "PENDING", value: null, reason: "Listing outcome listing_open is pending until the IPO lists.", source: "listing_outcomes" },
    gap_pct: { state: "PENDING", value: null, reason: "Listing outcome gap_pct is pending until the IPO lists.", source: "listing_outcomes" },
    d1_close: { state: "PENDING", value: null, reason: "pending until the IPO lists.", source: "listing_outcomes" },
    ceiling_20: { state: "PENDING", value: null, reason: "pending until the IPO lists.", source: "listing_outcomes" },
  },
  gmp: { state: "STALE", available: false, last_updated: "2026-07-24", reason: "No maintained live source" },
};

async function open(page: import("@playwright/test").Page) {
  await page.route("**/api/ipo/details/**", (r) => r.fulfill({ json: rich }));
  await page.goto(`/dashboard/ipo2/details/${ISIN}`);
  await expect(page.getByRole("heading", { name: "Ardee Engineering Ltd" })).toBeVisible();
}

test("populated: shipped sections render real values, not stubs", async ({ watched: page }) => {
  await open(page);
  // Issue overview: a shipped scalar renders its value.
  await expect(page.getByText("₹425", { exact: false }).first()).toBeVisible();
  // Presentation-derived, labeled pro-forma: market cap = 425 × 12 Cr shares.
  await expect(page.getByText("₹5,100 Cr")).toBeVisible();
  await expect(page.getByText("₹14,875")).toBeVisible(); // lot value = 35 × 425
  // §3 evidence-class labels are visually present.
  await expect(page.getByText("VERIFIED FACT").first()).toBeVisible();
  await expect(page.getByText("DETERMINISTIC PRO-FORMA").first()).toBeVisible();
  // §4 qualitative band, no percentage.
  await expect(page.getByText("FAVOURABLE").first()).toBeVisible();
  // proxy ratio is flagged as a proxy, not a real ratio.
  await expect(page.getByText("Issue-size-derived proxy").first()).toBeVisible();
  // canonical pro-forma fair value distinct from the house fair value.
  await expect(page.getByText("₹505")).toBeVisible();
});

test("populated: an ABSENT field shows its MISSING reason, never a zero", async ({ watched: page }) => {
  await open(page);
  await expect(page.getByText("Current NSE ingestion does not retain noOfSharesOffered.").first()).toBeVisible();
  // Missing-data register is present but collapsed by design (progressive
  // disclosure); expanding it reveals the filling producer for each gap.
  const reg = page.getByRole("heading", { name: "Missing-data register" });
  await expect(reg).toBeVisible();
  await reg.click();
  await expect(page.getByText("RHP financial-table extraction").first()).toBeVisible();
});

test("populated: RHP and SBI verbatim excerpts render with page + source", async ({ watched: page }) => {
  await open(page);
  await expect(page.getByText("Verified excerpt, p.42")).toBeVisible();
  await expect(page.getByText("repayment of borrowings aggregating to Rs. 120 crore", { exact: false })).toBeVisible();
  await expect(page.getByText("Verified excerpt, p.7")).toBeVisible();
  await expect(page.getByText("fair value of Rs. 505", { exact: false })).toBeVisible();
  // SBI is attributed distinctly (its own labeled section + source badge).
  await expect(page.getByRole("heading", { name: "SBI evidence" })).toBeVisible();
});

test("populated: no JSON blob or [object Object] reaches the DOM", async ({ watched: page }) => {
  await open(page);
  // Scope to the rendered record — excludes Next.js framework script payloads.
  const text = await page.getByTestId("complete-details").innerText();
  expect(text, "[object Object] leaked").not.toContain("[object Object]");
  expect(text, "raw JSON object leaked").not.toContain('{"');
  expect(text, "raw key:value blob leaked").not.toContain('"quality_score"');
  // The object-valued evidence field renders as a labeled row instead.
  expect(text, "object rendered as labeled rows").toContain("Quality score");
  expect(text).toContain("31");
});

test("populated: verdict is displayed as stored, not relabeled; no win-rate %", async ({ watched: page }) => {
  await open(page);
  await expect(page.getByText("GOOD", { exact: true }).first()).toBeVisible();
  const body = (await page.locator("body").innerText()).toLowerCase();
  for (const phrase of ["% win", "win rate", "win-rate", "% edge", "of 10 worked", "backtest", "72.7%", "+17.2%"]) {
    expect(body, `forbidden performance phrase present: ${phrase}`).not.toContain(phrase);
  }
});

test.describe("populated at 380px", () => {
  test.use({ viewport: { width: 380, height: 900 } });
  test("dense record screen has no horizontal overflow at 380px", async ({ watched: page }) => {
    await open(page);
    await noHorizontalOverflow(page);
    // Evidence stays expanded by default on mobile (progressive disclosure, not truncation).
    await expect(page.getByText("Verified excerpt, p.42")).toBeVisible();
  });
});
