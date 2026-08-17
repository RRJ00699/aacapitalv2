// lib/ui/payload-field-contract.test.ts — the generalised candles_json guard.
//
// ListingReview spent months rendering an empty tape because it read
// `c.candles_json`, a field NO payload ships. A guarded read of a field that
// does not exist fails silently: the section just never appears, so nobody
// notices the screen is dead. This test makes that class of bug loud.
//
// It compares the card fields the presentation layer READS against the fields
// `lib/v2/ipo-command.ts` (+ `lib/fair-value.ts`) actually PRODUCES. Anything
// read but never produced must be listed in KNOWN_DEAD_READS with the producer
// contract that would fill it. The list is frozen in both directions:
//
//   - a NEW dead read fails the test (you must bind to the real field, render
//     an honest missing state, or justify the entry here);
//   - a listed field that the producer STARTS shipping also fails, so the list
//     shrinks as contracts land instead of rotting.
//
// Note: this pins reads of the ipo-command card object (`c.<field>`), which is
// where the candles_json bug lived. Screens driven by ipo-details-v1 are
// state-checked at the leaf by `fieldDisplay`, so a missing field there already
// renders its own reason rather than silently disappearing.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const read = (rel: string) => readFileSync(resolve(ROOT, rel), "utf8");

/** Comments are prose, not code. */
const codeOf = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").split("\n").map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1")).join("\n");

