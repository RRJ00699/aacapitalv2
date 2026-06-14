/**
 * load-weekly-candles.ts
 * Reads data/candles/weekly/*.csv and upserts into price_candles_weekly table.
 *
 * Usage:
 *   npx tsx _scripts/loaders/load-weekly-candles.ts
 *   npx tsx _scripts/loaders/load-weekly-candles.ts --symbol=WABAG
 *   npx tsx _scripts/loaders/load-weekly-candles.ts --dry-run
 *   npx tsx _scripts/loaders/load-weekly-candles.ts --from=2023-01-01
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

const CANDLES_DIR = path.resolve(process.cwd(), "data/candles/weekly");
const BATCH_SIZE = 500;
const args = process.argv.slice(2);
const FILTER_SYMBOL = args.find((a) => a.startsWith("--symbol="))?.split("=")[1];
const DRY_RUN = args.includes("--dry-run");
const VERBOSE = args.includes("--verbose") || args.includes("-v");
const FROM_DATE = args.find((a) => a.startsWith("--from="))?.split("=")[1];

// ─── DB ──────────────────────────────────────────────────────────────────────

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || process.env.NEON_DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 5,
});

// ─── Types ───────────────────────────────────────────────────────────────────

interface WeeklyCandleRow {
  symbol: string;
  week_start: string; // YYYY-MM-DD — Monday of the week
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

// ─── Helpers ─────────────────────────────────────────────────────────────────

const MONTH_MAP: Record<string, string> = {
  Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06",
  Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12",
};

function normaliseDate(raw: string): string | null {
  if (!raw) return null;
  const s = raw.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

  // DD-Mon-YYYY
  const m1 = s.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);
  if (m1) {
    const mm = MONTH_MAP[m1[2].charAt(0).toUpperCase() + m1[2].slice(1).toLowerCase()];
    if (mm) return `${m1[3]}-${mm}-${m1[1].padStart(2, "0")}`;
  }

  // DD/MM/YYYY
  const m2 = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m2) return `${m2[3]}-${m2[2].padStart(2, "0")}-${m2[1].padStart(2, "0")}`;

  // YYYY/MM/DD
  const m3 = s.match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
  if (m3) return `${m3[1]}-${m3[2]}-${m3[3]}`;

  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().split("T")[0];
  return null;
}

/**
 * Return the Monday of the ISO week containing `dateStr`.
 * Weekly CSVs may use any day of the week as the anchor — we normalise to Monday.
 */
function toWeekStart(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = d.getUTCDay(); // 0=Sun, 1=Mon, ...6=Sat
  const diff = day === 0 ? -6 : 1 - day; // shift to Monday
  d.setUTCDate(d.getUTCDate() + diff);
  return d.toISOString().split("T")[0];
}

function parseNum(raw: string): number {
  if (!raw) return 0;
  return parseFloat(raw.replace(/,/g, "").trim()) || 0;
}

function symbolFromFilename(filename: string): string {
  return filename
    .replace(/\.csv$/i, "")
    .replace(/_weekly$/i, "")
    .replace(/^NSE_/i, "")
    .replace(/_EQ$/i, "")
    .toUpperCase();
}

function parseCsvFile(filePath: string, symbol: string): WeeklyCandleRow[] {
  const content = fs.readFileSync(filePath, "utf-8");
  const records: Record<string, string>[] = parse(content, {
    columns: true,
    skip_empty_lines: true,
    trim: true,
  });

  const rows: WeeklyCandleRow[] = [];
  const fromTs = FROM_DATE ? new Date(FROM_DATE).getTime() : 0;

  for (const rec of records) {
    const norm: Record<string, string> = {};
    for (const [k, v] of Object.entries(rec)) {
      norm[k.toLowerCase().trim()] = v;
    }

    const rawDate = norm["date"] || norm["timestamp"] || norm["week"] || norm["week_start"] || "";
    const isoDate = normaliseDate(rawDate);
    if (!isoDate) {
      if (VERBOSE) console.warn(`  ⚠ Skipping row with unparseable date in ${symbol}`);
      continue;
    }

    // Filter by --from date if set
    if (fromTs && new Date(isoDate).getTime() < fromTs) continue;

    const week_start = toWeekStart(isoDate);

    const open = parseNum(norm["open"]);
    const high = parseNum(norm["high"]);
    const low = parseNum(norm["low"]);
    const close = parseNum(norm["close"] || norm["ltp"] || norm["last"]);
    const volume = parseNum(norm["volume"] || norm["vol"] || "0");

    if (!close || !high || !low) {
      if (VERBOSE) console.warn(`  ⚠ Skipping incomplete row on ${isoDate} for ${symbol}`);
      continue;
    }

    rows.push({ symbol, week_start, open, high, low, close, volume });
  }

  // Deduplicate by week_start (keep last occurrence, i.e. end-of-week close)
  const deduped = new Map<string, WeeklyCandleRow>();
  for (const r of rows) deduped.set(r.week_start, r);

  return Array.from(deduped.values()).sort((a, b) =>
    a.week_start.localeCompare(b.week_start)
  );
}

