// _scripts/engines/multibagger_similarity_engine.ts
// Builds Historical Similarity matches: current weekly structures vs mined multibagger patterns.
// Usage:
//   npx tsx _scripts/engines/multibagger_similarity_engine.ts --limit 300 --top 5
//   npx tsx _scripts/engines/multibagger_similarity_engine.ts --symbol NETWEB --top 5

import { Command } from 'commander';
import pLimit from 'p-limit';
import { pool, closePool, getSymbols, fetchWeeklyCandles } from '../lib/db';
import {
  normalizeShape,
  dtwDistance,
  distanceToSimilarity,
  probabilityFromSimilarity,
  classifyTier,
} from '../../lib/intelligence/historical-similarity';

const program = new Command();
program
  .option('--symbol <symbol>', 'single symbol to refresh')
  .option('--limit <n>', 'max symbols to process', '500')
  .option('--top <n>', 'top historical matches per symbol', '5')
  .option('--lookback-weeks <n>', 'current structure lookback', '78')
  .option('--concurrency <n>', 'parallel symbols', '4')
  .option('--min-score <n>', 'minimum similarity score to store', '55');
program.parse(process.argv);
const opts = program.opts();

type HistoricalPattern = {
  event_id: number;
  symbol: string;
  start_date: string;
  end_date: string;
  return_pct: number;
  normalized_shape: number[];
};

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS multibagger_similarity (
      id BIGSERIAL PRIMARY KEY,
      symbol TEXT NOT NULL,
      similar_to TEXT NOT NULL,
      historical_event_id BIGINT,
      historical_start_date DATE,
      historical_end_date DATE,
      historical_return_pct NUMERIC,
      historical_tier TEXT,
      similarity_score NUMERIC NOT NULL,
      dtw_distance NUMERIC,
      current_shape JSONB,
      historical_shape JSONB,
      p_2x NUMERIC,
      p_5x NUMERIC,
      p_10x NUMERIC,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      notes TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE(symbol, similar_to, historical_event_id)
    )
  `);
  await pool.query(`CREATE INDEX IF NOT EXISTS idx_multibagger_similarity_symbol ON multibagger_similarity(symbol, similarity_score DESC)`);
  await pool.query(`CREATE INDEX IF NOT EXISTS idx_multibagger_similarity_score ON multibagger_similarity(similarity_score DESC)`);
}

async function loadHistoricalPatterns(): Promise<HistoricalPattern[]> {
  const result = await pool.query(`
    SELECT
      p.event_id,
      p.symbol,
      e.start_date::text,
      e.end_date::text,
      e.return_pct,
      p.normalized_shape
    FROM multibagger_patterns p
    JOIN multibagger_events e ON e.id = p.event_id
    WHERE p.normalized_shape IS NOT NULL
      AND e.return_pct >= 100
    ORDER BY e.return_pct DESC
  `);

  return result.rows
    .map((r) => ({
      event_id: Number(r.event_id),
      symbol: String(r.symbol || '').toUpperCase(),
      start_date: r.start_date,
      end_date: r.end_date,
      return_pct: Number(r.return_pct || 0),
      normalized_shape: Array.isArray(r.normalized_shape) ? r.normalized_shape.map(Number) : [],
    }))
    .filter((r) => r.normalized_shape.length >= 12);
}

async function upsertMatch(symbol: string, currentShape: number[], match: HistoricalPattern, distance: number, similarityScore: number) {
  const probs = probabilityFromSimilarity(similarityScore, match.return_pct);
  await pool.query(
    `INSERT INTO multibagger_similarity
      (symbol, similar_to, historical_event_id, historical_start_date, historical_end_date,
       historical_return_pct, historical_tier, similarity_score, dtw_distance,
       current_shape, historical_shape, p_2x, p_5x, p_10x, status, notes, updated_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13,$14,'ACTIVE',$15,NOW())
     ON CONFLICT (symbol, similar_to, historical_event_id) DO UPDATE SET
       historical_return_pct = EXCLUDED.historical_return_pct,
       historical_tier = EXCLUDED.historical_tier,
       similarity_score = EXCLUDED.similarity_score,
       dtw_distance = EXCLUDED.dtw_distance,
       current_shape = EXCLUDED.current_shape,
       historical_shape = EXCLUDED.historical_shape,
       p_2x = EXCLUDED.p_2x,
       p_5x = EXCLUDED.p_5x,
       p_10x = EXCLUDED.p_10x,
       status = 'ACTIVE',
       notes = EXCLUDED.notes,
       updated_at = NOW()`,
    [
      symbol,
      match.symbol,
      match.event_id,
      match.start_date,
      match.end_date,
      match.return_pct,
      classifyTier(match.return_pct),
      similarityScore,
      distance,
      JSON.stringify(currentShape),
      JSON.stringify(match.normalized_shape),
      probs.p2x,
      probs.p5x,
      probs.p10x,
      `Current ${opts.lookbackWeeks}W structure matched historical multibagger setup`,
    ]
  );
}

async function processSymbol(symbol: string, patterns: HistoricalPattern[]) {
  const candles = await fetchWeeklyCandles(symbol, Number(opts.lookbackWeeks));
  if (candles.length < 40) return { symbol, stored: 0, reason: 'not enough weekly candles' };

  const currentShape = normalizeShape(candles.map((c) => c.close), 24);
  if (currentShape.length < 12) return { symbol, stored: 0, reason: 'shape failed' };

  const matches = patterns
    .filter((p) => p.symbol !== symbol)
    .map((p) => {
      const distance = dtwDistance(currentShape, p.normalized_shape);
      return { pattern: p, distance, similarityScore: distanceToSimilarity(distance) };
    })
    .filter((m) => m.similarityScore >= Number(opts.minScore))
    .sort((a, b) => b.similarityScore - a.similarityScore || b.pattern.return_pct - a.pattern.return_pct)
    .slice(0, Number(opts.top));

  await pool.query(`UPDATE multibagger_similarity SET status = 'STALE' WHERE symbol = $1`, [symbol]);

  for (const m of matches) {
    await upsertMatch(symbol, currentShape, m.pattern, m.distance, m.similarityScore);
  }

  return { symbol, stored: matches.length, reason: matches.length ? 'ok' : 'no match above threshold' };
}

async function main() {
  await ensureTable();
  const patterns = await loadHistoricalPatterns();
  if (patterns.length === 0) {
    throw new Error('No historical multibagger patterns found. Run _scripts/engines/historical_multibagger_miner.ts first.');
  }

  const symbols = opts.symbol
    ? [String(opts.symbol).toUpperCase()]
    : (await getSymbols('price_candles_weekly')).slice(0, Number(opts.limit));

  const limit = pLimit(Number(opts.concurrency));
  let done = 0;
  let stored = 0;

  await Promise.all(symbols.map((s) => limit(async () => {
    const r = await processSymbol(s, patterns);
    done += 1;
    stored += r.stored;
    if (done % 25 === 0 || opts.symbol) console.log(`[similarity] ${done}/${symbols.length}; stored=${stored}; latest=${r.symbol}:${r.stored}`);
  })));

  console.log(`[similarity] complete. symbols=${symbols.length}, matches=${stored}`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
}).finally(closePool);
