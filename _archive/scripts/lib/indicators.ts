import type { Candle } from './db';

export function ema(values: number[], period: number): Array<number | null> {
  const out: Array<number | null> = Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let seed = 0;
  for (let i = 0; i < period; i++) seed += values[i];
  let prev = seed / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export function rsi(values: number[], period = 14): Array<number | null> {
  const out: Array<number | null> = Array(values.length).fill(null);
  if (values.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = values[i] - values[i - 1];
    if (diff >= 0) gain += diff;
    else loss -= diff;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < values.length; i++) {
    const diff = values[i] - values[i - 1];
    const g = diff > 0 ? diff : 0;
    const l = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

export function trueRanges(candles: Candle[]): number[] {
  return candles.map((c, i) => {
    if (i === 0) return c.high - c.low;
    const prevClose = candles[i - 1].close;
    return Math.max(c.high - c.low, Math.abs(c.high - prevClose), Math.abs(c.low - prevClose));
  });
}

export function isNR7(trs: number[], index: number): boolean {
  if (index < 6) return false;
  const window = trs.slice(index - 6, index + 1);
  const current = trs[index];
  return Number.isFinite(current) && current === Math.min(...window);
}

export function isInsideBar(candles: Candle[], index: number): boolean {
  if (index < 1) return false;
  return candles[index].high <= candles[index - 1].high && candles[index].low >= candles[index - 1].low;
}

export function sma(values: Array<number | null>, period: number): Array<number | null> {
  const out: Array<number | null> = Array(values.length).fill(null);
  let sum = 0;
  let count = 0;
  const q: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v !== null && Number.isFinite(v)) {
      sum += v;
      count++;
      q.push(v);
    } else {
      q.push(NaN);
    }
    if (q.length > period) {
      const old = q.shift();
      if (old !== undefined && Number.isFinite(old)) {
        sum -= old;
        count--;
      }
    }
    if (q.length === period && count > 0) out[i] = sum / count;
  }
  return out;
}

export type HeikinAshi = {
  haOpen: number;
  haHigh: number;
  haLow: number;
  haClose: number;
  green: boolean;
  noLowerShadow: boolean;
};

export function heikinAshi(candles: Candle[]): HeikinAshi[] {
  const out: HeikinAshi[] = [];
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const haClose = (c.open + c.high + c.low + c.close) / 4;
    const haOpen = i === 0 ? (c.open + c.close) / 2 : (out[i - 1].haOpen + out[i - 1].haClose) / 2;
    const haHigh = Math.max(c.high, haOpen, haClose);
    const haLow = Math.min(c.low, haOpen, haClose);
    const green = haClose > haOpen;
    const noLowerShadow = green && Math.abs(haLow - Math.min(haOpen, haClose)) <= Math.max(c.close * 0.001, 0.01);
    out.push({ haOpen, haHigh, haLow, haClose, green, noLowerShadow });
  }
  return out;
}

export function resampleMonthly(daily: Candle[]): Candle[] {
  const map = new Map<string, Candle>();
  for (const c of daily) {
    const key = c.date.slice(0, 7) + '-01';
    const existing = map.get(key);
    if (!existing) {
      map.set(key, { ...c, date: key });
    } else {
      existing.high = Math.max(existing.high, c.high);
      existing.low = Math.min(existing.low, c.low);
      existing.close = c.close;
      existing.volume = (existing.volume ?? 0) + (c.volume ?? 0);
    }
  }
  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function normalizeShape(values: number[], buckets = 24): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const denom = max - min || 1;
  const norm = values.map((v) => (v - min) / denom);
  const out: number[] = [];
  for (let b = 0; b < buckets; b++) {
    const start = Math.floor((b * norm.length) / buckets);
    const end = Math.max(start + 1, Math.floor(((b + 1) * norm.length) / buckets));
    const slice = norm.slice(start, end);
    out.push(slice.reduce((s, v) => s + v, 0) / slice.length);
  }
  return out;
}

export function dtwDistance(a: number[], b: number[]): number {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(Infinity));
  dp[0][0] = 0;
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      const cost = Math.abs(a[i - 1] - b[j - 1]);
      dp[i][j] = cost + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[n][m] / (n + m);
}

export function pct(a: number, b: number): number {
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === 0) return 0;
  return ((b - a) / a) * 100;
}
