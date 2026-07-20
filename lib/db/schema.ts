/**
 * lib/db/schema.ts
 * Compatibility shim — getDb() for existing app routes (auth, market-regime).
 * Delegates to lib/db.ts (pg-based connection).
 */

import { sql } from '@/lib/db';

/** getDb() — returns sql tagged-template. Used by auth + market-regime routes. */
export function getDb() {
  return sql;
}
// initDb() removed 2026-07-20: its only caller was /api/db/init (archived —
// zero consumers) and it verified equity-era tables (company_master, amfi_*,
// management_commentary) that the IPO-only product no longer owns.
// Preserved in _archive/routes/api-db-init-route.ts.txt.
