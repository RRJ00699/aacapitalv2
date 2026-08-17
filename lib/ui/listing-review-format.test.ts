import test from "node:test";
import assert from "node:assert/strict";
import { looksSerialized, type ValueNode } from "./details-format";
import {
  sessionRows, tapeView, outcomeRows, deriveGap, hasShippedGap, discoveryView,
  listingDayFacts, stateHeadline, shippedLabel, isoDay, toNumber, signedPct,
  OUTCOME_FIELDS, EXCLUDED_OUTCOME_FIELDS, FIRST_SESSIONS, NON_ASSERTING_STATES,
  TAPE_ABSENT_MESSAGE, TAPE_COVERAGE_NOTE, CEILING_FALLBACK_CAPTION,
  DISCOVERY_ABSENT_MESSAGE, DISCOVERY_STATELESS_MESSAGE,
} from "./listing-review-format";

// A data-rich listed IPO: five daily sessions exactly as /api/ipo/journey
// returns them (computeJourney().series = date/high/low/close — no open, no volume).
const SERIES = [
  { date: "2026-07-10", high: 512, low: 448, close: 498 },
  { date: "2026-07-13T00:00:00.000Z", high: 521, low: 486, close: 515 },
  { date: "2026-07-14", high: 530, low: 495, close: 502 },
  { date: "2026-07-15", high: 508, low: 470, close: 476 },
  { date: "2026-07-16", high: 489, low: 462, close: 484 },
  { date: "2026-07-17", high: 495, low: 470, close: 491 },
];
const JOURNEY = { ok: true, hasData: true, sym: "UATPOST", isin: "INE000000045", entry: 460, series: SERIES };

const available = (value: unknown, extra: Record<string, unknown> = {}) =>
  ({ state: "AVAILABLE", value, reason: null, source: "listing_outcomes", ...extra });

const OUTCOME = {
  listing_open: available(460),
  gap_pct: available(8.2),
  d1_close: available(498),
  best_close: available(515),
  worst_close: available(476),
  ceiling_20: available(552, { label: "Historical ceiling indicator — non-executable" }),
  pool: available("2026H1"),
  winner_35: available(false),
  hold_positive_vs_open: available(true),
  computed_at: available("2026-07-18"),
};

// ── tape ────────────────────────────────────────────────────────────────────
test("sessionRows renders exactly the first five sessions with both changes", () => {
  const rows = sessionRows(SERIES, 425);
  assert.equal(rows.length, FIRST_SESSIONS);
  assert.equal(rows[0].session, "D0");
  assert.equal(rows[0].date, "2026-07-10");
  assert.equal(rows[1].date, "2026-07-13"); // ISO timestamp trimmed to the day
  assert.equal(rows[0].close, "₹498");
  assert.equal(rows[0].vsIssue, "+17.2%");
  assert.equal(rows[0].vsPrev, "—"); // D0 has no previous close
  assert.equal(rows[1].vsPrev, "+3.4%");
  assert.equal(rows[1].vsPrevTrend, "up");
  assert.equal(rows[3].vsPrevTrend, "down");
});

test("a session with a missing close breaks the chain instead of comparing across the gap", () => {
  const rows = sessionRows([SERIES[0], { date: "2026-07-13", high: null, low: null, close: null }, SERIES[2]], 425);
  assert.equal(rows[1].close, "—");
  assert.equal(rows[1].vsIssue, "—");
  assert.equal(rows[1].vsIssueTrend, "none");
  assert.equal(rows[2].vsPrev, "—", "day-over-day must not skip the missing session");
});

test("no issue price means no fabricated vs-issue percentage", () => {
  const rows = sessionRows(SERIES, null);
  assert.equal(rows[0].vsIssue, "—");
  assert.equal(rows[0].close, "₹498", "the price itself still renders");
});

test("tapeView returns rows with the coverage note when candles exist", () => {
  const view = tapeView(JOURNEY, 425);
  assert.equal(view.kind, "rows");
  if (view.kind !== "rows") return;
  assert.equal(view.rows.length, 5);
  assert.equal(view.sessionsCaptured, 6, "captured count is the full series, not the shown five");
  assert.equal(view.note, TAPE_COVERAGE_NOTE);
  assert.match(view.note, /open and volume are not in its response/);
  assert.match(view.note, /15-minute bars are not published to KV/);
});

