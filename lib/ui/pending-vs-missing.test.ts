// lib/ui/pending-vs-missing.test.ts — the pending-vs-missing sweep.
//
// The owner's live Complete Details screen for Molbio (ipo_id 1100) read
// "Issue price — not available — Data is not available from the current V2
// source." Molbio had simply not been priced yet, so the sentence described a
// defect that did not exist. These tests pin the two halves of the fix: the
// generic producer default is replaced by a lifecycle-specific sentence, and
// DetailField.state is never rewritten to make that happen.
import test from "node:test";
import assert from "node:assert/strict";
import {
  absenceCopy, lifecycleFacts, isGenericReason, buildMissingRegister,
  GENERIC_ABSENCE_REASON, HONEST_REASON_KEYS, LIFECYCLE_UNKNOWN,
  type DetailField,
} from "./details-format";

/** How the producer's `field()` helper stamps an absent scalar. */
const producerMissing = (source: string): DetailField =>
  ({ state: "MISSING", value: null, reason: GENERIC_ABSENCE_REASON, source, as_of: null });

/** A pre-listing record: every listing_outcome leaf is PENDING, no issue price. */
const preListing = {
  identity: { listing_date: producerMissing("ipo") },
  issue: { issue_price: producerMissing("ipo_issue"), band_low: producerMissing("ipo_issue") },
  valuation: { score: producerMissing("valuation") },
  listing_outcome: {
    listing_open: { state: "PENDING", value: null, reason: "Listing outcome listing_open is pending until the IPO lists.", source: "listing_outcomes" },
    gap_pct: { state: "PENDING", value: null, reason: "Listing outcome gap_pct is pending until the IPO lists.", source: "listing_outcomes" },
  },
};

/** A listed record: the outcome leaves are no longer PENDING, and it was priced. */
const listed = {
  identity: { listing_date: { state: "AVAILABLE", value: "2026-07-10", source: "ipo" } },
  issue: { issue_price: { state: "AVAILABLE", value: 460, source: "ipo_issue" }, band_low: producerMissing("ipo_issue") },
  valuation: { score: producerMissing("valuation") },
  listing_outcome: {
    listing_open: { state: "AVAILABLE", value: 470, source: "listing_outcomes" },
    best_close: { state: "MISSING", value: null, reason: "Listing outcome best_close is unavailable because no computed outcome is stored.", source: "listing_outcomes" },
  },
};

test("lifecycle is read from the payload, never from a clock", () => {
  assert.deepEqual(lifecycleFacts(preListing), { listed: false, priced: false });
  assert.deepEqual(lifecycleFacts(listed), { listed: true, priced: true });
  // No listing_outcome branch at all asserts nothing either way.
  assert.deepEqual(lifecycleFacts({ issue: {} }), { listed: null, priced: false });
  assert.deepEqual(lifecycleFacts(null), { listed: null, priced: false });
});

test("the producer's generic default is recognised; a written reason is not", () => {
  assert.equal(isGenericReason(GENERIC_ABSENCE_REASON), true);
  assert.equal(isGenericReason(null), true);
  assert.equal(isGenericReason(""), true);
  assert.equal(isGenericReason("Current NSE ingestion does not retain noOfSharesOffered."), false);
});

test("Molbio: an unpriced issue reads as pending, not as a broken source", () => {
  const copy = absenceCopy("issue.issue_price", preListing.issue.issue_price, lifecycleFacts(preListing));
  assert.equal(copy.lead, "pending");
  assert.equal(copy.reason, "pending — set when the issue is priced");
  assert.equal(copy.producer, "ipo_issue");
  assert.ok(!copy.reason!.includes("V2 source"));
});

test("the same field on a LISTED IPO is a real gap, and names the producer", () => {
  const copy = absenceCopy("issue.band_low", listed.issue.band_low, lifecycleFacts(listed));
  assert.equal(copy.lead, "not available");
  assert.equal(copy.reason, "No price band is recorded for this IPO in the issue record.");
  assert.equal(copy.producer, "ipo_issue");
});

