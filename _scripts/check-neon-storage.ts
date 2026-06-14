/**
 * _scripts/check-neon-storage.ts
 * Monitors Neon DB storage and runs purge strategy.
 * 
 * Usage:
 *   npx tsx _scripts/check-neon-storage.ts
 *   npx tsx _scripts/check-neon-storage.ts --purge
 */

import { Pool } from "pg";
import * as dotenv from "dotenv";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

const NEON_FREE_LIMIT_BYTES = 512 * 1024 * 1024;
const WARN_THRESHOLD  = 0.70;
const PURGE_THRESHOLD = 0.85;

const args     = process.argv.slice(2);
const DO_PURGE = args.includes("--purge");

// ── Tables that belong in LOCAL Postgres only ─────────────────────────────────
const LOCAL_ONLY_TABLES = [
  "price_candles",
  "price_candles_weekly",
  "price_weekly",      // legacy table from v1
  "price_monthly",     // legacy table from v1
];

// ── Purge strategies — column names verified against actual schema ─────────────
const PURGE_STRATEGIES: Record<string, { description: string; sql: string }> = {
  price_candles: {
    description: "Truncate — belongs in local Postgres",
    sql: "TRUNCATE TABLE price_candles",
  },
  price_candles_weekly: {
    description: "Truncate — belongs in local Postgres",
    sql: "TRUNCATE TABLE price_candles_weekly",
  },
  price_weekly: {
    description: "Truncate — legacy v1 table, belongs in local Postgres",
    sql: "TRUNCATE TABLE price_weekly",
  },
  price_monthly: {
    description: "Truncate — legacy v1 table, belongs in local Postgres",
    sql: "TRUNCATE TABLE price_monthly",
  },
  nse_shareholding_filings_raw: {
    description: "Truncate raw filings — data already processed into shareholding_history",
    sql: "TRUNCATE TABLE nse_shareholding_filings_raw",
  },
  intelligence_jobs: {
    description: "Delete completed jobs (keep last 30 days)",
    sql: "DELETE FROM intelligence_jobs WHERE created_at < NOW() - INTERVAL '30 days'",
  },
  market_regimes: {
    description: "Keep only last 2 years",
    sql: `DELETE FROM market_regimes 
          WHERE evaluation_date < NOW() - INTERVAL '2 years'
          `,
  },
  market_snapshot: {
    description: "Keep only last 30 days",
    sql: `DELETE FROM market_snapshot 
          WHERE last_updated < NOW() - INTERVAL '30 days'
          
          `,
  },
  daily_institutional_flows: {
    description: "Keep only last 1 year",
    sql: `DELETE FROM daily_institutional_flows 
          WHERE (date IS NOT NULL AND date < NOW() - INTERVAL '1 year')
             OR (flow_date IS NOT NULL AND flow_date < NOW() - INTERVAL '1 year')`,
  },
};

function bar(used: number, total: number, width = 30): string {
  const pct    = Math.min(used / total, 1);
  const filled = Math.round(pct * width);
  const color  = pct > 0.85 ? "🔴" : pct > 0.70 ? "🟡" : "🟢";
  return `${color} [${"█".repeat(filled)}${"░".repeat(width - filled)}]`;
}

function fmt(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024)        return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

async function getTableColumns(client: any, table: string): Promise<string[]> {
  const { rows } = await client.query(
    `SELECT column_name FROM information_schema.columns 
     WHERE table_schema='public' AND table_name=$1`,
    [table]
  );
  return rows.map((r: any) => r.column_name);
}

