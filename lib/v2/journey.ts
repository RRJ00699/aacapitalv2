// lib/v2/journey.ts — the HOLD engine (lock8/trail12 exit levels).
// V2 rewrite: candles come from canonical `market_candles` (keyed by ipo_id),
// with the window floored at `ipo.listing_date`. Was V1 `price_candles` by symbol
// + `ipo_intelligence` for the listing date. The exit math is unchanged.
import type { SqlClient } from "./sql";

export const ARM = 0.08;   // arm the floor once high hits +8%
export const FLOOR = 0.03; // protect +3% once armed
export const TRAIL = 0.12; // 12% trailing stop from peak

// price_candles held the whole NSE universe, so its earliest row was not the
// listing day; market_candles is IPO-scoped by ipo_id, but we still floor at
// listing_date so pre-listing rows (if any) never enter the entry/floor math.
export async function fetchJourneyCandles(sql: SqlClient, sym: string) {
  return await sql`
    WITH t AS (
      SELECT id, listing_date FROM ipo
      WHERE UPPER(symbol) = ${sym}
      ORDER BY listing_date DESC NULLS LAST
      LIMIT 1
    )
    SELECT c.d AS date, c.o AS open, c.h AS high, c.l AS low, c.c AS close, c.v AS volume
    FROM market_candles c, t
    WHERE c.ipo_id = t.id
      AND (t.listing_date IS NULL OR c.d >= t.listing_date)
    ORDER BY c.d ASC
    LIMIT 40`;
}

// Pure: given candles (+ an optional live price) produce the decision payload.
export function computeJourney(
  rows: Record<string, unknown>[],
  sym: string,
  liveOverride?: { price: number; source: string } | null,
) {
  if (!rows.length) {
    return { ok: true, sym, hasData: false,
      note: "No candles yet — the journey begins once it lists and trades." };
  }
  const entry = Number(rows[0].open) || 0;
  if (entry <= 0) return { ok: true, sym, hasData: false, note: "No valid open price." };

  let peak = entry, armed = false, lowSince = entry;
  const series = rows.map((r) => {
    const hi = Number(r.high), lo = Number(r.low), cl = Number(r.close);
    peak = Math.max(peak, hi);
    lowSince = Math.min(lowSince, lo);
    if (hi >= entry * (1 + ARM)) armed = true;
    return { date: r.date, close: cl, high: hi, low: lo };
  });
  const lastClose = Number(rows[rows.length - 1].close) || entry;
  const floorLevel = entry * (1 + FLOOR);
  const trailLevel = peak * (1 - TRAIL);
  const daysHeld = rows.length;
  const lockinDaysLeft = Math.max(0, 30 - daysHeld);

  const live = liveOverride && liveOverride.price > 0 ? liveOverride.price : lastClose;
  const liveSource = liveOverride && liveOverride.price > 0 ? liveOverride.source : "close";

  const gainNow = ((live / entry) - 1) * 100;
  const offPeak = ((live / peak) - 1) * 100;
  let decision = "HOLD", reason = "", tone = "good";
  if (armed && live <= floorLevel) {
    decision = "EXIT"; tone = "bad";
    reason = "Floor broken. Price is at or below your +3% floor. You were up 8%+ — lock the gain now rather than watch it bleed to close.";
  } else if (live <= trailLevel) {
    decision = "EXIT"; tone = "bad";
    reason = "Trailing stop hit. Price is 12%+ off the peak. The run is over — take what's left.";
  } else if (armed) {
    reason = `Holding. Up ${gainNow.toFixed(1)}%, floor armed. Your urge to sell early is the mistake — the rule exits you if it breaks, not before.`;
  } else {
    reason = "Holding. Not yet +8% to arm the floor. Trailing stop protects the downside.";
  }

  return {
    ok: true, sym, hasData: true,
    entry: Math.round(entry * 10) / 10,
    peak: Math.round(peak * 10) / 10,
    low: Math.round(lowSince * 10) / 10,
    live: Math.round(live * 10) / 10,
    liveSource, armed,
    floorLevel: Math.round(floorLevel * 10) / 10,
    trailLevel: Math.round(trailLevel * 10) / 10,
    gainNow: Math.round(gainNow * 10) / 10,
    offPeak: Math.round(offPeak * 10) / 10,
    daysHeld, lockinDaysLeft,
    decision, reason, tone, series,
  };
}