test("valuation waits on the issue price, not on the listing", () => {
  const pending = absenceCopy("valuation.score", preListing.valuation.score, lifecycleFacts(preListing));
  assert.equal(pending.lead, "pending");
  assert.match(pending.reason!, /scoring engine runs on the issue price/);
  // Priced and still absent: the engine owed a row and there is none.
  const gap = absenceCopy("valuation.score", listed.valuation.score, lifecycleFacts(listed));
  assert.equal(gap.lead, "not available");
  assert.equal(gap.reason, "No v2-score valuation row is stored for this IPO.");
});

test("decision.verdict says what the producer already says about its siblings", () => {
  const copy = absenceCopy("decision.verdict", producerMissing("decisions"), lifecycleFacts(listed));
  assert.equal(copy.lead, "pending");
  assert.equal(copy.reason, "pending — a persisted decision is not yet available");
});

test("a reason the producer actually wrote is never overwritten", () => {
  const f: DetailField = { state: "MISSING", value: null, reason: "Current NSE ingestion does not retain noOfSharesOffered.", source: "NSE ingestion" };
  const copy = absenceCopy("issue.reservation_split", f, lifecycleFacts(preListing));
  assert.equal(copy.reason, "Current NSE ingestion does not retain noOfSharesOffered.");
  assert.equal(copy.lead, "not available");
  assert.equal(copy.producer, "NSE ingestion");
});

test("an unknown field keeps the payload's own sentence, generic included", () => {
  const copy = absenceCopy("issue.some_future_field", producerMissing("ipo_issue"), lifecycleFacts(preListing));
  assert.equal(copy.reason, GENERIC_ABSENCE_REASON);
  assert.equal(copy.lead, "not available");
});

test("a PENDING payload state keeps its lead word even with no book entry", () => {
  const f: DetailField = { state: "PENDING", value: null, reason: "AI analysis has not yet run.", source: "rhp_findings.findings" };
  assert.deepEqual(absenceCopy(undefined, f, LIFECYCLE_UNKNOWN),
    { lead: "pending", reason: "AI analysis has not yet run.", producer: "rhp_findings.findings" });
});

test("no substitution ever changes DetailField.state", () => {
  const before = JSON.stringify(preListing);
  for (const key of HONEST_REASON_KEYS) absenceCopy(key, preListing.issue.issue_price, lifecycleFacts(preListing));
  assert.equal(JSON.stringify(preListing), before, "the payload must be read-only to the copy layer");
  assert.equal(preListing.issue.issue_price.state, "MISSING");
});

test("the sweep covers every field the producer stamps with its generic default", () => {
  assert.deepEqual([...HONEST_REASON_KEYS], [
    "decision.verdict",
    "identity.listing_date",
    "issue.band_high", "issue.band_low", "issue.face_value", "issue.fresh_issue_cr",
    "issue.issue_price", "issue.issue_size_cr", "issue.lot_size", "issue.ofs_cr",
    "valuation.band", "valuation.computed_at", "valuation.engine_version",
    "valuation.fair_value_low", "valuation.fair_value_high", "valuation.inputs_used",
    "valuation.missing_inputs", "valuation.pb_source", "valuation.pe_source",
    "valuation.peer_median_pe", "valuation.score",
  ].sort());
});

test("the missing-data register quotes the same sentence the row shows", () => {
  const rows = buildMissingRegister(preListing as unknown as Record<string, unknown>);
  const price = rows.find((r) => r.field === "Issue: Issue price");
  assert.ok(price, "the unpriced issue must appear in the register");
  assert.equal(price!.reason, "pending — set when the issue is priced");
  assert.equal(price!.producer, "ipo_issue");
  for (const row of rows) assert.ok(!row.reason.includes("V2 source"), `generic reason leaked: ${row.field}`);
});
