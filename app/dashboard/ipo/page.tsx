// app/dashboard/ipo/page.tsx
// Task 5: IPO Command Center — full page wired to ipo_intelligence

import { neon } from "@neondatabase/serverless";
import IPOCommandCenterClient from "./IPOCommandCenterClient";
import type { IPOIntelligence } from "@/components/ipo/IPOIntelligenceCard";

const sql = neon(process.env.NEON_DATABASE_URL!);

export const revalidate = 900; // 15 min

async function getIPOs(): Promise<IPOIntelligence[]> {
  const r = await sql`
    SELECT
      id, company_name,
      issue_price, issue_size_cr,
      open_date AS issue_open_date,
      close_date AS issue_close_date,
      listing_date,
      suggested_action AS ipo_status,

      lqi_final AS lqi_score,
      archetype AS conviction,
      prob_10pct_profit AS p_profit_10pct,
      prob_loss_gt10 AS p_loss,
      expected_return AS expected_return_pct,

      qib_subscription, nii_subscription,
      retail_subscription, total_subscription,

      gmp_percentage, gmp_value,
      revenue_growth_3yr, pat_growth_3yr,
      pe_ratio, sector_pe_median,

      anchor_classification,
      NULL::int AS anchor_investor_count,
      ofs_percentage, promoter_holding_post,
      NULL::boolean AS is_sme,
      NULL::text AS listing_exchange

    FROM ipo_intelligence
    ORDER BY
      lqi_final DESC NULLS LAST,
      listing_date DESC NULLS LAST
    LIMIT 333
  ` as IPOIntelligence[];
  return r;
}

async function getSummaryStats() {
  const r = await sql`
    SELECT
      COUNT(*) FILTER (WHERE suggested_action = 'APPLY')                       AS open_count,
      COUNT(*) FILTER (WHERE listing_date >= CURRENT_DATE)                     AS listing_pending,
      COUNT(*) FILTER (WHERE archetype IN ('STRONG_BUY','BUY','APPLY'))        AS buy_signals,
      COUNT(*) FILTER (WHERE lqi_final >= 70)                                  AS high_lqi,
      COUNT(*) FILTER (WHERE gmp_percentage >= 20)                             AS high_gmp,
      ROUND(AVG(lqi_final)::numeric, 1)                                        AS avg_lqi,
      COUNT(*)                                                                  AS total
    FROM ipo_intelligence
  `;
  return r[0];
}

export default async function IPOCommandCenterPage() {
  const [ipos, stats] = await Promise.all([getIPOs(), getSummaryStats()]);
  return <IPOCommandCenterClient ipos={ipos} stats={stats} />;
}
