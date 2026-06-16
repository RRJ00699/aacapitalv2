import { pool, closePool } from '../lib/db';

type SignalRow = {
  symbol: string;
  signal_date: string;
  monthly_rsi_14: number | null;
  monthly_ok: boolean;
  weekly_close: number | null;
  weekly_ema_30: number | null;
  weekly_ok: boolean;
  weekly_ha_green_no_lower_shadow: boolean;
  daily_nr7_recent: boolean;
  daily_inside_bar_recent: boolean;
  delivery_percentage: number | null;
  delivery_rising: boolean;
  volume_ratio_20: number | null;
};

function score(row: SignalRow): { probability: number; strength: string; action: string; reasons: string[] } {
  let s = 0;
  const reasons: string[] = [];
  if (row.monthly_ok) { s += 30; reasons.push('Monthly momentum confirmed: RSI > 60 or trendline breakout'); }
  if (row.weekly_ok) { s += 35; reasons.push('Weekly trend confirmed: close above rising 30-EMA'); }
  if (row.weekly_ha_green_no_lower_shadow) { s += 15; reasons.push('Weekly Heikin Ashi green with no lower shadow'); }
  if (row.daily_nr7_recent) { s += 10; reasons.push('Daily NR7 trigger in last 2 sessions'); }
  if (row.daily_inside_bar_recent) { s += 7; reasons.push('Daily inside bar trigger in last 2 sessions'); }
  if (row.delivery_rising) { s += 8; reasons.push('Delivery trend rising'); }
  if ((row.volume_ratio_20 ?? 0) >= 1.3) { s += 5; reasons.push('Volume above 20-day average'); }
  const probability = Math.min(100, s);
  const strength = probability >= 85 ? 'VERY_HIGH' : probability >= 72 ? 'HIGH' : probability >= 60 ? 'MEDIUM' : 'LOW';
  const action = probability >= 85 ? 'ACCUMULATE' : probability >= 72 ? 'WATCH_FOR_BREAKOUT' : probability >= 60 ? 'WATCH' : 'IGNORE';
  return { probability, strength, action, reasons };
}

async function getLatestSignalRows(): Promise<SignalRow[]> {
  const res = await pool.query<SignalRow>(
    `WITH latest_daily AS (
       SELECT DISTINCT ON (symbol) symbol, date, nr7, inside_bar, delivery_percentage, delivery_rising, volume_ratio_20
       FROM technical_indicators_daily
       ORDER BY symbol, date DESC
     ), recent_daily AS (
       SELECT symbol,
              bool_or(nr7) AS daily_nr7_recent,
              bool_or(inside_bar) AS daily_inside_bar_recent,
              max(date)::text AS signal_date
       FROM (
         SELECT symbol, date, nr7, inside_bar,
                row_number() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
         FROM technical_indicators_daily
       ) x
       WHERE rn <= 2
       GROUP BY symbol
     ), latest_weekly AS (
       SELECT DISTINCT ON (symbol) symbol, week_start, ema_30, ema_30_rising, ha_green,
              ha_no_lower_shadow, close_above_ema_30
       FROM technical_indicators_weekly
       ORDER BY symbol, week_start DESC
     ), latest_weekly_price AS (
       SELECT DISTINCT ON (symbol) symbol, close
       FROM price_candles_weekly
       ORDER BY symbol, week_start DESC
     ), latest_monthly AS (
       SELECT DISTINCT ON (symbol) symbol, rsi_14, rsi_above_60, trendline_breakout
       FROM technical_indicators_monthly
       ORDER BY symbol, month_start DESC
     )
     SELECT
       d.symbol,
       rd.signal_date,
       m.rsi_14 AS monthly_rsi_14,
       COALESCE(m.rsi_above_60, false) OR COALESCE(m.trendline_breakout, false) AS monthly_ok,
       wp.close AS weekly_close,
       w.ema_30 AS weekly_ema_30,
       COALESCE(w.close_above_ema_30, false) AND COALESCE(w.ema_30_rising, false) AS weekly_ok,
       COALESCE(w.ha_green, false) AND COALESCE(w.ha_no_lower_shadow, false) AS weekly_ha_green_no_lower_shadow,
       COALESCE(rd.daily_nr7_recent, false) AS daily_nr7_recent,
       COALESCE(rd.daily_inside_bar_recent, false) AS daily_inside_bar_recent,
       d.delivery_percentage,
       COALESCE(d.delivery_rising, false) AS delivery_rising,
       d.volume_ratio_20
     FROM latest_daily d
     JOIN recent_daily rd ON rd.symbol = d.symbol
     LEFT JOIN latest_weekly w ON w.symbol = d.symbol
     LEFT JOIN latest_weekly_price wp ON wp.symbol = d.symbol
     LEFT JOIN latest_monthly m ON m.symbol = d.symbol
     JOIN company_master cm ON cm.nse_symbol = d.symbol
     WHERE cm.market_cap_cr >= 500
       AND (COALESCE(m.rsi_above_60, false) OR COALESCE(m.trendline_breakout, false))
       AND COALESCE(w.close_above_ema_30, false)
       AND COALESCE(w.ema_30_rising, false)
       AND COALESCE(w.ha_green, false)
       AND COALESCE(w.ha_no_lower_shadow, false)
       AND (COALESCE(rd.daily_nr7_recent, false) OR COALESCE(rd.daily_inside_bar_recent, false))`
  );
  return res.rows;
}

