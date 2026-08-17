// lib/ui/listing-review-format.ts — pure presentation helpers for the Listing
// Review / journey screen. Framework-agnostic (no React) so it is unit-testable
// under lib/**/*.test.ts.
//
// It deliberately does NOT restate DetailField.state semantics: every
// listing-outcome leaf goes through `fieldDisplay` from ./details-format, and
// every value goes through `toValueNode`, so the "no JSON.stringify /
// [object Object] in the DOM" guarantee is the same one Complete Details has.
//
// Honest-missing is the contract here. What the KV surface cannot carry is
// SAID, never approximated:
//  - the journey API returns computeJourney().series = {date, high, low, close};
//    per-bar open and volume exist in the snapshot but are dropped at the route
//    boundary (lib/v2/journey.ts), which this consumer must not edit;
//  - 15-minute bars (market_candles_15m) are not published to KV at all, so the
//    tape is daily. The top detector runs on those 15m bars inside the pipeline
//    and only its observation reaches KV.
import {
  fieldDisplay, toValueNode, humanizeKey, fmtNum, fmtRupee,
  type DetailField, type FieldDisplay, type ValueNode,
} from "./details-format";

export const FIRST_SESSIONS = 5;

// ── Shared, test-pinned copy ────────────────────────────────────────────────
/** The single honest line about the tape's real resolution and coverage. */
export const TAPE_COVERAGE_NOTE =
  "Daily bars. The journey API carries date, high, low and close for each session; per-bar open and volume are not in its response, and 15-minute bars are not published to KV.";
/** Rendered instead of an empty chart when no candle ever arrives. */
export const TAPE_ABSENT_MESSAGE = "Candle data not yet available.";

export const DISCOVERY_LABEL_FALLBACK = "The stored observation carries no label field.";
export const DISCOVERY_CAVEAT =
  "DISCOVERY observations describe detected price structure only. They are not executable signals, carry no expected return, and are not a recommendation.";
export const DISCOVERY_SCOPE_NOTE =
  "Top observations only — the bottom mirror is out of production scope by design.";
export const DISCOVERY_ABSENT_MESSAGE =
  "No top-structure observation is recorded for this IPO in the journey snapshot.";
export const DISCOVERY_STATELESS_MESSAGE =
  "A level observation is stored but carries no detector state, so nothing is asserted about it.";

/** Used only when the shipped ceiling_20 DetailField carries no label of its own. */
export const CEILING_FALLBACK_CAPTION = "Historical ceiling indicator — non-executable";