test("tapeView gives ONE honest line — never a blank chart — when candles are absent", () => {
  const empty = tapeView({ ok: true, hasData: false, note: "No candles yet — the journey begins once it lists and trades." }, 425);
  assert.equal(empty.kind, "absent");
  if (empty.kind !== "absent") return;
  assert.equal(empty.message, TAPE_ABSENT_MESSAGE);
  assert.match(String(empty.detail), /No candles yet/);

  const degraded = tapeView({ ok: true, hasData: false, degraded: "snapshot unavailable" }, 425);
  assert.equal(degraded.kind, "absent");
  if (degraded.kind !== "absent") return;
  assert.match(String(degraded.detail), /snapshot unavailable/);

  const nothing = tapeView(null, 425);
  assert.equal(nothing.kind, "absent");
  if (nothing.kind !== "absent") return;
  assert.equal(nothing.detail, null);
});

// ── listing-day outcome ─────────────────────────────────────────────────────
test("outcomeRows renders AVAILABLE values through fieldDisplay, formatted per field", () => {
  const rows = outcomeRows(OUTCOME);
  const by = Object.fromEntries(rows.map((r) => [r.key, r]));
  assert.equal(by.listing_open.display.state, "AVAILABLE");
  assert.deepEqual(by.listing_open.node, { kind: "scalar", text: "₹460" });
  assert.deepEqual(by.gap_pct.node, { kind: "scalar", text: "8.2%" });
  assert.deepEqual(by.d1_close.node, { kind: "scalar", text: "₹498" });
  assert.deepEqual(by.best_close.node, { kind: "scalar", text: "₹515" });
  assert.deepEqual(by.worst_close.node, { kind: "scalar", text: "₹476" });
});

test("PENDING and MISSING outcomes carry their reason and no value", () => {
  const rows = outcomeRows({
    listing_open: { state: "PENDING", value: null, reason: "Listing outcome listing_open is pending until the IPO lists.", source: "listing_outcomes" },
    gap_pct: { state: "MISSING", value: null, reason: "Listing outcome gap_pct is unavailable because no computed outcome is stored.", source: "listing_outcomes" },
  });
  const by = Object.fromEntries(rows.map((r) => [r.key, r]));
  assert.equal(by.listing_open.display.hasValue, false);
  assert.equal(by.listing_open.display.state, "PENDING");
  assert.match(String(by.listing_open.display.reason), /pending until the IPO lists/);
  assert.deepEqual(by.listing_open.node, { kind: "empty" });
  assert.equal(by.gap_pct.display.state, "MISSING");
  assert.match(String(by.gap_pct.display.reason), /no computed outcome is stored/);
});

test("an absent listing_outcome block still yields honest MISSING rows, never a crash", () => {
  for (const input of [undefined, null, {}, "nonsense", []]) {
    const rows = outcomeRows(input);
    assert.equal(rows.length, OUTCOME_FIELDS.length);
    for (const row of rows) {
      assert.equal(row.display.state, "MISSING");
      assert.deepEqual(row.node, { kind: "empty" });
    }
  }
});

test("ceiling_20 keeps its shipped non-executable label; the fallback only applies when none ships", () => {
  const withLabel = outcomeRows(OUTCOME).find((r) => r.key === "ceiling_20");
  assert.equal(withLabel?.caption, "Historical ceiling indicator — non-executable");
  const withoutLabel = outcomeRows({ ceiling_20: available(552) }).find((r) => r.key === "ceiling_20");
  assert.equal(withoutLabel?.caption, CEILING_FALLBACK_CAPTION);
  assert.match(String(withoutLabel?.caption), /non-executable/);
  assert.equal(shippedLabel({ label: "  " }), null);
  assert.equal(shippedLabel("not an object"), null);
});

