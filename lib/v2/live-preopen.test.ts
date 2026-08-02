import test from "node:test";
import assert from "node:assert/strict";
import { scoreStatic, marginOfSafety, scoreLive, confidence, scoreListing } from "./live-preopen";

// REAL rows captured from misty-meadow for listing_date 2026-07-30 (the query the
// route runs). They exercise the full money path end-to-end on real data — the
// route only adds live broker depth on top of scoreListing().
const INDOMIM = {
  ipo_id: 85, company_name: "Indo-MIM Ltd.", nse_symbol: "INDOMIM", listing_date: "2026-07-30",
  issue_size_cr: 3811.21, ofs_cr: 3311.21, fresh_cr: 500.0, issue_price: 485.0, anchor_count: null,
  ipo_pe: 44.95, peer_median_pe: null, roe: 18.92, debt_equity: 0.39, revenue_cagr_3y: 7.65, ofs_pct: 86.88,
  eps_post: 10.79, pe_source: "rhp_computed:price/eps_post", listing_open: 700.0, rhp_gate: "reject",
};
const LCL = {
  ipo_id: 42, company_name: "Lohia Corp Ltd.", nse_symbol: "LCL", listing_date: "2026-07-30",
  issue_size_cr: 1101.28, ofs_cr: 1101.28, fresh_cr: null, issue_price: 425.0, anchor_count: null,
  ipo_pe: 5.69, peer_median_pe: null, roe: null, debt_equity: null, revenue_cagr_3y: 21.36, ofs_pct: 100.0,
  eps_post: null, pe_source: "proxy:issue_size/pat", listing_open: 461.0, rhp_gate: "watch",
};

test("scoreStatic: mega + 50 anchors + fresh passes the key static rules", () => {
  const s = scoreStatic({ issue_size_cr: 2500, anchor_count: 55, ofs_pct: 10, issue_price: 250, ipo_pe: 40, rhp_gate: "accept" });
  assert.equal(s.isMega, true);
  assert.equal(s.has30, true);
  assert.equal(s.rhpReject, false);
  assert.ok(s.rules.find((r) => r.name === "Reasonable P/E (≤70)")?.passed === true);
});

test("scoreStatic: RHP JUNK (mapped to 'reject') hard-flags rhpReject", () => {
  const s = scoreStatic({ issue_size_cr: 2500, anchor_count: 40, ofs_pct: 10, issue_price: 250, ipo_pe: 40, rhp_gate: "reject" });
  assert.equal(s.rhpReject, true);
});

test("marginOfSafety: GMP fallback removed — no modeled FV falls to issue-price floor and flags gmpRemoved", () => {
  // no eps/pe/peer -> fairValue null -> issue-price floor anchor
  const mos = marginOfSafety({ issue_price: 100, listing_open: 90 });
  assert.equal(mos.anchorSource, "issue-price-floor");
  assert.equal(mos.gmpRemoved, true);
  assert.equal(mos.fairAnchor, 100);
  assert.equal(mos.mosPct, 11.1); // (100/90 - 1) * 100
  assert.match(mos.note, /GMP-implied fallback removed/);
});

test("marginOfSafety: modeled FV used when valuation inputs present", () => {
  const mos = marginOfSafety({ issue_price: 100, listing_open: 100, eps_post: 5, peer_median_pe: 25, roe: 20, revenue_cagr_3y: 25, debt_equity: 0.2, ofs_pct: 10 });
  assert.equal(mos.anchorSource, "modeled");
  assert.ok((mos.fairAnchor ?? 0) > 100); // 5 * 25 * quality/structure uplift
});

test("scoreLive: euphoric open (>=50%) does not pass 'Opening positive'", () => {
  const mos = marginOfSafety({ issue_price: 100, listing_open: 160 });
  const lv = scoreLive({ issue_price: 100, listing_open: 160 }, mos);
  assert.equal(lv.euphoric, true);
  assert.equal(lv.rules.find((r) => r.name === "Opening positive")?.passed, false);
});

test("confidence: rhpReject hard-kills to 0", () => {
  assert.equal(confidence([{ name: "x", passed: true, win: 90, detail: "" }], true, false, false), 0);
});

test("scoreListing REAL DATA — INDOMIM (RHP=JUNK): hard-killed to confidence 0 despite +44% open", () => {
  const r = scoreListing(INDOMIM);
  assert.equal(r.sym, "INDOMIM");
  assert.equal(r.rhp_reject, true);
  assert.equal(r.confidence, 0);                 // RHP reject overrides the strong open
  assert.equal(r.open_pct, 44.3);
  assert.equal(r.mos.anchor_source, "issue-price-floor"); // peer P/E null -> no modeled FV
  assert.equal(r.gmp.available, false);          // explicit, never omitted
  assert.ok(r.avoid_flags.some((a) => a.includes("OFS-heavy")));
  assert.equal(r.pe_source, "rhp_computed:price/eps_post");
});

test("scoreListing REAL DATA — LCL: proxy pe_source is disclosed, not laundered", () => {
  const r = scoreListing(LCL);
  assert.equal(r.pe_source, "proxy:issue_size/pat"); // disclosure survives to the response
  assert.equal(r.rhp_reject, false);
  assert.equal(r.gmp.available, false);
  assert.ok(r.avoid_flags.some((a) => a.includes("OFS-heavy")));
  assert.equal(r.confidence, 44);
});

test("scoreListing REAL DATA — true pre-open state (no listing_open yet) awaits the open", () => {
  const { listing_open, ...preOpen } = INDOMIM; void listing_open;
  const r = scoreListing(preOpen);
  assert.equal(r.open_pct, null);                // open not yet known
  assert.equal(r.mos.pct, null);                 // MoS awaits the open price
  assert.equal(r.gmp.available, false);          // still explicit
});
