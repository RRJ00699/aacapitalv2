/**
 * lib/db/schema.ts
 * Compatibility shim — restores getDb() and initDb() for existing app routes.
 * Delegates to lib/db.ts (pg-based connection).
 */

import { sql } from '@/lib/db';

/** getDb() — returns sql tagged-template. Used by watchlists, thesis, ipo/gmp, auth routes. */
export function getDb() {
  return sql;
}

/** initDb() — verifies DB is reachable and core tables exist. */
export async function initDb(): Promise<{ tables: string[]; status: string }> {
  const result = await sql`
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN (
      'company_master','quarterly_results','earnings_acceleration_scores',
      'management_commentary','management_commentary_scores',
      'amfi_category_flows','amfi_commentary_scores','intelligence_jobs'
    )
    ORDER BY table_name
  `;
  const tables = result.map((r: any) => r.table_name);
  return { tables, status: 'ok' };
}