async function checkStorage(pool: Pool) {
  const client = await pool.connect();
  try {
    const { rows: tables } = await client.query(`
      SELECT 
        tablename,
        pg_total_relation_size('public.'||tablename) AS total_bytes
      FROM pg_tables
      WHERE schemaname = 'public'
      ORDER BY pg_total_relation_size('public.'||tablename) DESC
    `);

    const { rows: [{ total_bytes }] } = await client.query(`
      SELECT COALESCE(SUM(pg_total_relation_size('public.'||tablename)),0) AS total_bytes
      FROM pg_tables WHERE schemaname = 'public'
    `);

    const usedBytes = parseInt(total_bytes) || 0;
    const pctUsed   = usedBytes / NEON_FREE_LIMIT_BYTES;

    console.log("\n═══════════════════════════════════════════════════════");
    console.log("  AACapital — Neon Storage Monitor");
    console.log("═══════════════════════════════════════════════════════");
    console.log(`  Free tier limit : ${fmt(NEON_FREE_LIMIT_BYTES)}`);
    console.log(`  Used            : ${fmt(usedBytes)} (${(pctUsed * 100).toFixed(1)}%)`);
    console.log(`  Available       : ${fmt(NEON_FREE_LIMIT_BYTES - usedBytes)}`);
    console.log(`  ${bar(usedBytes, NEON_FREE_LIMIT_BYTES)}\n`);

    if (pctUsed >= 1.0)             console.log("  ❌ OVER LIMIT — writes failing");
    else if (pctUsed >= PURGE_THRESHOLD) console.log(`  🔴 CRITICAL — run --purge`);
    else if (pctUsed >= WARN_THRESHOLD)  console.log(`  🟡 WARNING — monitor closely`);
    else                            console.log("  🟢 HEALTHY");

    console.log(`\n  ${"Table".padEnd(38)} ${"Size".padStart(12)}  ${"Rows".padStart(10)}  Note`);
    console.log("  " + "─".repeat(85));

    let localOnlyTotal = 0;
    for (const row of tables) {
      const bytes = parseInt(row.total_bytes) || 0;
      if (bytes < 8192) continue;

      let rowCount = "—";
      try {
        const { rows: [{ count }] } = await client.query(`SELECT COUNT(*) as count FROM "${row.tablename}"`);
        rowCount = parseInt(count).toLocaleString();
      } catch {}

      const isLocal  = LOCAL_ONLY_TABLES.includes(row.tablename);
      const hasPurge = row.tablename in PURGE_STRATEGIES && !isLocal;
      const pct      = bytes / NEON_FREE_LIMIT_BYTES * 100;
      const note     = isLocal ? "⚠ MOVE TO LOCAL" : hasPurge ? "♻ purgeable" : "✓ keep";
      const pctStr   = pct >= 1 ? ` (${pct.toFixed(0)}%)` : "";

      if (isLocal) localOnlyTotal += bytes;
      console.log(`  ${row.tablename.padEnd(38)} ${fmt(bytes).padStart(10)}${pctStr.padEnd(6)}  ${rowCount.padStart(10)}  ${note}`);
    }

    if (localOnlyTotal > 0) {
      console.log(`\n  ⚠ Tables that belong in local Postgres: ${fmt(localOnlyTotal)}`);
      console.log(`    Run: npx tsx _scripts/check-neon-storage.ts --purge`);
    }

    // GitHub Actions output
    if (process.env.GITHUB_OUTPUT) {
      const fs = await import("fs");
      fs.appendFileSync(process.env.GITHUB_OUTPUT,
        `neon_used_mb=${(usedBytes/1024/1024).toFixed(1)}\n` +
        `neon_pct=${(pctUsed*100).toFixed(1)}\n` +
        `neon_status=${pctUsed >= PURGE_THRESHOLD ? "critical" : pctUsed >= WARN_THRESHOLD ? "warning" : "ok"}\n`
      );
    }

    return { usedBytes, pctUsed };
  } finally {
    client.release();
  }
}

async function runPurge(pool: Pool) {
  console.log("\n═══════════════════════════════════════════════════════");
  console.log("  Purge Strategy");
  console.log("═══════════════════════════════════════════════════════");

  const client = await pool.connect();
  try {
    for (const [table, strategy] of Object.entries(PURGE_STRATEGIES)) {
      // Check table exists
      const { rows: [{ exists }] } = await client.query(
        `SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1) as exists`,
        [table]
      );
      if (!exists) { console.log(`  ○ ${table.padEnd(38)} — not found`); continue; }

      // Check row count
      const { rows: [{ count }] } = await client.query(`SELECT COUNT(*) as count FROM "${table}"`);
      if (parseInt(count) === 0) { console.log(`  ○ ${table.padEnd(38)} — already empty`); continue; }

      console.log(`  → ${table.padEnd(38)} ${strategy.description}`);
      try {
        await client.query(strategy.sql);
        console.log(`  ✓ Done`);
      } catch (e: any) {
        // If SQL failed due to wrong column, try to diagnose
        const cols = await getTableColumns(client, table);
        console.log(`  ✗ Failed. Columns in ${table}: ${cols.join(", ")}`);
      }
    }

    console.log("\n  Running VACUUM ANALYZE...");
    await client.query("VACUUM ANALYZE");
    console.log("  ✓ Done\n");
  } finally {
    client.release();
  }

  await checkStorage(pool);
}

async function main() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL || process.env.NEON_DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    max: 3,
  });

  try {
    const { pctUsed } = await checkStorage(pool);
    if (DO_PURGE) {
      await runPurge(pool);
    } else if (pctUsed >= PURGE_THRESHOLD) {
      console.log("\n  Run: npx tsx _scripts/check-neon-storage.ts --purge");
    }
    if (pctUsed >= 1.0) process.exit(2);
    if (pctUsed >= PURGE_THRESHOLD && !DO_PURGE) process.exit(1);
  } finally {
    await pool.end();
  }
}

main().catch(err => { console.error("Fatal:", err); process.exit(1); });
