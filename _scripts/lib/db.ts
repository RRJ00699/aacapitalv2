import 'dotenv/config';
import { Pool } from 'pg';

const connectionString = process.env.DATABASE_URL;

if (!connectionString) {
  throw new Error('DATABASE_URL is required');
}

export const pool = new Pool({
  connectionString,
  max: Number(process.env.PG_POOL_MAX ?? 5),
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 20_000,
  statement_timeout: 120_000,
});

export async function closePool() {
  await pool.end();
}

export async function getSymbols(table = 'price_candles'): Promise<string[]> {
  const result = await pool.query<{ symbol: string }>(
    `SELECT DISTINCT symbol FROM ${table} WHERE symbol IS NOT NULL ORDER BY symbol`
  );
  return result.rows.map((r) => r.symbol);
}

export type Candle = {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

function toNumber(value: unknown): number {
  if (value === null || value === undefined) return NaN;
  return Number(value);
}

export async function fetchDailyCandles(symbol: string, lookbackDays = 4000): Promise<Candle[]> {
  const result = await pool.query(
    `SELECT symbol, date::text AS date, open, high, low, close, volume
     FROM price_candles
     WHERE symbol = $1
       AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
       AND close > 0
     ORDER BY date DESC
     LIMIT $2`,
    [symbol, lookbackDays]
  );
  return result.rows.reverse().map((r) => ({
    symbol: r.symbol,
    date: r.date,
    open: toNumber(r.open),
    high: toNumber(r.high),
    low: toNumber(r.low),
    close: toNumber(r.close),
    volume: r.volume === null ? null : Number(r.volume),
  }));
}

export async function fetchWeeklyCandles(symbol: string, lookbackWeeks = 700): Promise<Candle[]> {
  const result = await pool.query(
    `SELECT symbol, week_start::text AS date, open, high, low, close, volume
     FROM price_candles_weekly
     WHERE symbol = $1
       AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
       AND close > 0
     ORDER BY week_start DESC
     LIMIT $2`,
    [symbol, lookbackWeeks]
  );
  return result.rows.reverse().map((r) => ({
    symbol: r.symbol,
    date: r.date,
    open: toNumber(r.open),
    high: toNumber(r.high),
    low: toNumber(r.low),
    close: toNumber(r.close),
    volume: r.volume === null ? null : Number(r.volume),
  }));
}