// ─── DB Upsert ───────────────────────────────────────────────────────────────

async function upsertBatch(
  client: InstanceType<typeof Pool>["prototype"],
  rows: WeeklyCandleRow[]
): Promise<number> {
  if (rows.length === 0) return 0;

  const values: unknown[] = [];
  const placeholders: string[] = [];
  let idx = 1;

  for (const r of rows) {
    placeholders.push(
      `($${idx++},$${idx++},$${idx++},$${idx++},$${idx++},$${idx++},$${idx++})`
    );
    values.push(r.symbol, r.week_start, r.open, r.high, r.low, r.close, r.volume);
  }

  const sql = `
    INSERT INTO price_candles_weekly (symbol, week_start, open, high, low, close, volume)
    VALUES ${placeholders.join(",")}
    ON CONFLICT (symbol, week_start) DO UPDATE SET
      open       = EXCLUDED.open,
      high       = EXCLUDED.high,
      low        = EXCLUDED.low,
      close      = EXCLUDED.close,
      volume     = EXCLUDED.volume,
      updated_at = NOW()
  `;

  const result = await client.query(sql, values);
  return result.rowCount ?? rows.length;
}

// ─── Schema guard ────────────────────────────────────────────────────────────

async function ensureSchema(client: InstanceType<typeof Pool>["prototype"]): Promise<void> {
  await client.query(`
    ALTER TABLE price_candles_weekly
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()
  `);
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main() {
  console.log("═══════════════════════════════════════════");
  console.log("  AACapital — Weekly Candle Loader");
  console.log("═══════════════════════════════════════════");
  console.log(`  Source : ${CANDLES_DIR}`);
  console.log(`  Mode   : ${DRY_RUN ? "DRY RUN (no DB writes)" : "LIVE"}`);
  if (FILTER_SYMBOL) console.log(`  Filter : ${FILTER_SYMBOL}`);
  if (FROM_DATE) console.log(`  From   : ${FROM_DATE}`);
  console.log("");

  if (!process.env.DATABASE_URL && !process.env.NEON_DATABASE_URL) {
    console.error("❌ DATABASE_URL or NEON_DATABASE_URL not set");
    process.exit(1);
  }

  if (!fs.existsSync(CANDLES_DIR)) {
    console.error(`❌ Candles directory not found: ${CANDLES_DIR}`);
    process.exit(1);
  }

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
          // Show date range for dry run
          const first = rows[0]?.week_start ?? "—";
          const last = rows[rows.length - 1]?.week_start ?? "—";
          console.log(
            `  ✓ [DRY] ${symbol.padEnd(20)} ${String(rows.length).padStart(4)} weeks  ` +
            `${first} → ${last}`
          );
          result.inserted = rows.length;
        } else {
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
          const first = rows[0]?.week_start ?? "—";
          const last = rows[rows.length - 1]?.week_start ?? "—";
          console.log(
            `  ✓ ${symbol.padEnd(20)} ${String(rows.length).padStart(4)} weeks → ` +
            `${String(inserted).padStart(4)} upserted  ${first} → ${last}` +
            `${result.skipped > 0 ? `  (${result.skipped} dupes)` : ""}`
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
    console.log(`  Dupes updated   : ${totalSkipped.toLocaleString()}`);
  }

  if (failed.length > 0) {
    console.log("\n  ❌ Failures:");
    for (const r of failed) console.log(`    ${r.symbol}: ${r.error}`);
    process.exit(1);
  }

  console.log("\n✅ Weekly candle load complete\n");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
