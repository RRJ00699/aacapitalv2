import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

//  /api/technical-features
// Surfaces the Technical Feature Store. Joins the NEW ranked descriptors (technical_features:
// relative strength, RVOL, volatility percentile, 52w/ATH proximity, EMA alignment) with the
// EXISTING nightly engine (technical_signals: Wyckoff stage, breakout-watch, convergence) — one
// endpoint for both screening (no ?symbol -> universe) and deep-dive (?symbol=X -> one stock).
// Descriptive context, NOT buy calls.

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}

const shape = (r: any) => ({
  symbol: r.symbol,
  sector: r.sector || null,
  price: num(r.price),
  ret_3m: num(r.ret_3m), ret_6m: num(r.ret_6m),
  rs_score: num(r.rs_score),                       // 0-100 universe momentum rank
  rs_3m_universe: num(r.rs_3m_universe), rs_6m_universe: num(r.rs_6m_universe),
  rs_6m_sector: num(r.rs_6m_sector),
  rvol: num(r.rvol), rvol_rank: num(r.rvol_rank),
  atr_pct: num(r.atr_pct), vol_pctile: num(r.vol_pctile), rsi14: num(r.rsi14),
  ema_aligned: r.ema_aligned ?? null, above_ema200: r.above_ema200 ?? null,
  pct_from_52wh: num(r.pct_from_52wh), pct_from_ath: num(r.pct_from_ath),
  // Bucket-A descriptors (context, not forecasts)
  compression_tightness: num(r.compression_tightness), compression_state: r.compression_state || null,
  support: num(r.support), support_dist: num(r.support_dist),
  resistance: num(r.resistance), resistance_dist: num(r.resistance_dist),
  gap_dir: r.gap_dir || null, gap_size: num(r.gap_size), gap_filled: r.gap_filled ?? null,
  delivery_today: num(r.delivery_today), delivery_ratio: num(r.delivery_ratio), delivery_state: r.delivery_state || null,
  // from the existing nightly engine (may be null if not yet scored that name)
  stage: r.stage_label || r.stage || null,
  breakout_watch_score: num(r.breakout_watch_score),
  breakout_watch_tier: r.breakout_watch_tier || null,
  convergence_score: num(r.convergence_score),
})

export async function GET(req: NextRequest) {
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()

    if (symbol) {
      const rows = await sql`
        SELECT tf.*, ts.stage, ts.stage_label, ts.breakout_watch_score,
               ts.breakout_watch_tier, ts.convergence_score
        FROM technical_features tf
        LEFT JOIN technical_signals ts
          ON ts.symbol = tf.symbol AND ts.timeframe = 'daily'
        WHERE tf.symbol = ${symbol}
        LIMIT 1`
      if (!rows.length) return NextResponse.json({ symbol, available: false },
        { headers: { "Cache-Control": "public, max-age=1800" } })
      return NextResponse.json({ symbol, available: true, technical: shape(rows[0]) },
        { headers: { "Cache-Control": "public, max-age=1800" } })
    }

    // universe (for screening) — distinct-on keeps the latest daily signal row per symbol
    const rows = await sql`
      WITH sig AS (
        SELECT DISTINCT ON (symbol) symbol, stage, stage_label,
               breakout_watch_score, breakout_watch_tier, convergence_score
        FROM technical_signals
        WHERE timeframe = 'daily'
        ORDER BY symbol, signal_date DESC
      )
      SELECT tf.*, s.stage, s.stage_label, s.breakout_watch_score,
             s.breakout_watch_tier, s.convergence_score
      FROM technical_features tf
      LEFT JOIN sig s ON s.symbol = tf.symbol
      ORDER BY tf.rs_score DESC NULLS LAST`
    const stocks = (rows as any[]).map(shape)
    return NextResponse.json({ count: stocks.length, stocks },
      { headers: { "Cache-Control": "public, max-age=1800" } })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
