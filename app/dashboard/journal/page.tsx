// app/dashboard/journal/page.tsx
// Trade Journal — wired to Neon trade_journal table

import { neon } from "@neondatabase/serverless";
import JournalClient from "./JournalClient";

const sql = neon(process.env.NEON_DATABASE_URL!);
export const revalidate = 300;

export interface TradeEntry {
  id: number;
  symbol: string;
  company_name: string | null;
  trade_type: string | null;
  entry_date: string | null;
  exit_date: string | null;
  entry_price: number | null;
  exit_price: number | null;
  quantity: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  holding_days: number | null;
  reason_entry: string | null;
  reason_exit: string | null;
  conviction_at_entry: string | null;
  outcome: string | null;
  lessons: string | null;
}

async function getJournal(): Promise<TradeEntry[]> {
  try {
    const r = await sql`
      SELECT
        id, symbol, company_name, trade_type,
        entry_date, exit_date,
        entry_price, exit_price, quantity,
        pnl, pnl_pct,
        CASE WHEN exit_date IS NOT NULL AND entry_date IS NOT NULL
          THEN (exit_date::date - entry_date::date)
          ELSE NULL END   AS holding_days,
        reason_entry, reason_exit,
        conviction_at_entry, outcome, lessons
      FROM trade_journal
      ORDER BY entry_date DESC
    ` as TradeEntry[];
    return r;
  } catch { return []; }
}

async function getStats() {
  try {
    const r = await sql`
      SELECT
        COUNT(*)                                    AS total_trades,
        COUNT(*) FILTER (WHERE pnl > 0)             AS winners,
        COUNT(*) FILTER (WHERE pnl < 0)             AS losers,
        ROUND(SUM(pnl)::numeric, 0)                 AS total_pnl,
        ROUND(AVG(pnl_pct)::numeric, 1)             AS avg_return_pct,
        ROUND(MAX(pnl_pct)::numeric, 1)             AS best_trade_pct,
        ROUND(MIN(pnl_pct)::numeric, 1)             AS worst_trade_pct,
        ROUND(AVG(CASE WHEN exit_date IS NOT NULL AND entry_date IS NOT NULL
          THEN (exit_date::date - entry_date::date) ELSE NULL END)::numeric, 0) AS avg_holding_days
      FROM trade_journal
      WHERE outcome IS NOT NULL
    `;
    return r[0];
  } catch { return {}; }
}

export default async function JournalPage() {
  const [trades, stats] = await Promise.all([getJournal(), getStats()]);
  return <JournalClient trades={trades} stats={stats} />;
}
