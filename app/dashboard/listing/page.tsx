// app/dashboard/listing/page.tsx
// Task 7: Listing Day Dashboard — OI + VWAP signals

import postgres from "postgres";

import ListingDayClient from "./ListingDayClient";

const db = postgres(process.env.NEON_DATABASE_URL!, { ssl: "require" });

export const revalidate = 60; // refresh every minute on listing day

export interface ListingSignal {
  id: number;
  company_name: string;
  nse_symbol: string | null;
  issue_price: number | null;
  listing_date: string | null;
  listing_price: number | null;
  listing_gap_pct: number | null;
  lqi_score: number | null;
  conviction: string | null;

  // Live signals (from kite-sync-ipos.py --listing)
  last_price: number | null;
  vwap: number | null;
  above_vwap: boolean | null;
  listing_volume: number | null;
  buy_qty: number | null;
  sell_qty: number | null;

  // Subscription
  total_subscription: number | null;
  qib_subscription: number | null;
  gmp_percentage: number | null;

  // Computed
  current_gain_pct?: number | null;
}

async function getListingToday(): Promise<ListingSignal[]> {
  const r = await db<ListingSignal>`
    SELECT
      id, company_name, nse_symbol,
      issue_price, listing_date,
      listing_price, listing_gap_pct,
      lqi_score, conviction,
      last_price, vwap, above_vwap,
      listing_volume, buy_qty, sell_qty,
      total_subscription, qib_subscription,
      gmp_percentage
    FROM ipo_intelligence
    WHERE listing_date = CURRENT_DATE
    ORDER BY lqi_score DESC NULLS LAST
  `;
  return r.rows;
}

async function getRecentListings(): Promise<ListingSignal[]> {
  const r = await db<ListingSignal>`
    SELECT
      id, company_name, nse_symbol,
      issue_price, listing_date,
      listing_price, listing_gap_pct,
      lqi_score, conviction,
      total_subscription, qib_subscription,
      gmp_percentage,
      NULL::numeric AS last_price,
      NULL::numeric AS vwap,
      NULL::boolean AS above_vwap,
      NULL::bigint  AS listing_volume,
      NULL::bigint  AS buy_qty,
      NULL::bigint  AS sell_qty
    FROM ipo_intelligence
    WHERE listing_date >= CURRENT_DATE - INTERVAL '14 days'
      AND listing_date < CURRENT_DATE
      AND listing_gap_pct IS NOT NULL
    ORDER BY listing_date DESC
    LIMIT 20
  `;
  return r.rows;
}

async function getListingStats() {
  const r = await db`
    SELECT
      COUNT(*) FILTER (WHERE listing_gap_pct > 0)   AS positive_listings,
      COUNT(*) FILTER (WHERE listing_gap_pct >= 10)  AS gain_10plus,
      COUNT(*) FILTER (WHERE listing_gap_pct < 0)    AS negative_listings,
      ROUND(AVG(listing_gap_pct)::numeric, 1)        AS avg_gain,
      COUNT(*)                                         AS total_listed
    FROM ipo_intelligence
    WHERE listing_gap_pct IS NOT NULL
      AND listing_date >= CURRENT_DATE - INTERVAL '90 days'
  `;
  return r.rows[0];
}

export default async function ListingDayPage() {
  const [todayListings, recentListings, stats] = await Promise.all([
    getListingToday(),
    getRecentListings(),
    getListingStats(),
  ]);

  return (
    <ListingDayClient
      todayListings={todayListings}
      recentListings={recentListings}
      stats={stats}
    />
  );
}