// ── Small local helpers ─────────────────────────────────────────────────────
const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Strictly numeric: booleans and blank strings are NOT numbers. */
export function toNumber(v: unknown): number | null {
  if (v == null || v === "" || typeof v === "boolean") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Signed one-decimal percentage, e.g. "+12.3%" / "-4.0%". */
export const signedPct = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;

/** YYYY-MM-DD from whatever the snapshot serialized a DATE column into. */
export function isoDay(v: unknown): string | null {
  if (v == null) return null;
  const text = v instanceof Date ? v.toISOString() : String(v);
  const match = text.match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : (text.trim() ? text.trim() : null);
}

// ── 1. First-five-session tape ──────────────────────────────────────────────
export type Trend = "up" | "down" | "flat" | "none";

export type SessionRow = {
  session: string;
  date: string;
  high: string;
  low: string;
  close: string;
  vsIssue: string;
  vsIssueTrend: Trend;
  vsPrev: string;
  vsPrevTrend: Trend;
};

const trendOf = (pct: number | null): Trend =>
  pct == null ? "none" : pct > 0.05 ? "up" : pct < -0.05 ? "down" : "flat";

const changePct = (now: number | null, base: number | null): number | null =>
  now == null || base == null || base <= 0 ? null : ((now - base) / base) * 100;

/**
 * The first `FIRST_SESSIONS` sessions of the journey series as display rows.
 * A session with no close breaks the day-over-day chain rather than silently
 * comparing across the gap.
 */
export function sessionRows(series: unknown, issuePrice: unknown): SessionRow[] {
  const bars = Array.isArray(series) ? series.slice(0, FIRST_SESSIONS) : [];
  const issue = toNumber(issuePrice);
  let previousClose: number | null = null;
  return bars.map((raw, i) => {
    const bar = isPlainObject(raw) ? raw : {};
    const high = toNumber(bar.high);
    const low = toNumber(bar.low);
    const close = toNumber(bar.close);
    const vsIssue = changePct(close, issue);
    const vsPrev = i === 0 ? null : changePct(close, previousClose);
    previousClose = close;
    return {
      session: `D${i}`,
      date: isoDay(bar.date) ?? "—",
      high: high == null ? "—" : fmtRupee(high),
      low: low == null ? "—" : fmtRupee(low),
      close: close == null ? "—" : fmtRupee(close),
      vsIssue: vsIssue == null ? "—" : signedPct(vsIssue),
      vsIssueTrend: trendOf(vsIssue),
      vsPrev: vsPrev == null ? "—" : signedPct(vsPrev),
      vsPrevTrend: trendOf(vsPrev),
    };
  });
}

export type JourneyResponse = {
  ok?: boolean;
  hasData?: boolean;
  sym?: string;
  isin?: string | null;
  note?: string;
  degraded?: string;
  series?: unknown;
  entry?: unknown;
  daysHeld?: unknown;
  level_observation?: unknown;
};

export type TapeView =
  | { kind: "rows"; rows: SessionRow[]; sessionsCaptured: number; note: string }
  | { kind: "absent"; message: string; detail: string | null };

/** Rows when candles exist; otherwise ONE honest line — never a blank chart. */
export function tapeView(journey: JourneyResponse | null | undefined, issuePrice: unknown): TapeView {
  const series = journey && Array.isArray(journey.series) ? journey.series : [];
  if (!series.length) {
    const detail = journey
      ? (typeof journey.note === "string" && journey.note ? journey.note
        : typeof journey.degraded === "string" && journey.degraded ? `Journey snapshot: ${journey.degraded}.`
        : null)
      : null;
    return { kind: "absent", message: TAPE_ABSENT_MESSAGE, detail };
  }
  return {
    kind: "rows",
    rows: sessionRows(series, issuePrice),
    sessionsCaptured: series.length,
    note: TAPE_COVERAGE_NOTE,
  };
}

// ── 2. Listing-day outcome (ipo-details-v1 .listing_outcome) ────────────────
export type OutcomeFormat = "rupee" | "pct" | "raw";
export type OutcomeSpec = { key: string; label: string; format: OutcomeFormat; caption?: string };

/**
 * The outcome leaves this screen renders. `pool`, `winner_35` and
 * `hold_positive_vs_open` are deliberately EXCLUDED: they are cohort /
 * backtest-flavoured fields and this screen ships no performance statistics.
 */
export const OUTCOME_FIELDS: readonly OutcomeSpec[] = [
  { key: "listing_open", label: "Listing open", format: "rupee" },
  { key: "gap_pct", label: "Gap vs issue price", format: "pct" },
  { key: "d1_close", label: "Day-1 close", format: "rupee" },
  { key: "best_close", label: "Best close", format: "rupee" },
  { key: "worst_close", label: "Worst close", format: "rupee" },
  { key: "ceiling_20", label: "Ceiling indicator", format: "rupee", caption: CEILING_FALLBACK_CAPTION },
];

export const EXCLUDED_OUTCOME_FIELDS: readonly string[] = ["pool", "winner_35", "hold_positive_vs_open"];

export type OutcomeRow = {
  key: string;
  label: string;
  display: FieldDisplay;
  node: ValueNode;
  caption: string | null;
};

function formatted(value: unknown, format: OutcomeFormat): ValueNode {
  if (typeof value === "number" && Number.isFinite(value)) {
    if (format === "rupee") return { kind: "scalar", text: fmtRupee(value) };
    if (format === "pct") return { kind: "scalar", text: `${fmtNum(value)}%` };
  }
  return toValueNode(value);
}

/** A DetailField's own `label` (ceiling_20 ships one) without inventing copy. */
export function shippedLabel(field: unknown): string | null {
  if (!isPlainObject(field)) return null;
  const label = field.label;
  return typeof label === "string" && label.trim() ? label : null;
}

/**
 * Outcome rows driven entirely by `fieldDisplay`: AVAILABLE renders the value,
 * MISSING / PENDING renders its reason (the renderer reads `display.reason`).
 */
export function outcomeRows(listingOutcome: unknown): OutcomeRow[] {
  const record = isPlainObject(listingOutcome) ? listingOutcome : {};
  return OUTCOME_FIELDS.map((spec) => {
    const raw = record[spec.key];
    const field = isPlainObject(raw) ? (raw as DetailField) : undefined;
    const display = fieldDisplay(field);
    return {
      key: spec.key,
      label: spec.label,
      display,
      node: display.hasValue ? formatted(field?.value, spec.format) : { kind: "empty" },
      caption: shippedLabel(raw) ?? spec.caption ?? null,
    };
  });
}

// ── The gap, derived only when the producer did not compute it ──────────────
export type DerivedGap = { available: boolean; text: string; formula: string; reason?: string };

export const GAP_FORMULA = "(listing_open − issue_price) / issue_price × 100";

export function deriveGap(listingOpen: unknown, issuePrice: unknown): DerivedGap {
  const open = toNumber(listingOpen);
  const issue = toNumber(issuePrice);
  if (open == null || issue == null || issue <= 0)
    return {
      available: false, text: "—", formula: GAP_FORMULA,
      reason: "Needs both a listed open price and the issue price; one of them is not available.",
    };
  return { available: true, text: signedPct(((open - issue) / issue) * 100), formula: GAP_FORMULA };
}

/** True when the producer's own gap_pct is present, so nothing is derived. */
export function hasShippedGap(listingOutcome: unknown): boolean {
  const record = isPlainObject(listingOutcome) ? listingOutcome : {};
  return fieldDisplay(isPlainObject(record.gap_pct) ? (record.gap_pct as DetailField) : undefined).hasValue;
}

// ── 3. Top-structure DISCOVERY observation ─────────────────────────────────
export type DiscoveryRow = { label: string; value: ValueNode };

export type DiscoveryView =
  | {
      kind: "present";
      /** The producer's own label literal, mirrored — never invented. */
      producerLabel: string | null;
      state: string;
      alert: boolean;
      headline: string;
      detectorVersion: string | null;
      evaluatedThrough: string | null;
      rows: DiscoveryRow[];
      triggerRows: DiscoveryRow[];
    }
  | { kind: "absent"; message: string };

/** Neutral descriptions of the detector's own state vocabulary. */
const STATE_HEADLINE: Record<string, string> = {
  TOP: "Top state fired — the detector observed a completed distribution structure.",
  WATCH: "Watch state — a possible distribution structure is forming.",
  IDLE: "Idle — no distribution structure observed.",
  BC_ARMED: "Buying-climax bar armed; no further structure yet.",
  AR_CONFIRMED: "Automatic-reaction low confirmed after the climax bar.",
  FAILED_RETEST: "Retest of the climax high failed.",
  SOW_FIRE: "Sign-of-weakness break below the frozen reaction low.",
  // #333 added a freshness gate: the detector refuses to evaluate a stale bar
  // and stores this instead of an observation, so the UI must not read it as
  // "nothing found".
  STALE_INPUT: "Stale input — the newest 15-minute bar is older than the last completed session, so nothing was evaluated.",
};

/** States that assert nothing about structure; they report the detector's own health. */
export const NON_ASSERTING_STATES: readonly string[] = ["STALE_INPUT"];

export function stateHeadline(state: string): string {
  return STATE_HEADLINE[state] ?? `Detector state ${state}, recorded as observed.`;
}

/** Ordered summary keys; each renders only when the payload actually carries it. */
const SUMMARY_KEYS = ["max_state", "watch_kind", "fire_path", "alert_bar", "alert_price", "promoted", "invalidated"];

/**
 * Accepts the stored `listing_observations` row ({payload, observed_at}) or a
 * bare detector payload. Nothing is asserted that the payload does not carry.
 */
export function discoveryView(levelObservation: unknown): DiscoveryView {
  if (!isPlainObject(levelObservation)) return { kind: "absent", message: DISCOVERY_ABSENT_MESSAGE };
  const payload = isPlainObject(levelObservation.payload)
    ? (levelObservation.payload as Record<string, unknown>)
    : levelObservation;
  const rawState = typeof payload.state === "string" ? payload.state.trim().toUpperCase() : "";
  if (!rawState) {
    return {
      kind: "absent",
      message: Object.keys(payload).length ? DISCOVERY_STATELESS_MESSAGE : DISCOVERY_ABSENT_MESSAGE,
    };
  }
  const rows: DiscoveryRow[] = [];
  for (const key of SUMMARY_KEYS) {
    const node = toValueNode(payload[key]);
    if (node.kind !== "empty") rows.push({ label: humanizeKey(key), value: node });
  }
  const trigger = isPlainObject(payload.trigger) ? payload.trigger : {};
  const triggerRows: DiscoveryRow[] = Object.entries(trigger)
    .map(([key, value]) => ({ label: humanizeKey(key), value: toValueNode(value) }))
    .filter((row) => row.value.kind !== "empty");
  return {
    kind: "present",
    producerLabel: typeof payload.label === "string" && payload.label.trim() ? payload.label.trim() : null,
    state: rawState,
    alert: payload.alert === true,
    headline: stateHeadline(rawState),
    detectorVersion: typeof payload.detector_version === "string" ? payload.detector_version : null,
    evaluatedThrough: typeof payload.evaluated_through_bar === "string" ? payload.evaluated_through_bar : null,
    rows,
    triggerRows,
  };
}

// ── Listing-day facts fed to lib/listing-review observations ───────────────
export type ListingDayFacts = {
  issue: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
};

/**
 * Day-0 facts assembled ONLY from what the journey API actually returns:
 * `entry` is rows[0].open (the one open that survives computeJourney), and
 * high/low/close come from series[0].
 */
export function listingDayFacts(journey: JourneyResponse | null | undefined, issuePrice: unknown): ListingDayFacts {
  const series = journey && Array.isArray(journey.series) ? journey.series : [];
  const day0 = isPlainObject(series[0]) ? (series[0] as Record<string, unknown>) : {};
  return {
    issue: toNumber(issuePrice),
    open: toNumber(journey?.entry),
    high: toNumber(day0.high),
    low: toNumber(day0.low),
    close: toNumber(day0.close),
  };
}
