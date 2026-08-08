/**
 * load-daily-candles.ts
 * Reads data/candles/daily/*.csv and upserts into price_candles table.
 *
 * Usage:
 *   npx tsx _scripts/loaders/load-daily-candles.ts
 *   npx tsx _scripts/loaders/load-daily-candles.ts --symbol=WABAG
 *   npx tsx _scripts/loaders/load-daily-candles.ts --dry-run
 *
 * CSV format expected (standard NSE/Screener export):
 *   Date,Open,High,Low,Close,Volume
 *   OR: date,open,high,low,close,volume  (lowercase headers also handled)
 *
 * Environment: DATABASE_URL must be set (pg Pool connection string)
 */

import fs from "fs";
import path from "path";
import { parse } from "csv-parse/sync";
import { Pool } from "pg";
import * as dotenv from "dotenv";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

// ─── Config ──────────────────────────────────────────────────────────────────

const CANDLES_DIR = path.resolve(process.cwd(), "data/candles/daily");
const BATCH_SIZE = 500; // rows per INSERT batch
const args = process.argv.slice(2);
const FILTER_SYMBOL = args.find((a) => a.startsWith("--symbol="))?.split("=")[1];
const DRY_RUN = args.includes("--dry-run");
const VERBOSE = args.includes("--verbose") || args.includes("-v");

// ─── DB ──────────────────────────────────────────────────────────────────────

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || process.env.NEON_DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 5,
});

// ─── Types ───────────────────────────────────────────────────────────────────

interface CandleRow {
  symbol: string;
  date: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface LoadResult {
  symbol: string;
  file: string;
  rows: number;
  inserted: number;
  skipped: number;
  error?: string;
}

// ─── CSV Parsing ─────────────────────────────────────────────────────────────

/**
 * Normalise a raw CSV date string to YYYY-MM-DD.
 * Handles: 2024-01-15, 15-Jan-2024, 15/01/2024, Jan 15 2024
 */
function normaliseDate(raw: string): string | null {
  if (!raw) return null;
  const s = raw.trim();

  // Already ISO
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

  // DD-Mon-YYYY  e.g. 15-Jan-2024
  const monMap: Record<string, string> = {
    Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06",
    Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12",
  };
  const ddMonYYYY = s.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);
  if (ddMonYYYY) {
    const [, d, m, y] = ddMonYYYY;
    const mm = monMap[m.charAt(0).toUpperCase() + m.slice(1).toLowerCase()];
    if (mm) return `${y}-${mm}-${d.padStart(2, "0")}`;
  }

