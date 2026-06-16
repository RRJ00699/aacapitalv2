// app/dashboard/multibagger/page.tsx
// Task 2: Wire Multibagger Discovery tab to Neon technical_signals

import { neon } from "@neondatabase/serverless";
import MultibaggerClient from "./MultibaggerClient";

const sql = neon(process.env.NEON_DATABASE_URL!);

export const revalidate = 3600;

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
  const result = await sql`
    SELECT
      id, symbol, signal_date,
      monthly_rsi_14                    AS monthly_rsi,
      monthly_ok                        AS monthly_rsi_ok,
      weekly_ema_30                     AS weekly_ema30,
      weekly_ok                         AS price_above_ema30,
      weekly_ha_green_no_lower_shadow   AS weekly_ha_bullish,
      daily_nr7_recent                  AS daily_nr7,
      daily_inside_bar_recent           AS daily_inside_bar,
      buy_zone_score                    AS criteria_met,
      trigger_ok                        AS all_criteria_met,
      probability_score                 AS mb_score,
      action_label                      AS conviction,
      NULL::text                        AS dtw_pattern_match,
      NULL::numeric                     AS dtw_similarity_pct,
      updated_at                        AS synced_at
    FROM technical_signals
    ORDER BY
      trigger_ok DESC NULLS LAST,
      probability_score DESC NULLS LAST,
      signal_date DESC
    LIMIT 200
  ` as TechnicalSignal[];
  return result;
}

async function getStats() {
  const r = await sql`
    SELECT
      COUNT(*)                                          AS total,
      COUNT(*) FILTER (WHERE trigger_ok = true)        AS strong,
      COUNT(DISTINCT symbol)                            AS unique_stocks,
      MAX(signal_date)                                  AS latest_date
    FROM technical_signals
  `;
  return r[0];
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
