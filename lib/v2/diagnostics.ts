// lib/v2/diagnostics.ts — whitelisted, read-only admin diagnostics (Settings panel).
// V2 rewrite: checks that pointed at frozen V1 tables now read canonical ones.
// `sbi_notes` is REMOVED (the SBI parser was dropped from the V2 pipeline).
import type { SqlClient } from "./sql";

export const CHECKS = [
  "pipeline_failures", "rhp_status", "rhp_run_log", "kite_session",
  "preopen_book", "eps_coverage", "twin_census",
] as const;
export type Check = (typeof CHECKS)[number];

// Fixed queries only — no user SQL ever reaches here. Returns rows for a known
// check, or null for an unknown / intentionally-removed check (e.g. sbi_notes).
export async function runDiagnostic(sql: SqlClient, check: string): Promise<unknown[] | null> {
  switch (check) {
    case "pipeline_failures":
      return await sql`SELECT step, LEFT(stderr_tail, 160) AS error, failed_at
        FROM pipeline_failures WHERE failed_at > NOW() - interval '7 days'
        ORDER BY failed_at DESC LIMIT 20`;
    case "rhp_status":
      return await sql`SELECT i.name_display AS company_name,
          (rf.id IS NOT NULL) AS has_rhp, d.fundamental_verdict AS verdict
        FROM ipo i
        LEFT JOIN LATERAL (SELECT id FROM rhp_findings r WHERE r.ipo_id = i.id ORDER BY analyzed_at DESC LIMIT 1) rf ON true
        LEFT JOIN LATERAL (SELECT fundamental_verdict FROM decisions dd WHERE dd.ipo_id = i.id ORDER BY decided_at DESC LIMIT 1) d ON true
        WHERE i.listing_date >= CURRENT_DATE - 7 ORDER BY i.listing_date NULLS LAST LIMIT 25`;
    case "twin_census":
      return await sql`SELECT name_norm AS canon, COUNT(*) AS n, array_agg(name_display) AS names
        FROM ipo GROUP BY 1 HAVING COUNT(*) > 1`;
    case "kite_session":
      return await sql`SELECT user_id, created_at, expires_at, (expires_at > NOW()) AS valid
        FROM kite_session ORDER BY created_at DESC LIMIT 3`;
    case "rhp_run_log":
      return await sql`SELECT * FROM rhp_run_log ORDER BY 1 DESC LIMIT 5`;
    case "preopen_book":
      return await sql`SELECT symbol, COUNT(*) AS polls, MIN(captured_at) AS first, MAX(captured_at) AS last,
          MAX(lean_pct) AS max_lean, MIN(lean_pct) AS min_lean
        FROM ipo_preopen_book GROUP BY symbol ORDER BY MAX(captured_at) DESC LIMIT 10`;
    case "eps_coverage":
      return await sql`SELECT COALESCE(inputs_used->>'pe_source', '(none)') AS source, COUNT(*) AS n
        FROM valuation WHERE engine_version LIKE 'v2-score-%' AND pe IS NOT NULL GROUP BY 1 ORDER BY 2 DESC`;
    default:
      return null;
  }
}
