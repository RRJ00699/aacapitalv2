// app/dashboard/multibagger/page.tsx
// Task 2: Wire Multibagger Discovery tab to Neon technical_signals

import postgres from "postgres";

import MultibaggerClient from "./MultibaggerClient";

const db = postgres(process.env.NEON_DATABASE_URL!, { ssl: "require" });

export const revalidate = 3600; // revalidate every hour

export interface TechnicalSignal {
  id: number;
  symbol: string;
  signal_date: string;
  monthly_rsi: number | null;
  monthly_rsi_ok: boolean | null;
  weekly_ema30: number | null;
  price_above_ema30: boolean | null;
  weekly_ha_bullish: boolean | null;
  daily_nr7: boolean | null;
  daily_inside_bar: boolean | null;
  criteria_met: number | null;
  all_criteria_met: boolean | null;
  mb_score: number | null;
  conviction: string | null;
  dtw_pattern_match: string | null;
  dtw_similarity_pct: number | null;
  synced_at: string;
}

async function getSignals(): Promise<TechnicalSignal[]> {
  const result = await db<TechnicalSignal>`
    SELECT
      id, symbol, signal_date,
      monthly_rsi, monthly_rsi_ok,
      weekly_ema30, price_above_ema30,
      weekly_ha_bullish,
      daily_nr7, daily_inside_bar,
      criteria_met, all_criteria_met,
      mb_score, conviction,
      dtw_pattern_match, dtw_similarity_pct,
      synced_at
    FROM technical_signals
    ORDER BY
      all_criteria_met DESC NULLS LAST,
      mb_score DESC NULLS LAST,
      signal_date DESC
    LIMIT 200
  `;
  return result.rows;
}

async function getStats() {
  const r = await db`
    SELECT
      COUNT(*)                                            AS total,
      COUNT(*) FILTER (WHERE all_criteria_met = true)    AS strong,
      COUNT(DISTINCT symbol)                             AS unique_stocks,
      MAX(signal_date)                                   AS latest_date
    FROM technical_signals
  `;
  return r.rows[0];
}

export default async function MultibaggerPage() {
  const [signals, stats] = await Promise.all([getSignals(), getStats()]);

  return (
    <MultibaggerClient
      signals={signals}
      stats={{
        total:        Number(stats.total),
        strong:       Number(stats.strong),
        uniqueStocks: Number(stats.unique_stocks),
        latestDate:   stats.latest_date as string,
      }}
    />
  );
}
