// lib/v2/diagnostics.ts — D1-backed, whitelisted, read-only admin diagnostics.
import { d1All } from "@/lib/d1";

export const CHECKS = [
  "pipeline_failures", "rhp_status", "preopen_book", "eps_coverage", "twin_census",
] as const;
export type Check = (typeof CHECKS)[number];

export async function runDiagnostic(check: string): Promise<unknown[] | null> {
  switch (check) {
    case "pipeline_failures":
      return await d1All(`SELECT step, substr(stderr_tail,1,160) AS error, failed_at
        FROM pipeline_failures WHERE failed_at > datetime('now','-7 days')
        ORDER BY failed_at DESC LIMIT 20`);
    case "rhp_status":
      return await d1All(`SELECT i.name AS company_name,
          CASE WHEN EXISTS(SELECT 1 FROM research_findings rf WHERE rf.ipo_id=i.id) THEN 1 ELSE 0 END AS has_rhp,
          (SELECT decision FROM decision_history d WHERE d.ipo_id=i.id AND d.layer='company_quality'
             ORDER BY decided_at DESC LIMIT 1) AS verdict
        FROM ipo i JOIN ipo_issue ii ON ii.ipo_id=i.id
        WHERE ii.listing_date >= date('now','-7 days')
        ORDER BY ii.listing_date DESC LIMIT 25`);
    case "twin_census":
      // D1 enforces name_norm UNIQUE; any row here would indicate schema corruption.
      return await d1All(`SELECT name_norm AS canon, COUNT(*) AS n
        FROM ipo GROUP BY name_norm HAVING COUNT(*) > 1`);
    case "preopen_book":
      return await d1All(`SELECT i.nse_symbol AS symbol, COUNT(*) AS polls,
          MIN(o.observed_at) AS first, MAX(o.observed_at) AS last
        FROM listing_observations o JOIN ipo i ON i.id=o.ipo_id
        WHERE o.observation_type='preopen'
        GROUP BY i.nse_symbol ORDER BY MAX(o.observed_at) DESC LIMIT 10`);
    case "eps_coverage":
      return await d1All(`SELECT COUNT(*) AS valuation_runs,
          SUM(CASE WHEN fair_value_lo_rs IS NOT NULL OR fair_value_hi_rs IS NOT NULL THEN 1 ELSE 0 END) AS with_fair_value
        FROM valuation_runs`);
    default:
      return null;
  }
}
