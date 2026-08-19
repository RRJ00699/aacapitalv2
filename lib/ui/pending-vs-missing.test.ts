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
  absenceCopy, absenceLine, lifecycleFacts, isGenericReason, buildMissingRegister,
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
  const pre = lifecycleFacts(preListing);
  assert.equal(pre.listed, false);
  assert.equal(pre.priced, false);
  const post = lifecycleFacts(listed);
  assert.equal(post.listed, true);
  assert.equal(post.priced, true);
  assert.ok(post.filed.has("issue.issue_price"));
  assert.ok(post.filed.has("listing_outcome.listing_open"));
  assert.equal(post.filed.has("issue.band_low"), false); // absent leaves are not "filed"
  // No listing_outcome branch at all asserts nothing either way.
  assert.equal(lifecycleFacts({ issue: {} }).listed, null);
  assert.equal(lifecycleFacts(null).listed, null);
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
  // The RENDERED line, not a substring of it — a reason that carried its own
  // "pending" prefix produced "pending — pending — …" on screen.
  assert.equal(absenceLine(copy), "pending — set when the issue is priced");
  assert.equal(copy.producer, "ipo_issue");
});

test("no reason ever carries its own lead word, so no line can say it twice", () => {
  const both = [lifecycleFacts(preListing), lifecycleFacts(listed)];
  for (const key of HONEST_REASON_KEYS) {
    for (const facts of both) {
      const line = absenceLine(absenceCopy(key, { state: "MISSING", value: null, reason: GENERIC_ABSENCE_REASON, source: "x" }, facts));
      assert.ok(!/^(pending|not available) — (pending|not available)\b/.test(line), `doubled lead on ${key}: ${line}`);
      assert.ok(!line.includes("V2 source"), `generic reason survived on ${key}`);
    }
  }
});

test("a filed sibling withdraws the lifecycle excuse — a pure OFS is not pending", () => {
  // Priced, pre-listing, all-OFS: fresh_cr is absent because there IS no fresh
  // issue, not because the offer document has not been filed.
  const pureOfs = {
    issue: {
      issue_price: { state: "AVAILABLE", value: 460, source: "ipo_issue" },
      issue_size_cr: { state: "AVAILABLE", value: 900, source: "ipo_issue" },
      ofs_cr: { state: "AVAILABLE", value: 900, source: "ipo_issue" },
      fresh_issue_cr: producerMissing("ipo_issue"),
      band_low: producerMissing("ipo_issue"),
    },
    listing_outcome: { listing_open: { state: "PENDING", value: null, reason: "pending until the IPO lists.", source: "listing_outcomes" } },
  };
  const facts = lifecycleFacts(pureOfs);
  assert.equal(facts.listed, false); // still pre-listing …
  const fresh = absenceCopy("issue.fresh_issue_cr", pureOfs.issue.fresh_issue_cr, facts);
  assert.equal(fresh.lead, "not available"); // … but the OFS side is filed
  assert.match(fresh.reason!, /pure offer for sale has no fresh-issue amount/);
  // Same rule for a band on an already-priced issue.
  const band = absenceCopy("issue.band_low", pureOfs.issue.band_low, facts);
  assert.equal(band.lead, "not available");
  assert.match(band.reason!, /fixed-price issue has no band/);
});

test("with nothing filed, the same two fields ARE pending", () => {
  const facts = lifecycleFacts(preListing);
  assert.equal(absenceLine(absenceCopy("issue.fresh_issue_cr", producerMissing("ipo_issue"), facts)),
    "pending — the fresh-issue amount is set when the offer document is filed");
  assert.equal(absenceLine(absenceCopy("issue.band_low", preListing.issue.band_low, facts)),
    "pending — set when the price band is announced");
});

test("the same field on a LISTED IPO is a real gap, and names the producer", () => {
  const copy = absenceCopy("issue.band_low", listed.issue.band_low, lifecycleFacts(listed));
  assert.equal(copy.lead, "not available");
  assert.match(copy.reason!, /No low end of the price band is recorded/);
  assert.equal(copy.producer, "ipo_issue");
});

test("valuation waits on the issue price, not on the listing", () => {
  const pending = absenceCopy("valuation.score", preListing.valuation.score, lifecycleFacts(preListing));
  assert.equal(absenceLine(pending),
    "pending — the v2 scoring engine runs on the issue price, which is not set yet");
  // Priced and still absent: the engine owed a row and there is none.
  const gap = absenceCopy("valuation.score", listed.valuation.score, lifecycleFacts(listed));
  assert.equal(gap.lead, "not available");
  assert.equal(gap.reason, "No v2-score valuation row is stored for this IPO.");
});

test("decision.verdict says what the producer already says about its siblings", () => {
  const copy = absenceCopy("decision.verdict", producerMissing("decisions"), lifecycleFacts(listed));
  assert.equal(absenceLine(copy), "pending — a persisted decision is not yet available");
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

test("absenceLine never leaves a dangling dash when there is no reason", () => {
  assert.equal(absenceLine({ lead: "not available", reason: null, producer: null }), "not available");
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
