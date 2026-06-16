// app/dashboard/watchlist/page.tsx
// Watchlist Management — wired to Neon watchlist table

import { neon } from "@neondatabase/serverless";
import WatchlistClient from "./WatchlistClient";

const sql = neon(process.env.NEON_DATABASE_URL!);
export const revalidate = 300;

export interface WatchlistItem {
  id: number;
  symbol: string;
  company_name: string | null;
  sector: string | null;
  added_date: string | null;
  target_price: number | null;
  stop_loss: number | null;
  notes: string | null;
  conviction: string | null;
  current_price: number | null;
  upside_pct: number | null;
}

async function getWatchlist(): Promise<WatchlistItem[]> {
  try {
    const r = await sql`
      SELECT
        w.id, w.symbol,
        COALESCE(s.name, w.symbol)   AS company_name,
        s.industry                   AS sector,
        w.created_at                 AS added_date,
        w.target_price, w.stop_loss, w.notes, w.conviction,
        s.current_price,
        CASE WHEN s.current_price > 0 AND w.target_price > 0
          THEN ROUND(((w.target_price - s.current_price) / s.current_price * 100)::numeric, 1)
          ELSE NULL END              AS upside_pct
      FROM watchlist w
      LEFT JOIN stock_fundamentals s ON s.nse_symbol = w.symbol
      ORDER BY w.created_at DESC
    ` as WatchlistItem[];
    return r;
  } catch { return []; }
}

export default async function WatchlistPage() {
  const items = await getWatchlist();
  return <WatchlistClient items={items} />;
}
