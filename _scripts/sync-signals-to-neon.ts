/**
 * AACapital — Sync Technical Signals: Local Postgres → Neon
 * Fixed: auto-detects local column schema, never crashes on missing columns
 */

import { Client as NeonClient } from "pg";
import { Client as LocalClient } from "pg";

const NEON_URL  = process.env.NEON_DATABASE_URL!;
const LOCAL_URL =
  process.env.LOCAL_DATABASE_URL ||
  "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable";

const CLEAR_FIRST = process.argv.includes("--clear");

function log(msg: string) {
  const ts = new Date().toISOString().substring(11, 19);
  console.log(`[${ts}] ${msg}`);
}

// ── ensure Neon table has all needed columns ──────────────────────────────────

const ENSURE_NEON_SQL = `
  CREATE TABLE IF NOT EXISTS technical_signals (
    id                  SERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    signal_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    probability_score   NUMERIC,
    signal_strength     TEXT,
    action_label        TEXT,
    conviction          TEXT,
    mb_score            INT,
    criteria_met        INT DEFAULT 0,
    all_criteria_met    BOOLEAN DEFAULT FALSE,
    monthly_rsi         NUMERIC(6,2),
    monthly_rsi_ok      BOOLEAN,
    weekly_ema30        NUMERIC(12,2),
    price_above_ema30   BOOLEAN,
    weekly_ha_bullish   BOOLEAN,
    daily_nr7           BOOLEAN,
    daily_inside_bar    BOOLEAN,
    reasons             JSONB,
    synced_at           TIMESTAMPTZ DEFAULT now(),
    source              TEXT DEFAULT 'local_screener',
    UNIQUE (symbol, signal_date)
  );
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS probability_score NUMERIC;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS signal_strength TEXT;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS action_label TEXT;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS conviction TEXT;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS mb_score INT;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS criteria_met INT DEFAULT 0;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS all_criteria_met BOOLEAN DEFAULT FALSE;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS monthly_rsi NUMERIC(6,2);
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS monthly_rsi_ok BOOLEAN;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS weekly_ema30 NUMERIC(12,2);
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS price_above_ema30 BOOLEAN;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS weekly_ha_bullish BOOLEAN;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS daily_nr7 BOOLEAN;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS daily_inside_bar BOOLEAN;
  ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS reasons JSONB;
  CREATE INDEX IF NOT EXISTS idx_ts_date   ON technical_signals (signal_date DESC);
  CREATE INDEX IF NOT EXISTS idx_ts_symbol ON technical_signals (symbol);
`;

// ── detect what columns exist in local table ──────────────────────────────────

async function getLocalColumns(local: LocalClient): Promise<Set<string>> {
  const r = await local.query(`
    SELECT column_name FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'technical_signals'
  `);
  return new Set(r.rows.map((row: any) => row.column_name));
}

// ── fetch signals using only existing columns ─────────────────────────────────

async function fetchLocalSignals(local: LocalClient): Promise<any[]> {
  const cols = await getLocalColumns(local);
  log(`Local technical_signals columns: ${[...cols].join(", ")}`);

  if (cols.size === 0) {
    log("technical_signals table does not exist in local DB");
    return [];
  }

  // Build SELECT using only columns that exist
  const want = [
    "symbol", "signal_date",
    "probability_score", "signal_strength", "action_label", "conviction",
    "mb_score", "criteria_met", "all_criteria_met",
    "monthly_rsi", "monthly_rsi_ok",
    "weekly_ema30", "price_above_ema30",
    "weekly_ha_bullish", "daily_nr7", "daily_inside_bar", "reasons",
  ];

  const select = want.filter(c => cols.has(c));
  if (!cols.has("symbol")) {
    log("No symbol column — table may be empty or wrong schema");
    return [];
  }

  const orderBy = cols.has("probability_score")
    ? "probability_score DESC NULLS LAST"
    : cols.has("mb_score") ? "mb_score DESC NULLS LAST" : "symbol";

  const dateCol = cols.has("signal_date") ? "signal_date" : "CURRENT_DATE AS signal_date";
  const selectStr = select.includes("signal_date")
    ? select.join(", ")
    : [...select.filter(c => c !== "signal_date"), dateCol].join(", ");

  const result = await local.query(
    `SELECT ${selectStr} FROM technical_signals ORDER BY ${orderBy}`
  );
  return result.rows;
}

// ── upsert to Neon ─────────────────────────────────────────────────────────────

