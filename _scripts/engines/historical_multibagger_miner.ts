import { Command } from 'commander';
import pLimit from 'p-limit';
import { pool, closePool, getSymbols, fetchWeeklyCandles } from '../lib/db';
import { dtwDistance, normalizeShape, pct } from '../lib/indicators';

const program = new Command();
program
  .option('--concurrency <n>', 'parallel symbols', '4')
  .option('--min-return <n>', 'minimum return percent', '500')
  .option('--window-weeks <n>', 'rolling window weeks', '104')
  .option('--lookback-weeks <n>', 'lookback before breakout', '78');
program.parse(process.argv);
const opts = program.opts();

const STAGE1_CENTROID = [
  0.42,0.38,0.35,0.34,0.36,0.39,0.37,0.35,
  0.36,0.38,0.40,0.42,0.43,0.42,0.44,0.46,
  0.48,0.52,0.57,0.61,0.66,0.72,0.81,0.92,
];

function detectVolatilityContraction(closes: number[]): { compressed: boolean; compressionPct: number } {
  if (closes.length < 40) return { compressed: false, compressionPct: 999 };
  const hi = Math.max(...closes);
  const lo = Math.min(...closes);
  const mid = (hi + lo) / 2;
  const compressionPct = mid > 0 ? ((hi - lo) / mid) * 100 : 999;
  return { compressed: compressionPct <= 25, compressionPct };
}

function accumulationScore(closes: number[], volumes: Array<number | null>): number {
  if (closes.length < 24) return 0;
  const first = closes.slice(0, Math.floor(closes.length / 3));
  const middle = closes.slice(Math.floor(closes.length / 3), Math.floor((2 * closes.length) / 3));
  const last = closes.slice(Math.floor((2 * closes.length) / 3));
  const firstAvg = first.reduce((a, b) => a + b, 0) / first.length;
  const middleAvg = middle.reduce((a, b) => a + b, 0) / middle.length;
  const lastAvg = last.reduce((a, b) => a + b, 0) / last.length;
  const rangeCompression = detectVolatilityContraction(closes).compressed ? 25 : 0;
  const higherLow = lastAvg > middleAvg && middleAvg >= firstAvg * 0.9 ? 25 : 0;
  const breakoutPressure = closes[closes.length - 1] > Math.max(...closes.slice(0, -4)) * 0.95 ? 25 : 0;
  const validVolumes = volumes.filter((v): v is number => v !== null && Number.isFinite(v));
  let volumeScore = 0;
  if (validVolumes.length >= 20) {
    const early = validVolumes.slice(0, Math.floor(validVolumes.length / 2));
    const late = validVolumes.slice(Math.floor(validVolumes.length / 2));
    const earlyAvg = early.reduce((a, b) => a + b, 0) / early.length;
    const lateAvg = late.reduce((a, b) => a + b, 0) / late.length;
    if (lateAvg > earlyAvg * 1.1) volumeScore = 25;
  }
  return Math.min(100, rangeCompression + higherLow + breakoutPressure + volumeScore);
}

async function insertEvent(symbol: string, start: any, end: any, returnPct: number, windowWeeks: number): Promise<number> {
  const res = await pool.query<{ id: number }>(
    `INSERT INTO multibagger_events
     (symbol, start_date, end_date, start_close, end_close, return_pct, window_days)
     VALUES ($1,$2,$3,$4,$5,$6,$7)
     ON CONFLICT (symbol, start_date, end_date) DO UPDATE SET
      start_close = EXCLUDED.start_close,
      end_close = EXCLUDED.end_close,
      return_pct = EXCLUDED.return_pct
     RETURNING id`,
    [symbol, start.date, end.date, start.close, end.close, returnPct, windowWeeks * 7]
  );
  return res.rows[0].id;
}