  // DD/MM/YYYY
  const ddSlash = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (ddSlash) {
    const [, d, m, y] = ddSlash;
    return `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
  }

  // Try native Date parse as last resort
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().split("T")[0];

  return null;
}

/**
 * Parse a number string, removing commas and handling empty values.
 */
function parseNum(raw: string): number {
  if (!raw) return 0;
  return parseFloat(raw.replace(/,/g, "").trim()) || 0;
}

/**
 * Infer symbol from filename. Expects filenames like:
 *   WABAG.csv, WABAG_daily.csv, NSE_WABAG_EQ.csv
 */
function symbolFromFilename(filename: string): string {
  return filename
    .replace(/\.csv$/i, "")
    .replace(/_daily$/i, "")
    .replace(/^NSE_/i, "")
    .replace(/_EQ$/i, "")
    .toUpperCase();
}

/**
 * Parse a single CSV file into CandleRow[].
 */
function parseCsvFile(filePath: string, symbol: string): CandleRow[] {
  const content = fs.readFileSync(filePath, "utf-8");
  const records: Record<string, string>[] = parse(content, {
    columns: true,
    skip_empty_lines: true,
    trim: true,
  });

  const rows: CandleRow[] = [];

  for (const rec of records) {
    // Normalise column names to lowercase
    const norm: Record<string, string> = {};
    for (const [k, v] of Object.entries(rec)) {
      norm[k.toLowerCase().trim()] = v;
    }

    const date = normaliseDate(norm["date"] || norm["timestamp"] || norm["time"] || "");
    if (!date) {
      if (VERBOSE) console.warn(`  ⚠ Skipping row with unparseable date in ${symbol}`);
      continue;
    }

    const open = parseNum(norm["open"]);
    const high = parseNum(norm["high"]);
    const low = parseNum(norm["low"]);
    const close = parseNum(norm["close"] || norm["ltp"] || norm["last"]);
    const volume = parseNum(norm["volume"] || norm["vol"] || "0");

    if (!close || !high || !low) {
      if (VERBOSE) console.warn(`  ⚠ Skipping incomplete row on ${date} for ${symbol}`);
      continue;
    }

    rows.push({ symbol, date, open, high, low, close, volume });
  }

  return rows;
}

// ─── DB Upsert ───────────────────────────────────────────────────────────────

/**
 * Upsert a batch of candle rows into price_candles.
 * Uses ON CONFLICT DO NOTHING so re-runs are safe.
 */
async function upsertBatch(client: InstanceType<typeof Pool>["prototype"], rows: CandleRow[]): Promise<number> {
  if (rows.length === 0) return 0;

  const values: unknown[] = [];
  const placeholders: string[] = [];
  let idx = 1;

  for (const r of rows) {
    placeholders.push(`($${idx++},$${idx++},$${idx++},$${idx++},$${idx++},$${idx++},$${idx++})`);
    values.push(r.symbol, r.date, r.open, r.high, r.low, r.close, r.volume);
  }

  const sql = `
    INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
    VALUES ${placeholders.join(",")}
    ON CONFLICT (symbol, date) DO UPDATE SET
      open   = EXCLUDED.open,
      high   = EXCLUDED.high,
      low    = EXCLUDED.low,
      close  = EXCLUDED.close,
      volume = EXCLUDED.volume,
      updated_at = NOW()
  `;

  const result = await client.query(sql, values);
  return result.rowCount ?? rows.length;
}

// ─── Schema guard ────────────────────────────────────────────────────────────

async function ensureSchema(client: InstanceType<typeof Pool>["prototype"]): Promise<void> {
  // Add updated_at if it doesn't exist (non-destructive migration)
  await client.query(`
    ALTER TABLE price_candles
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()
  `);
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main() {
  console.log("═══════════════════════════════════════════");
  console.log("  AACapital — Daily Candle Loader");
  console.log("═══════════════════════════════════════════");
  console.log(`  Source : ${CANDLES_DIR}`);
  console.log(`  Mode   : ${DRY_RUN ? "DRY RUN (no DB writes)" : "LIVE"}`);
  if (FILTER_SYMBOL) console.log(`  Filter : ${FILTER_SYMBOL}`);
  console.log("");

  if (!process.env.DATABASE_URL && !process.env.NEON_DATABASE_URL) {
    console.error("❌ DATABASE_URL or NEON_DATABASE_URL not set");
    process.exit(1);
  }

  if (!fs.existsSync(CANDLES_DIR)) {
    console.error(`❌ Candles directory not found: ${CANDLES_DIR}`);
    process.exit(1);
  }

  // List CSV files
  const allFiles = fs.readdirSync(CANDLES_DIR).filter((f) => f.endsWith(".csv"));
  const files = FILTER_SYMBOL
    ? allFiles.filter((f) => symbolFromFilename(f) === FILTER_SYMBOL.toUpperCase())
    : allFiles;

  if (files.length === 0) {
    console.warn("⚠ No CSV files found");
    process.exit(0);
  }
  console.log(`📂 Found ${files.length} CSV file(s)\n`);

  const client = await pool.connect();
  const results: LoadResult[] = [];
  let totalInserted = 0;
  let totalSkipped = 0;

  try {
    if (!DRY_RUN) {
      await ensureSchema(client);
    }

    for (const file of files) {
      const symbol = symbolFromFilename(file);
      const filePath = path.join(CANDLES_DIR, file);
      const result: LoadResult = { symbol, file, rows: 0, inserted: 0, skipped: 0 };

      try {
        const rows = parseCsvFile(filePath, symbol);
        result.rows = rows.length;

        if (DRY_RUN) {
          console.log(`  ✓ [DRY] ${symbol.padEnd(20)} ${rows.length} rows parsed`);
          result.inserted = rows.length;
        } else {
          // Batch insert
          let inserted = 0;
          for (let i = 0; i < rows.length; i += BATCH_SIZE) {
            const batch = rows.slice(i, i + BATCH_SIZE);
            const count = await upsertBatch(client, batch);
            inserted += count;
          }
          result.inserted = inserted;
          result.skipped = rows.length - inserted;
          totalInserted += inserted;
          totalSkipped += result.skipped;
          console.log(
            `  ✓ ${symbol.padEnd(20)} ${String(rows.length).padStart(5)} rows → ` +
            `${String(inserted).padStart(5)} inserted  ${result.skipped > 0 ? `(${result.skipped} dupes)` : ""}`
          );
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        result.error = msg;
        console.error(`  ✗ ${symbol.padEnd(20)} ERROR: ${msg}`);
      }

      results.push(result);
    }
  } finally {
    client.release();
    await pool.end();
  }

  // ── Summary ──
  const succeeded = results.filter((r) => !r.error);
  const failed = results.filter((r) => r.error);

  console.log("\n═══════════════════════════════════════════");
  console.log("  Summary");
  console.log("═══════════════════════════════════════════");
  console.log(`  Files processed : ${files.length}`);
  console.log(`  Succeeded       : ${succeeded.length}`);
  console.log(`  Failed          : ${failed.length}`);
  if (!DRY_RUN) {
    console.log(`  Rows inserted   : ${totalInserted.toLocaleString()}`);
    console.log(`  Dupes skipped   : ${totalSkipped.toLocaleString()}`);
  }

  if (failed.length > 0) {
    console.log("\n  ❌ Failures:");
    for (const r of failed) {
      console.log(`    ${r.symbol}: ${r.error}`);
    }
    process.exit(1);
  }

  console.log("\n✅ Daily candle load complete\n");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