test("cohort / backtest-flavoured outcome fields are never rendered", () => {
  const keys = outcomeRows(OUTCOME).map((r) => r.key);
  for (const excluded of EXCLUDED_OUTCOME_FIELDS) {
    assert.equal(keys.includes(excluded), false, `${excluded} must not render on this screen`);
  }
  assert.deepEqual(EXCLUDED_OUTCOME_FIELDS, ["pool", "winner_35", "hold_positive_vs_open"]);
});

test("the gap is derived only as a labeled fallback, and refuses without both inputs", () => {
  assert.equal(hasShippedGap(OUTCOME), true);
  assert.equal(hasShippedGap({ gap_pct: { state: "PENDING", value: null, reason: "pending" } }), false);
  const derived = deriveGap(460, 425);
  assert.equal(derived.available, true);
  assert.equal(derived.text, "+8.2%");
  assert.match(derived.formula, /listing_open/);
  const refused = deriveGap(null, 425);
  assert.equal(refused.available, false);
  assert.equal(refused.text, "—");
  assert.match(String(refused.reason), /issue price/);
  assert.equal(deriveGap(460, 0).available, false);
});

// ── DISCOVERY observation ───────────────────────────────────────────────────
const LEVEL = {
  ipo_id: 42,
  observed_at: "2026-07-16T10:00:00Z",
  payload: {
    detector_version: "topout-online-researched-v1",
    evaluated_through_bar: "2026-07-16T10:00:00+05:30",
    label: "DISCOVERY",
    state: "TOP", alert: true, alert_bar: 37, alert_price: 476, watch_kind: null,
    promoted: false, invalidated: false, max_state: "SOW_FIRE", fire_path: "SOW",
    trigger: { state: "SOW_FIRE", path: "SOW", bc_high: 530, ar_low: 495, retest_high: 508, volume_ratio: 0.62, bars_since_bc: 9, trigger_strength: 10.2 },
  },
};

test("discoveryView mirrors the producer's own DISCOVERY label and state", () => {
  const view = discoveryView(LEVEL);
  assert.equal(view.kind, "present");
  if (view.kind !== "present") return;
  assert.equal(view.producerLabel, "DISCOVERY");
  assert.equal(view.state, "TOP");
  assert.equal(view.alert, true);
  assert.equal(view.detectorVersion, "topout-online-researched-v1");
  assert.equal(view.evaluatedThrough, "2026-07-16T10:00:00+05:30");
  assert.match(view.headline, /distribution structure/);
});

test("discoveryView renders trigger detail as labeled rows, never a serialized blob", () => {
  const view = discoveryView(LEVEL);
  if (view.kind !== "present") throw new Error("expected a present observation");
  const labels = view.triggerRows.map((r) => r.label);
  assert.deepEqual(labels.slice(0, 3), ["State", "Path", "Bc high"]);
  const walk = (n: ValueNode): string[] =>
    n.kind === "scalar" ? [n.text] : n.kind === "list" ? n.items.flatMap(walk) : n.kind === "rows" ? n.rows.flatMap((r) => walk(r.value)) : [];
  for (const row of [...view.rows, ...view.triggerRows]) {
    for (const text of walk(row.value)) assert.equal(looksSerialized(text), false, `leaked: ${text}`);
  }
  // Summary keys present in the payload render; null ones (watch_kind) do not.
  assert.equal(view.rows.some((r) => r.label === "Watch kind"), false);
  assert.equal(view.rows.some((r) => r.label === "Fire path"), true);
  assert.equal(view.rows.some((r) => r.label === "Max state"), true);
});

test("a bare payload (no observation envelope) is accepted too", () => {
  const view = discoveryView(LEVEL.payload);
  assert.equal(view.kind, "present");
  if (view.kind !== "present") return;
  assert.equal(view.state, "TOP");
});

test("no observation, or one with no state, yields an honest empty — never an invented signal", () => {
  for (const input of [null, undefined, "nope", 7, {}]) {
    const view = discoveryView(input);
    assert.equal(view.kind, "absent");
    if (view.kind !== "absent") return;
    assert.equal(view.message, DISCOVERY_ABSENT_MESSAGE);
  }
  const stateless = discoveryView({ payload: { detector_version: "topout-online-researched-v1" } });
  assert.equal(stateless.kind, "absent");
  if (stateless.kind !== "absent") return;
  assert.equal(stateless.message, DISCOVERY_STATELESS_MESSAGE);
});

