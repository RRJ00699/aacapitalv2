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
      issue_open_date, issue_close_date, listing_date,
      ipo_status,

      lqi_score, conviction,
      p_profit_10pct, p_loss, expected_return_pct,

      qib_subscription, nii_subscription,
      retail_subscription, total_subscription,

      gmp_percentage, gmp_value,
      revenue_growth_3yr, pat_growth_3yr,
      pe_ratio, sector_pe_median,

      anchor_classification, anchor_investor_count,
      ofs_percentage, promoter_holding_post,
      is_sme, listing_exchange

    FROM ipo_intelligence
    ORDER BY
      CASE ipo_status
        WHEN 'OPEN'               THEN 1
        WHEN 'LISTING_PENDING'    THEN 2
        WHEN 'ALLOTMENT_PENDING'  THEN 3
        WHEN 'CLOSED'             THEN 4
        WHEN 'LISTED'             THEN 5
        ELSE 6
      END,
      listing_date DESC NULLS LAST
    LIMIT 333
  ` as IPOIntelligence[];
  return r;
}

async function getSummaryStats() {
  const r = await sql`
    SELECT
      COUNT(*) FILTER (WHERE ipo_status = 'OPEN')                              AS open_count,
      COUNT(*) FILTER (WHERE ipo_status = 'LISTING_PENDING')                   AS listing_pending,
      COUNT(*) FILTER (WHERE conviction IN ('STRONG_BUY','BUY'))               AS buy_signals,
      COUNT(*) FILTER (WHERE lqi_score >= 70)                                  AS high_lqi,
      COUNT(*) FILTER (WHERE gmp_percentage >= 20)                             AS high_gmp,
      ROUND(AVG(lqi_score)::numeric, 1)                                        AS avg_lqi,
      COUNT(*)                                                                  AS total
    FROM ipo_intelligence
  `;
  return r[0];
}

export default async function IPOCommandCenterPage() {
  const [ipos, stats] = await Promise.all([getIPOs(), getSummaryStats()]);
  return <IPOCommandCenterClient ipos={ipos} stats={stats} />;
}
