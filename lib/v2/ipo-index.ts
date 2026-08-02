// lib/v2/ipo-index.ts — full-universe identity index for the /dashboard/ipo2 search.
// V2 rewrite: reads the canonical `ipo` table (was V1 `ipo_consolidated`).
import type { SqlClient } from "./sql";

export async function buildIpoIndex(sql: SqlClient) {
  const rows = await sql`
    SELECT name_display AS company_name,
           symbol       AS sym,
           listing_date
    FROM ipo
    WHERE name_display IS NOT NULL
    ORDER BY listing_date DESC NULLS LAST`;
  return { rows, generated_at: new Date().toISOString() };
}