test("an observation with no label reports the absence rather than inventing DISCOVERY", () => {
  const view = discoveryView({ payload: { state: "WATCH", watch_kind: "T2" } });
  assert.equal(view.kind, "present");
  if (view.kind !== "present") return;
  assert.equal(view.producerLabel, null);
  assert.match(view.headline, /Watch state/);
});

test("a STALE_INPUT observation reports the detector's freshness gate, not an absence of structure", () => {
  // #333 stores this instead of an observation when the newest 15-minute bar is
  // older than the last completed session.
  const view = discoveryView({ payload: { detector_version: "topout-online-researched-v1", label: "DISCOVERY", state: "STALE_INPUT", alert: false, trigger: null, max_state: "STALE_INPUT" } });
  assert.equal(view.kind, "present");
  if (view.kind !== "present") return;
  assert.equal(view.state, "STALE_INPUT");
  assert.equal(view.alert, false);
  assert.match(view.headline, /older than the last completed session/);
  assert.equal(NON_ASSERTING_STATES.includes(view.state), true, "STALE_INPUT must not read as a finding");
  assert.deepEqual(view.triggerRows, []);
});

test("stateHeadline covers the detector vocabulary and stays neutral on unknown states", () => {
  for (const state of ["TOP", "WATCH", "IDLE", "BC_ARMED", "AR_CONFIRMED", "FAILED_RETEST", "SOW_FIRE", "STALE_INPUT"]) {
    assert.ok(stateHeadline(state).length > 0);
  }
  assert.match(stateHeadline("BRAND_NEW"), /recorded as observed/);
  for (const state of ["TOP", "WATCH", "IDLE", "BRAND_NEW"]) {
    assert.doesNotMatch(stateHeadline(state), /\bbuy\b|\bsell\b|\bexit\b|%/i, "headlines must not read as instructions");
  }
});

// ── day-0 facts + small helpers ─────────────────────────────────────────────
test("listingDayFacts uses the one open that survives computeJourney (entry)", () => {
  const facts = listingDayFacts(JOURNEY, 425);
  assert.deepEqual(facts, { issue: 425, open: 460, high: 512, low: 448, close: 498 });
  assert.deepEqual(listingDayFacts(null, 425), { issue: 425, open: null, high: null, low: null, close: null });
  assert.deepEqual(listingDayFacts({ ok: true, series: [] }, null), { issue: null, open: null, high: null, low: null, close: null });
});

test("toNumber / isoDay / signedPct are strict about junk", () => {
  assert.equal(toNumber(true), null);
  assert.equal(toNumber(""), null);
  assert.equal(toNumber("425"), 425);
  assert.equal(toNumber("not a price"), null);
  assert.equal(isoDay("2026-07-10T09:15:00Z"), "2026-07-10");
  assert.equal(isoDay(null), null);
  assert.equal(isoDay(new Date("2026-07-10T00:00:00Z")), "2026-07-10");
  assert.equal(signedPct(0), "+0.0%");
  assert.equal(signedPct(-4), "-4.0%");
});

test("nothing this module produces reads as a win-rate or backtest statistic", () => {
  const view = tapeView(JOURNEY, 425);
  const discovery = discoveryView(LEVEL);
  const text = [
    TAPE_COVERAGE_NOTE, TAPE_ABSENT_MESSAGE, CEILING_FALLBACK_CAPTION,
    ...(view.kind === "rows" ? view.rows.flatMap((r) => [r.vsIssue, r.vsPrev]) : []),
    ...(discovery.kind === "present" ? [discovery.headline] : []),
    ...outcomeRows(OUTCOME).map((r) => r.label),
  ].join(" ").toLowerCase();
  for (const phrase of ["win rate", "win-rate", "% win", "of 10 worked", "backtest", "edge", "expected return"]) {
    assert.equal(text.includes(phrase), false, `forbidden performance phrase: ${phrase}`);
  }
});
