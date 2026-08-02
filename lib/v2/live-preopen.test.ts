import test from "node:test";
import assert from "node:assert/strict";
import { scoreStatic, marginOfSafety, scoreLive, confidence } from "./live-preopen";

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
