// app/dashboard/ipo/page.tsx
// IPO Command Center — wired to ipo_consolidated (the maintained wide table).
//
// Sources the REAL, backfilled columns (gap_bucket, floor/ceiling, level_verdict,
// listing_open, total_subscription_x, ipo_pe, anchor_count/quality, is_sme, …) and
// leads with the VALIDATED edge (gap_bucket), not the disproven LQI "Strong Buy/Avoid".

import { neon } from "@neondatabase/serverless";
import IPOCommandCenterClient from "./IPOCommandCenterClient";
import type { IPORow } from "@/components/ipo/IpoSignalCard";

const sql = neon(process.env.NEON_DATABASE_URL!);

export const revalidate = 900; // 15 min

async function getIPOs(): Promise<IPORow[]> {
  const r = await sql`
    SELECT
      ROW_NUMBER() OVER (ORDER BY listing_date DESC NULLS LAST, company_name) AS id,
      company_name,
      COALESCE(symbol_final, nse_symbol, symbol)        AS symbol,
      COALESCE(is_sme, FALSE)                           AS is_sme,
      issue_category,
      ipo_status,

      issue_price,
      issue_size_cr,
      ipo_open_date                                     AS issue_open_date,
      ipo_close_date                                    AS issue_close_date,
      listing_date,

      -- VALIDATED signal inputs
      listing_open,
      gap_bucket,
      listing_gap_pct,
      return_current,
      floor_price,
      ceiling_price,
      level_verdict,
      tp1_exit_note,

      -- demand (consolidated canonical subscription cols; these already reflect the backfill)
      final_total                                       AS total_subscription,
      final_qib                                         AS qib_subscription,
      final_retail                                      AS retail_subscription,
      final_nii                                         AS nii_subscription,

      -- fundamentals (correct column names)
      COALESCE(ipo_pe, ipo_pe_post)                     AS ipo_pe,
      peer_median_pe,
      roe,
      pat_cr,
      is_profitable,
      valuation_premium,
      promoter_holding_after                            AS promoter_holding_post,

      -- anchors / BRLM
      anchor_count,
      anchor_quality,
      anchor_total_cr,
      brlm_names,
      brlm_tier,

      -- context (NOT a buy signal)
      regime_at_listing,
      gmp_pct,
      gmp_value,

      -- quality score (demoted from "verdict")
      lqi_final                                         AS lqi_score
    FROM ipo_consolidated
    ORDER BY
      -- surface the actionable ones first: open/listing-pending, then by listing recency
      (ipo_status IN ('OPEN','LISTING_PENDING','ALLOTMENT_PENDING')) DESC,
      listing_date DESC NULLS LAST,
      lqi_final DESC NULLS LAST
    LIMIT 400
  ` as IPORow[];
  return r;
}

async function getSummaryStats() {
  const r = await sql`
    SELECT
      COUNT(*) FILTER (WHERE ipo_status IN ('OPEN','ALLOTMENT_PENDING'))                 AS open_count,
      COUNT(*) FILTER (WHERE listing_date >= CURRENT_DATE)                               AS listing_pending,
      -- the actual edge: MID-gap listings are the playable zone
      COUNT(*) FILTER (WHERE gap_bucket = 'MID')                                         AS playable_mid,
      -- capital-protection watch: holding something sitting on its floor
      COUNT(*) FILTER (WHERE level_verdict ILIKE '%FLOOR%')                              AS at_floor,
      -- strong demand (context)
      COUNT(*) FILTER (WHERE final_total >= 10)                                         AS subscribed_10x,
      COUNT(*)                                                                            AS total
    FROM ipo_consolidated
  `;
  return r[0];
}

export default async function IPOCommandCenterPage() {
  const [ipos, stats] = await Promise.all([getIPOs(), getSummaryStats()]);
  return <IPOCommandCenterClient ipos={ipos} stats={stats} />;
}
