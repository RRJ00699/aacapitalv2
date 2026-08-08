#!/usr/bin/env node
/**
 * _scripts/check-env.ts
 * Quick sanity-check: verifies all required env vars are set and DB is reachable.
 * Run before deploying or after rotating credentials.
 *
 * Usage: npx tsx _scripts/check-env.ts
 */

import { Pool } from "pg";
import * as dotenv from "dotenv";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

const REQUIRED_VARS = [
  "DATABASE_URL",
  "NEON_DATABASE_URL",
  "ANTHROPIC_API_KEY",
  "SCREENER_USERNAME",
  "SCREENER_PASSWORD",
] as const;

const OPTIONAL_VARS = [
  "NEXT_PUBLIC_APP_URL",
  "VERCEL_URL",
] as const;

async function main() {
  console.log("═══════════════════════════════════════════");
  console.log("  AACapital — Environment Check");
  console.log("═══════════════════════════════════════════\n");

  let allOk = true;

  // ── Required vars ──
  console.log("Required secrets:");
  for (const key of REQUIRED_VARS) {
    const val = process.env[key];
    if (!val) {
      console.log(`  ✗ ${key.padEnd(30)} MISSING`);
      allOk = false;
    } else {
      // Show first/last 4 chars only
      const masked =
        val.length > 12
          ? `${val.slice(0, 4)}${"*".repeat(Math.min(val.length - 8, 20))}${val.slice(-4)}`
          : "****";
      console.log(`  ✓ ${key.padEnd(30)} ${masked}`);
    }
  }

  // ── Optional vars ──
  console.log("\nOptional vars:");
  for (const key of OPTIONAL_VARS) {
    const val = process.env[key];
    console.log(`  ${val ? "✓" : "○"} ${key.padEnd(30)} ${val ?? "(not set)"}`);
  }

  // ── DB connectivity ──
  console.log("\nDatabase connectivity:");
  const connStr = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL;
  if (!connStr) {
    console.log("  ✗ No DATABASE_URL — skipping connectivity test");
    allOk = false;
  } else {
    const pool = new Pool({
      connectionString: connStr,
      ssl: { rejectUnauthorized: false },
      connectionTimeoutMillis: 5000,
    });
    try {
      const client = await pool.connect();
      const { rows } = await client.query(`
        SELECT
          COUNT(*) FILTER (WHERE table_name = 'company_master')  AS has_company_master,
          COUNT(*) FILTER (WHERE table_name = 'price_candles')   AS has_price_candles,
          COUNT(*) FILTER (WHERE table_name = 'ipo_live')        AS has_ipo_live
        FROM information_schema.tables
        WHERE table_schema = 'public'
      `);
      client.release();
      await pool.end();

      const r = rows[0];
      console.log(`  ✓ Connected to Neon DB`);
      console.log(`    company_master   : ${r.has_company_master === "1" ? "✓ exists" : "✗ missing"}`);
      console.log(`    price_candles    : ${r.has_price_candles === "1" ? "✓ exists" : "✗ missing"}`);
      console.log(`    ipo_live         : ${r.has_ipo_live === "1" ? "✓ exists" : "✗ missing — run sql/ipo_schema.sql"}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.log(`  ✗ DB connection failed: ${msg}`);
      allOk = false;
    }
  }

  // ── Anthropic API ──
  console.log("\nAnthropic API:");
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    console.log("  ✗ ANTHROPIC_API_KEY not set");
    allOk = false;
  } else if (!apiKey.startsWith("sk-ant-")) {
    console.log("  ⚠ ANTHROPIC_API_KEY looks malformed (should start with sk-ant-)");
    allOk = false;
  } else {
    console.log("  ✓ ANTHROPIC_API_KEY format looks correct");
  }

  console.log("\n═══════════════════════════════════════════");
  if (allOk) {
    console.log("✅ All checks passed — ready to deploy\n");
  } else {
    console.log("❌ Some checks failed — fix above issues first\n");
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