async function insertPattern(symbol: string, eventId: number, lookback: any[], dtw: number) {
  const closes = lookback.map((c) => c.close);
  const volumes = lookback.map((c) => c.volume);
  const vc = detectVolatilityContraction(closes.slice(-52));
  const shape = normalizeShape(closes, 24);
  const score = accumulationScore(closes, volumes);
  const phase = {
    method: 'standardized_structural_phase_bucketing',
    phaseA: 'decline_stopped_or_base_start',
    phaseB: 'range_bound_absorption',
    phaseC: 'spring_or_final_shakeout_optional',
    phaseD: 'markup_attempt_or_higher_low',
    notes: 'Heuristic Wyckoff Stage 1 approximation. Validate against charts before capital deployment.',
  };
  await pool.query(
    `INSERT INTO multibagger_patterns
     (symbol, event_id, lookback_start, lookback_end, volatility_contraction,
      high_low_compression_pct, accumulation_score, wyckoff_phase,
      normalized_shape, dtw_distance_to_centroid)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
     ON CONFLICT (symbol, event_id) DO UPDATE SET
      volatility_contraction = EXCLUDED.volatility_contraction,
      high_low_compression_pct = EXCLUDED.high_low_compression_pct,
      accumulation_score = EXCLUDED.accumulation_score,
      wyckoff_phase = EXCLUDED.wyckoff_phase,
      normalized_shape = EXCLUDED.normalized_shape,
      dtw_distance_to_centroid = EXCLUDED.dtw_distance_to_centroid`,
    [
      symbol, eventId, lookback[0].date, lookback[lookback.length - 1].date,
      vc.compressed, vc.compressionPct, score, phase, JSON.stringify(shape), dtw,
    ]
  );
}

async function processSymbol(symbol: string) {
  const candles = await fetchWeeklyCandles(symbol, 700);
  const windowWeeks = Number(opts.windowWeeks);
  const lookbackWeeks = Number(opts.lookbackWeeks);
  const minReturn = Number(opts.minReturn);
  if (candles.length < windowWeeks + lookbackWeeks) return { symbol, events: 0 };

  let events = 0;
  let lastEventEndIndex = -999;
  for (let i = 0; i + windowWeeks < candles.length; i++) {
    const start = candles[i];
    const end = candles[i + windowWeeks];
    const ret = pct(start.close, end.close);
    if (ret >= minReturn && i - lastEventEndIndex > 26) {
      const lookbackStart = Math.max(0, i - lookbackWeeks);
      const lookback = candles.slice(lookbackStart, i + 1);
      if (lookback.length >= 40) {
        const shape = normalizeShape(lookback.map((c) => c.close), 24);
        const dtw = dtwDistance(shape, STAGE1_CENTROID);
        const eventId = await insertEvent(symbol, start, end, ret, windowWeeks);
        await insertPattern(symbol, eventId, lookback, dtw);
        events++;
        lastEventEndIndex = i + windowWeeks;
      }
    }
  }
  return { symbol, events };
}

async function ensureTables() {
  // Self-heal: the miner writes these but no migration creates them.
  await pool.query(`
    CREATE TABLE IF NOT EXISTS multibagger_events (
      id          SERIAL PRIMARY KEY,
      symbol      TEXT NOT NULL,
      start_date  DATE NOT NULL,
      end_date    DATE NOT NULL,
      start_close NUMERIC(14,4),
      end_close   NUMERIC(14,4),
      return_pct  NUMERIC(12,2),
      window_days INTEGER,
      created_at  TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE (symbol, start_date, end_date)
    )`);
  await pool.query(`
    CREATE TABLE IF NOT EXISTS multibagger_patterns (
      id                        SERIAL PRIMARY KEY,
      symbol                    TEXT NOT NULL,
      event_id                  INTEGER REFERENCES multibagger_events(id) ON DELETE CASCADE,
      lookback_start            DATE,
      lookback_end              DATE,
      volatility_contraction    BOOLEAN,
      high_low_compression_pct  NUMERIC(12,2),
      accumulation_score        NUMERIC(12,2),
      wyckoff_phase             JSONB,
      normalized_shape          JSONB,
      dtw_distance_to_centroid  NUMERIC(14,4),
      created_at                TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE (symbol, event_id)
    )`);
}

async function main() {
  await ensureTables();
  const symbols = await getSymbols('price_candles_weekly');
  const limit = pLimit(Number(opts.concurrency));
  let done = 0;
  let totalEvents = 0;
  const results = await Promise.allSettled(symbols.map((s) => limit(async () => {
    const r = await processSymbol(s);
    done++;
    totalEvents += r.events;
    if (done % 25 === 0) console.log(`Processed ${done}/${symbols.length}; events=${totalEvents}`);
    return r;
  })));
  const failed = results.filter((r) => r.status === 'rejected').length;
  console.log(`Multibagger mining complete. Symbols=${symbols.length}, events=${totalEvents}, failed=${failed}`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
}).finally(closePool);