async function upsertSignals(neon: NeonClient, signals: any[]): Promise<number> {
  let upserted = 0;
  for (const s of signals) {
    const score    = s.probability_score ?? s.mb_score ?? null;
    const strength = s.signal_strength ?? null;
    const action   = s.action_label ?? s.conviction ?? null;
    const conv     = s.conviction ?? s.action_label ?? null;
    const reasons  = s.reasons ? JSON.stringify(s.reasons) : null;

    await neon.query(`
      INSERT INTO technical_signals (
        symbol, signal_date,
        probability_score, signal_strength, action_label, conviction,
        mb_score, criteria_met, all_criteria_met,
        monthly_rsi, monthly_rsi_ok,
        weekly_ema30, price_above_ema30,
        weekly_ha_bullish, daily_nr7, daily_inside_bar,
        reasons, synced_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,now())
      ON CONFLICT (symbol, signal_date) DO UPDATE SET
        probability_score = EXCLUDED.probability_score,
        signal_strength   = EXCLUDED.signal_strength,
        action_label      = EXCLUDED.action_label,
        conviction        = EXCLUDED.conviction,
        mb_score          = EXCLUDED.mb_score,
        criteria_met      = EXCLUDED.criteria_met,
        all_criteria_met  = EXCLUDED.all_criteria_met,
        monthly_rsi       = EXCLUDED.monthly_rsi,
        monthly_rsi_ok    = EXCLUDED.monthly_rsi_ok,
        weekly_ema30      = EXCLUDED.weekly_ema30,
        price_above_ema30 = EXCLUDED.price_above_ema30,
        weekly_ha_bullish = EXCLUDED.weekly_ha_bullish,
        daily_nr7         = EXCLUDED.daily_nr7,
        daily_inside_bar  = EXCLUDED.daily_inside_bar,
        reasons           = EXCLUDED.reasons,
        synced_at         = now()
    `, [
      s.symbol,
      s.signal_date ?? new Date(),
      score,
      strength,
      action,
      conv,
      s.mb_score ?? null,
      s.criteria_met ?? null,
      s.all_criteria_met ?? null,
      s.monthly_rsi ?? null,
      s.monthly_rsi_ok ?? null,
      s.weekly_ema30 ?? null,
      s.price_above_ema30 ?? null,
      s.weekly_ha_bullish ?? null,
      s.daily_nr7 ?? null,
      s.daily_inside_bar ?? null,
      reasons,
    ]);
    upserted++;
  }
  return upserted;
}

// ── summary ───────────────────────────────────────────────────────────────────

async function printSummary(neon: NeonClient) {
  const r = await neon.query(`
    SELECT COUNT(*) AS total,
           COUNT(DISTINCT symbol) AS unique_stocks,
           MAX(signal_date) AS latest_date,
           COUNT(*) FILTER (WHERE action_label = 'ACCUMULATE' OR conviction = 'ACCUMULATE') AS accumulate
    FROM technical_signals
  `);
  const row = r.rows[0];
  console.log("\n" + "═".repeat(50));
  console.log("  Neon technical_signals");
  console.log("═".repeat(50));
  console.log(`  Total rows:    ${row.total}`);
  console.log(`  Unique stocks: ${row.unique_stocks}`);
  console.log(`  Latest date:   ${row.latest_date}`);
  console.log(`  ACCUMULATE:    ${row.accumulate}`);
  console.log("═".repeat(50));

  const top = await neon.query(`
    SELECT symbol, probability_score, action_label, signal_date
    FROM technical_signals
    WHERE action_label = 'ACCUMULATE' OR conviction = 'ACCUMULATE'
    ORDER BY probability_score DESC NULLS LAST LIMIT 10
  `);
  if (top.rows.length) {
    console.log("\nTop ACCUMULATE signals:");
    for (const r of top.rows) {
      console.log(`  ${r.symbol.padEnd(14)} score=${r.probability_score ?? "-"} date=${String(r.signal_date).substring(0,10)}`);
    }
  }
}

// ── main ──────────────────────────────────────────────────────────────────────

async function main() {
  log("═".repeat(50));
  log("AACapital — Sync technical_signals: Local → Neon");
  log("═".repeat(50));

  const local = new LocalClient({ connectionString: LOCAL_URL });
  const neon  = new NeonClient({ connectionString: NEON_URL });

  await local.connect();
  log("Local Postgres connected");
  await neon.connect();
  log("Neon connected");

  await neon.query(ENSURE_NEON_SQL);
  log("Neon schema ensured");

  if (CLEAR_FIRST) {
    await neon.query("TRUNCATE technical_signals RESTART IDENTITY");
    log("Neon technical_signals cleared");
  }

  const signals = await fetchLocalSignals(local);
  log(`Found ${signals.length} signals in local DB`);

  if (!signals.length) {
    log("No signals — run: npx tsx _scripts/engines/multibagger_screener.ts first");
    await local.end(); await neon.end();
    process.exit(0);
  }

  const count = await upsertSignals(neon, signals);
  log(`✅ ${count} signals synced to Neon`);

  await printSummary(neon);
  await local.end();
  await neon.end();
  log("✅ Sync complete");
}

main().catch(err => { console.error("FATAL:", err); process.exit(1); });
