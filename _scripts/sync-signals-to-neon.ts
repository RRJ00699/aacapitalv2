/**
 * AACapital — Sync Technical Signals: Local Postgres → Neon
 * Task 2 dependency: sync-signals-to-neon.ts
 *
 * Reads technical_signals from LOCAL postgres (aacapital DB)
 * and upserts them into Neon's technical_signals table for Vercel to read.
 *
 * Usage:
 *   npx tsx _scripts/sync-signals-to-neon.ts
 *   npx tsx _scripts/sync-signals-to-neon.ts --clear   # clear Neon first
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

// ── schema ────────────────────────────────────────────────────────────────────

const ENSURE_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS technical_signals (
    id                  SERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    signal_date         DATE NOT NULL,

    -- Multibagger criteria (all must align)
    monthly_rsi         NUMERIC(6,2),
    monthly_rsi_ok      BOOLEAN,

    weekly_ema30        NUMERIC(12,2),
    price_above_ema30   BOOLEAN,

    weekly_ha_bullish   BOOLEAN,

    daily_nr7           BOOLEAN,
    daily_inside_bar    BOOLEAN,

    -- Composite signal
    criteria_met        INT DEFAULT 0,
    all_criteria_met    BOOLEAN DEFAULT FALSE,

    -- Multibagger score (0-100)
    mb_score            INT,
    conviction          TEXT,  -- ACCUMULATE / WATCH / AVOID

    -- DTW pattern similarity
    dtw_pattern_match   TEXT,
    dtw_similarity_pct  NUMERIC(5,2),

    -- Meta
    synced_at           TIMESTAMPTZ DEFAULT now(),
    source              TEXT DEFAULT 'local_screener',

    UNIQUE (symbol, signal_date)
  );

  CREATE INDEX IF NOT EXISTS idx_tech_signals_date   ON technical_signals (signal_date DESC);
  CREATE INDEX IF NOT EXISTS idx_tech_signals_symbol ON technical_signals (symbol);
  CREATE INDEX IF NOT EXISTS idx_tech_signals_all_met ON technical_signals (all_criteria_met) WHERE all_criteria_met = TRUE;
`;

// ── fetch from local ───────────────────────────────────────────────────────────

interface LocalSignal {
  symbol: string;
  signal_date: Date;
  monthly_rsi?: number;
  monthly_rsi_ok?: boolean;
  weekly_ema30?: number;
  price_above_ema30?: boolean;
  weekly_ha_bullish?: boolean;
  daily_nr7?: boolean;
  daily_inside_bar?: boolean;
  criteria_met?: number;
  all_criteria_met?: boolean;
  mb_score?: number;
  conviction?: string;
  dtw_pattern_match?: string;
  dtw_similarity_pct?: number;
}

async function fetchLocalSignals(local: LocalClient): Promise<LocalSignal[]> {
  // Try the exact columns that multibagger_screener.ts writes
  const result = await local.query<LocalSignal>(`
    SELECT
      symbol,
      signal_date,
      monthly_rsi,
      monthly_rsi_ok,
      weekly_ema30,
      price_above_ema30,
      weekly_ha_bullish,
      daily_nr7,
      daily_inside_bar,
      criteria_met,
      all_criteria_met,
      mb_score,
      conviction,
      dtw_pattern_match,
      dtw_similarity_pct
    FROM technical_signals
    ORDER BY signal_date DESC, mb_score DESC NULLS LAST
  `);
  return result.rows;
}

// ── upsert to Neon ─────────────────────────────────────────────────────────────

async function upsertSignals(neon: NeonClient, signals: LocalSignal[]): Promise<number> {
  let upserted = 0;

  // Batch in chunks of 100
  const CHUNK = 100;
  for (let i = 0; i < signals.length; i += CHUNK) {
    const chunk = signals.slice(i, i + CHUNK);

    for (const s of chunk) {
      await neon.query(
        `
        INSERT INTO technical_signals (
          symbol, signal_date,
          monthly_rsi, monthly_rsi_ok,
          weekly_ema30, price_above_ema30,
          weekly_ha_bullish,
          daily_nr7, daily_inside_bar,
          criteria_met, all_criteria_met,
          mb_score, conviction,
          dtw_pattern_match, dtw_similarity_pct,
          synced_at
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,now())
        ON CONFLICT (symbol, signal_date) DO UPDATE SET
          monthly_rsi         = EXCLUDED.monthly_rsi,
          monthly_rsi_ok      = EXCLUDED.monthly_rsi_ok,
          weekly_ema30        = EXCLUDED.weekly_ema30,
          price_above_ema30   = EXCLUDED.price_above_ema30,
          weekly_ha_bullish   = EXCLUDED.weekly_ha_bullish,
          daily_nr7           = EXCLUDED.daily_nr7,
          daily_inside_bar    = EXCLUDED.daily_inside_bar,
          criteria_met        = EXCLUDED.criteria_met,
          all_criteria_met    = EXCLUDED.all_criteria_met,
          mb_score            = EXCLUDED.mb_score,
          conviction          = EXCLUDED.conviction,
          dtw_pattern_match   = EXCLUDED.dtw_pattern_match,
          dtw_similarity_pct  = EXCLUDED.dtw_similarity_pct,
          synced_at           = now()
        `,
        [
          s.symbol,
          s.signal_date,
          s.monthly_rsi     ?? null,
          s.monthly_rsi_ok  ?? null,
          s.weekly_ema30    ?? null,
          s.price_above_ema30 ?? null,
          s.weekly_ha_bullish ?? null,
          s.daily_nr7       ?? null,
          s.daily_inside_bar ?? null,
          s.criteria_met    ?? null,
          s.all_criteria_met ?? null,
          s.mb_score        ?? null,
          s.conviction      ?? null,
          s.dtw_pattern_match ?? null,
          s.dtw_similarity_pct ?? null,
        ]
      );
      upserted++;
    }

    log(`  Upserted ${Math.min(i + CHUNK, signals.length)} / ${signals.length}`);
  }

  return upserted;
}

// ── summary query ──────────────────────────────────────────────────────────────

async function printSummary(neon: NeonClient) {
  const r = await neon.query(`
    SELECT
      COUNT(*)                                                  AS total,
      COUNT(*) FILTER (WHERE all_criteria_met = true)          AS strong_signals,
      COUNT(DISTINCT symbol)                                    AS unique_stocks,
      MAX(signal_date)                                          AS latest_date,
      COUNT(*) FILTER (WHERE conviction = 'ACCUMULATE')        AS accumulate_count
    FROM technical_signals
  `);
  const row = r.rows[0];
  console.log("\n" + "═".repeat(50));
  console.log("NEON — technical_signals summary");
  console.log("═".repeat(50));
  console.log(`  Total rows:        ${row.total}`);
  console.log(`  Strong signals:    ${row.strong_signals}`);
  console.log(`  Unique stocks:     ${row.unique_stocks}`);
  console.log(`  Latest date:       ${row.latest_date}`);
  console.log(`  ACCUMULATE:        ${row.accumulate_count}`);
  console.log("═".repeat(50));

  // Top signals
  const top = await neon.query(`
    SELECT symbol, mb_score, conviction, signal_date, criteria_met
    FROM technical_signals
    WHERE all_criteria_met = true
    ORDER BY mb_score DESC NULLS LAST
    LIMIT 10
  `);
  if (top.rows.length) {
    console.log("\nTOP MULTIBAGGER SIGNALS:");
    for (const r of top.rows) {
      console.log(
        `  ${r.symbol.padEnd(12)} score=${r.mb_score ?? "-"} ` +
        `${(r.conviction || "").padEnd(12)} criteria=${r.criteria_met}/5 ` +
        `date=${r.signal_date?.toISOString().substring(0,10)}`
      );
    }
  }
}

// ── main ───────────────────────────────────────────────────────────────────────

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

  // Ensure table exists in Neon
  await neon.query(ENSURE_TABLE_SQL);
  log("Neon table ensured");

  if (CLEAR_FIRST) {
    await neon.query("TRUNCATE technical_signals RESTART IDENTITY");
    log("⚠️  Neon technical_signals cleared");
  }

  // Fetch from local
  log("Fetching signals from local DB…");
  const signals = await fetchLocalSignals(local);
  log(`Found ${signals.length} signals in local DB`);

  if (!signals.length) {
    log("No signals found — run multibagger_screener.ts first");
    await local.end();
    await neon.end();
    process.exit(0);
  }

  // Upsert to Neon
  log("Upserting to Neon…");
  const count = await upsertSignals(neon, signals);
  log(`✅ ${count} signals synced to Neon`);

  await printSummary(neon);

  await local.end();
  await neon.end();

  log("\n✅ Sync complete — Multibagger Discovery tab is now live");
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