async function upsertSignals(rows: SignalRow[]) {
  for (const row of rows) {
    const s = score(row);
    const triggerOk = row.monthly_ok && row.weekly_ok && row.weekly_ha_green_no_lower_shadow &&
      (row.daily_nr7_recent || row.daily_inside_bar_recent) &&
      (row.delivery_rising || (row.volume_ratio_20 ?? 0) >= 1.3);
    await pool.query(
      `INSERT INTO technical_signals
       (symbol, signal_date, monthly_rsi_14, monthly_ok, weekly_close, weekly_ema_30,
        weekly_ok, weekly_ha_green_no_lower_shadow, daily_nr7_recent, daily_inside_bar_recent,
        delivery_percentage, delivery_rising, volume_ratio_20, trigger_ok,
        probability_score, signal_strength, action_label, reasons, updated_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,now())
       ON CONFLICT (symbol, signal_date) DO UPDATE SET
        monthly_rsi_14 = EXCLUDED.monthly_rsi_14,
        monthly_ok = EXCLUDED.monthly_ok,
        weekly_close = EXCLUDED.weekly_close,
        weekly_ema_30 = EXCLUDED.weekly_ema_30,
        weekly_ok = EXCLUDED.weekly_ok,
        weekly_ha_green_no_lower_shadow = EXCLUDED.weekly_ha_green_no_lower_shadow,
        daily_nr7_recent = EXCLUDED.daily_nr7_recent,
        daily_inside_bar_recent = EXCLUDED.daily_inside_bar_recent,
        delivery_percentage = EXCLUDED.delivery_percentage,
        delivery_rising = EXCLUDED.delivery_rising,
        volume_ratio_20 = EXCLUDED.volume_ratio_20,
        trigger_ok = EXCLUDED.trigger_ok,
        probability_score = EXCLUDED.probability_score,
        signal_strength = EXCLUDED.signal_strength,
        action_label = EXCLUDED.action_label,
        reasons = EXCLUDED.reasons,
        updated_at = now()`,
      [
        row.symbol, row.signal_date, row.monthly_rsi_14, row.monthly_ok,
        row.weekly_close, row.weekly_ema_30, row.weekly_ok,
        row.weekly_ha_green_no_lower_shadow, row.daily_nr7_recent,
        row.daily_inside_bar_recent, row.delivery_percentage, row.delivery_rising,
        row.volume_ratio_20, triggerOk, s.probability, s.strength, s.action,
        JSON.stringify(s.reasons),
      ]
    );
  }
}

async function main() {
  const rows = await getLatestSignalRows();
  await upsertSignals(rows);
  console.log(`Multi-timeframe screener complete. Signals updated=${rows.length}`);
  const top = await pool.query(
    `SELECT symbol, signal_date, probability_score, signal_strength, action_label, reasons
     FROM technical_signals
     ORDER BY signal_date DESC, probability_score DESC
     LIMIT 20`
  );
  console.table(top.rows);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
}).finally(closePool);
