import { Command } from 'commander';
import pLimit from 'p-limit';
import { pool, closePool, getSymbols, fetchDailyCandles, fetchWeeklyCandles } from '../lib/db';
import { ema, heikinAshi, isInsideBar, isNR7, resampleMonthly, rsi, sma, trueRanges } from '../lib/indicators';

const program = new Command();
program
  .option('--symbol <symbol>', 'single symbol')
  .option('--mode <mode>', 'latest or full', 'latest')
  .option('--concurrency <n>', 'parallel symbols', '4');
program.parse(process.argv);
const opts = program.opts();

type DeliveryRow = { date: string; delivery_percentage: number | null };

async function fetchDelivery(symbol: string, limit = 500): Promise<Map<string, number | null>> {
  try {
    const res = await pool.query<DeliveryRow>(
      `SELECT date::text AS date, delivery_percentage
       FROM delivery_data
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT $2`,
      [symbol, limit]
    );
    return new Map(res.rows.map((r) => [r.date, r.delivery_percentage === null ? null : Number(r.delivery_percentage)]));
  } catch {
    return new Map();
  }
}

async function upsertDaily(symbol: string) {
  const candles = await fetchDailyCandles(symbol, opts.mode === 'full' ? 4000 : 160);
  if (candles.length < 30) return { symbol, daily: 0 };
  const trs = trueRanges(candles);
  const volumes = candles.map((c) => (c.volume === null ? null : Number(c.volume)));
  const volAvg20 = sma(volumes, 20);
  const deliveryMap = await fetchDelivery(symbol, opts.mode === 'full' ? 4000 : 200);
  const deliverySeries = candles.map((c) => deliveryMap.get(c.date) ?? null);
  const deliveryAvg10 = sma(deliverySeries, 10);

  const rows = candles.map((c, i) => {
    const va = volAvg20[i];
    const vr = va && c.volume ? c.volume / va : null;
    const delivery = deliveryMap.get(c.date) ?? null;
    const dAvg = deliveryAvg10[i];
    const dPrev = i > 0 ? deliveryAvg10[i - 1] : null;
    return [
      c.symbol, c.date, trs[i], isNR7(trs, i), isInsideBar(candles, i), va, vr,
      delivery, dAvg, dAvg !== null && dPrev !== null ? dAvg > dPrev : false,
    ];
  });

  const insertRows = opts.mode === 'latest' ? rows.slice(-10) : rows;
  for (const r of insertRows) {
    await pool.query(
      `INSERT INTO technical_indicators_daily
       (symbol, date, true_range, nr7, inside_bar, volume_avg_20, volume_ratio_20,
        delivery_percentage, delivery_avg_10, delivery_rising, updated_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,now())
       ON CONFLICT (symbol, date) DO UPDATE SET
        true_range = EXCLUDED.true_range,
        nr7 = EXCLUDED.nr7,
        inside_bar = EXCLUDED.inside_bar,
        volume_avg_20 = EXCLUDED.volume_avg_20,
        volume_ratio_20 = EXCLUDED.volume_ratio_20,
        delivery_percentage = EXCLUDED.delivery_percentage,
        delivery_avg_10 = EXCLUDED.delivery_avg_10,
        delivery_rising = EXCLUDED.delivery_rising,
        updated_at = now()`,
      r
    );
  }
  return { symbol, daily: insertRows.length };
}

async function upsertWeekly(symbol: string) {
  const candles = await fetchWeeklyCandles(symbol, opts.mode === 'full' ? 700 : 120);
  if (candles.length < 35) return { symbol, weekly: 0 };
  const closes = candles.map((c) => c.close);
  const ema30 = ema(closes, 30);
  const ha = heikinAshi(candles);
  const rows = candles.map((c, i) => {
    const e = ema30[i];
    const prevE = i > 0 ? ema30[i - 1] : null;
    return [
      c.symbol, c.date, e, e !== null && prevE !== null ? e > prevE : false,
      ha[i].haOpen, ha[i].haHigh, ha[i].haLow, ha[i].haClose,
      ha[i].green, ha[i].noLowerShadow,
      e !== null ? c.close > e : false,
    ];
  });
  const insertRows = opts.mode === 'latest' ? rows.slice(-10) : rows;
  for (const r of insertRows) {
    await pool.query(
      `INSERT INTO technical_indicators_weekly
       (symbol, week_start, ema_30, ema_30_rising, ha_open, ha_high, ha_low, ha_close,
        ha_green, ha_no_lower_shadow, close_above_ema_30, updated_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,now())
       ON CONFLICT (symbol, week_start) DO UPDATE SET
        ema_30 = EXCLUDED.ema_30,
        ema_30_rising = EXCLUDED.ema_30_rising,
        ha_open = EXCLUDED.ha_open,
        ha_high = EXCLUDED.ha_high,
        ha_low = EXCLUDED.ha_low,
        ha_close = EXCLUDED.ha_close,
        ha_green = EXCLUDED.ha_green,
        ha_no_lower_shadow = EXCLUDED.ha_no_lower_shadow,
        close_above_ema_30 = EXCLUDED.close_above_ema_30,
        updated_at = now()`,
      r
    );
  }
  return { symbol, weekly: insertRows.length };
}

function trendlineBreakout(monthly: ReturnType<typeof resampleMonthly>, i: number): boolean {
  if (i < 6) return false;
  const highs = monthly.slice(i - 6, i).map((c) => c.high);
  const maxHigh = Math.max(...highs);
  const recentDecline = highs[0] > highs[highs.length - 1];
  return recentDecline && monthly[i].close > maxHigh;
}

async function upsertMonthly(symbol: string) {
  const daily = await fetchDailyCandles(symbol, 4000);
  const monthly = resampleMonthly(daily);
  if (monthly.length < 20) return { symbol, monthly: 0 };
  const r = rsi(monthly.map((c) => c.close), 14);
  const rows = monthly.map((c, i) => [
    c.symbol, c.date, c.open, c.high, c.low, c.close, c.volume,
    r[i], r[i] !== null ? r[i] > 60 : false, trendlineBreakout(monthly, i),
  ]);
  const insertRows = opts.mode === 'latest' ? rows.slice(-3) : rows;
  for (const row of insertRows) {
    await pool.query(
      `INSERT INTO technical_indicators_monthly
       (symbol, month_start, open, high, low, close, volume, rsi_14, rsi_above_60, trendline_breakout, updated_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,now())
       ON CONFLICT (symbol, month_start) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        rsi_14 = EXCLUDED.rsi_14,
        rsi_above_60 = EXCLUDED.rsi_above_60,
        trendline_breakout = EXCLUDED.trendline_breakout,
        updated_at = now()`,
      row
    );
  }
  return { symbol, monthly: insertRows.length };
}

async function processSymbol(symbol: string) {
  const d = await upsertDaily(symbol);
  const w = await upsertWeekly(symbol);
  const m = await upsertMonthly(symbol);
  return { symbol, ...d, ...w, ...m };
}

async function main() {
  const symbols = opts.symbol ? [opts.symbol] : await getSymbols('price_candles');
  const limit = pLimit(Number(opts.concurrency));
  let done = 0;
  const results = await Promise.allSettled(symbols.map((s) => limit(async () => {
    const r = await processSymbol(s);
    done++;
    if (done % 25 === 0 || opts.symbol) console.log(`Processed ${done}/${symbols.length}`, r);
    return r;
  })));
  const failed = results.filter((r) => r.status === 'rejected').length;
  console.log(`Indicator calculation complete. Symbols=${symbols.length}, failed=${failed}`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
}).finally(closePool);