/** Every field name the command payload can carry on a card. */
function producedFields(): Set<string> {
  const command = read("lib/v2/ipo-command.ts");
  const fairValue = read("lib/fair-value.ts");
  const fields = new Set<string>();
  const add = (name: string) => fields.add(name.toLowerCase());
  // SQL: `... AS alias` and bare `alias.column` projections.
  for (const m of command.matchAll(/\bAS\s+([a-z_0-9]+)/gi)) add(m[1]);
  for (const m of command.matchAll(/[\s,(]([a-z]{1,4})\.([a-z_0-9]+)/g)) add(m[2]);
  // Object-literal keys added by enrichCards / fairValue, plus shorthand props.
  for (const src of [command, fairValue]) {
    for (const m of src.matchAll(/\b([a-z_][a-z_0-9]*)\s*:/g)) add(m[1]);
    for (const m of src.matchAll(/\{\s*\.\.\.[a-z]+\s*,\s*([a-z_][a-z_0-9]*)\s*[,}]/g)) add(m[1]);
  }
  // Identity fields the index/journey snapshots also carry.
  for (const name of ["sym", "isin", "state", "insights", "research", "_identity_only"]) add(name);
  return fields;
}

/** Card-field reads (`c.<field>`) in a presentation file. */
function cardReads(rel: string): string[] {
  const code = codeOf(read(rel));
  return [...new Set([...code.matchAll(/\bc\.([a-z_][A-Za-z_0-9]*)/g)].map((m) => m[1]))].sort();
}

const SCANNED = [
  "app/dashboard/ipo2/page.tsx",
  "components/ipo/IpoCard.tsx",
  "components/ipo/ListingReview.tsx",
  "components/ipo/MarketsSidebar.tsx",
];

/**
 * Fields the UI reads that NO producer ships, with the contract that would fill
 * each. Audited 2026-08-17 against lib/v2/ipo-command.ts. `notes.dropped` in the
 * command payload already declares live-ticks / intraday-levels / news / sbi /
 * gmp as dropped for V2 — these reads are the consumer-side remains of that cut.
 */
const KNOWN_DEAD_READS: Record<string, string> = {
  // ── GMP: producer dropped it (no maintained grey-market source) ────────────
  gmp_day_before: "GMP producer. ipo-details-v1 ships gmp.state = STALE, available: false.",
  gmp_high: "GMP producer — same dropped source as gmp_day_before.",
  gmp_low: "GMP producer — same dropped source as gmp_day_before.",
  gmp_band: "GMP producer — same dropped source as gmp_day_before.",
  gmp_hint: "GMP producer — same dropped source as gmp_day_before.",
  // ── Narrative reason strings: never produced by the V2 command builder ─────
  why_trade: "Decision-reason producer: decisions.reasons is shipped by ipo-details-v1, not by ipo-command.",
  why_caution: "Decision-reason producer (see why_trade).",
  why_avoid: "Decision-reason producer (see why_trade).",
  why_passes: "Decision-reason producer (see why_trade).",
  score_evidence: "Scoring producer: valuation ships score/score_band only, no evidence string.",
  // ── Street / SBI: removed from the V2 feeds (#282) ────────────────────────
  street_consensus: "Street-consensus producer. News + SBI were dropped from the V2 feeds in #282.",
  street_brokers: "Street-consensus producer (see street_consensus).",
  sbi_rating: "SBI structured extraction. Only verbatim SBI excerpts ship, via ipo-details verified_evidence.",
  sbi_one_line: "SBI structured extraction (see sbi_rating).",
  sbi_full: "SBI structured extraction (see sbi_rating).",
  // ── RHP narrative: only findings/red_flag_count/junk_signals are produced ──
  rhp_one_line: "RHP narrative producer. ipo-command ships red_flag_count + junk_signals only.",
  rhp_mos: "RHP narrative producer (see rhp_one_line).",
  rhp_full: "RHP narrative producer (see rhp_one_line).",
  rhp_confidence: "RHP narrative producer (see rhp_one_line).",
  rhp_url: "Document producer: document URLs ship on ipo-details verified_evidence[].document.url.",
  ai_summary: "AI-analysis producer: ipo-details-v1 ships ai_analysis.findings; ipo-command does not.",
  // ── Quality / confidence scalars: no producer at all ──────────────────────
  quality_score: "Quality-score producer. ipo-command ships research.company_quality.{status,verdict} only.",
  quality_conf: "Quality-score producer (see quality_score).",
  vscore: "Valuation-confidence producer. ipo-command ships v.score as ipo_score.",
  vconf: "Valuation-confidence producer (see vscore).",
  chittorgarh_slug: "Source-link producer: no slug is carried in the V2 identity projection.",
};

test("the field extractor itself is sane (a broken parse must not read as 'all dead')", () => {
  const produced = producedFields();
  for (const anchor of ["issue_price", "listing_gap_pct", "anchor_count", "playbook_setup", "house_stack", "research", "verdict"]) {
    assert.ok(produced.has(anchor), `producer-field extraction looks broken: missing ${anchor}`);
  }
  assert.ok(produced.size > 60, `producer-field extraction found only ${produced.size} fields`);
});

test("every scanned presentation file exists", () => {
  for (const file of SCANNED) assert.ok(existsSync(resolve(ROOT, file)), `scanned file missing: ${file}`);
});

test("no NEW dead card read: everything read but not produced is a known, contracted gap", () => {
  const produced = producedFields();
  const offenders: string[] = [];
  for (const file of SCANNED) {
    for (const field of cardReads(file)) {
      if (produced.has(field.toLowerCase())) continue;
      if (field in KNOWN_DEAD_READS) continue;
      offenders.push(`${file}: c.${field}`);
    }
  }
  assert.deepEqual(offenders, [],
    "these read a card field no producer ships — bind to the real field, render an honest missing state, or add it to KNOWN_DEAD_READS with its contract");
});

test("KNOWN_DEAD_READS only lists fields that are genuinely still dead", () => {
  const produced = producedFields();
  const revived = Object.keys(KNOWN_DEAD_READS).filter((f) => produced.has(f.toLowerCase()));
  assert.deepEqual(revived, [], "the producer now ships these — bind the UI to them and drop them from KNOWN_DEAD_READS");
});

test("KNOWN_DEAD_READS only lists fields something actually reads", () => {
  const readSomewhere = new Set(SCANNED.flatMap(cardReads));
  const stale = Object.keys(KNOWN_DEAD_READS).filter((f) => !readSomewhere.has(f));
  assert.deepEqual(stale, [], "nothing reads these any more — delete them from KNOWN_DEAD_READS");
});

test("every dead read names the producer contract that would fill it", () => {
  for (const [field, contract] of Object.entries(KNOWN_DEAD_READS)) {
    assert.ok(contract.trim().length > 15, `${field}: name the producer contract, not just a shrug`);
  }
});

test("ListingReview no longer reads the field that started this: candles_json", () => {
  // The original bug. journey:isin:<ISIN>:v1 ships `rows`, served as `series`
  // by /api/ipo/journey; `candles_json` is a DB column that never leaves Neon.
  const review = codeOf(read("components/ipo/ListingReview.tsx"));
  assert.ok(!review.includes("candles_json"), "ListingReview must not read candles_json — it is not in any payload");
  assert.ok(/\/api\/ipo\/journey/.test(review), "ListingReview should read the journey snapshot route");
  assert.equal(KNOWN_DEAD_READS["candles_json"], undefined, "candles_json is fixed, not a known gap");
});
