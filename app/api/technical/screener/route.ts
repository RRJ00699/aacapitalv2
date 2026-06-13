// app/api/technical/screener/route.ts
// Technical Screener API — reads price_candles tables
// Returns stocks filtered by pattern, EMA, RSI, sector, volume

import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const timeframe = searchParams.get("timeframe") || "daily"
    const pattern   = searchParams.get("pattern") || ""
    const ema       = searchParams.get("ema") || "all"
    const sector    = searchParams.get("sector") || ""
    const rsiMin    = parseFloat(searchParams.get("rsi_min") || "0")
    const rsiMax    = parseFloat(searchParams.get("rsi_max") || "100")
    const limit     = Math.min(200, parseInt(searchParams.get("limit") || "100"))

    // Select table based on timeframe
    const table = timeframe === "weekly"
      ? "price_candles_weekly"
      : timeframe === "monthly"
      ? "price_candles_monthly"
      : "price_candles"

    // Check table exists
    const tableCheck = await sql`
      SELECT 1 FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = ${table}
      LIMIT 1
    `.catch(() => [])

    if (tableCheck.length === 0) {
      return NextResponse.json({
        success: false,
        error: `Table ${table} not found. Load candle data first.`,
        hint: "Run python download_candles.py, then build load-candles.ts",
      }, { status: 404 })
    }

    // Check if pre-computed signals table exists
    const sigCheck = await sql`
      SELECT 1 FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'technical_signals'
      LIMIT 1
    `.catch(() => [])

    if (sigCheck.length > 0) {
      // Query from pre-computed signals table
      const rows = await sql`
        SELECT
          ts.symbol,
          cm.company_name,
          cm.sector,
          ts.close,
          ts.change_pct,
          ts.volume,
          ts.avg_volume_20,
          ts.ema200,
          ts.rsi,
          ts.nr7,
          ts.vr7,
          ts.volume_expansion,
          ts.ema_crossover,
          ts.buy_zone_score
        FROM technical_signals ts
        LEFT JOIN company_master cm ON cm.symbol = ts.symbol
        WHERE ts.timeframe = ${timeframe}
          AND ts.signal_date = (
            SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = ${timeframe}
          )
          AND (ts.rsi IS NULL OR ts.rsi BETWEEN ${rsiMin} AND ${rsiMax})
          AND (${ema} <> 'above' OR ts.close > ts.ema200)
          AND (${ema} <> 'below' OR ts.close < ts.ema200)
          AND (${ema} <> 'near'  OR ABS(ts.close - ts.ema200) / NULLIF(ts.ema200, 0) < 0.03)
          AND (${pattern} <> 'nr7'      OR ts.nr7 = true)
          AND (${pattern} <> 'vr7'      OR ts.vr7 = true)
          AND (${pattern} <> 'vol_exp'  OR ts.volume_expansion = true)
          AND (${pattern} <> 'ema_cross' OR ts.ema_crossover = true)
          AND (${pattern} <> 'nr7_vr7'  OR (ts.nr7 = true AND ts.vr7 = true))
          AND (${sector} = '' OR cm.sector = ${sector})
        ORDER BY ts.buy_zone_score DESC NULLS LAST
        LIMIT ${limit}
      `
      return NextResponse.json({ success: true, data: rows, source: "signals_table", timeframe })
    }

    // Fallback: derive basic signals from raw candle data
    // Works immediately with candle CSVs loaded into price_candles
    const rows = await sql`
      WITH ranked AS (
        SELECT
          symbol, date, open, high, low, close, volume,
          ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
        FROM price_candles
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
      ),
      latest AS (
        SELECT symbol, date, open, high, low, close, volume
        FROM ranked WHERE rn = 1
      ),
      prev_7 AS (
        SELECT
          symbol,
          MAX(high - low) AS max_hl_range,
          MAX(volume)     AS max_vol,
          AVG(volume)     AS avg_vol
        FROM ranked
        WHERE rn BETWEEN 2 AND 7
        GROUP BY symbol
      )
      SELECT
        l.symbol,
        cm.company_name,
        cm.sector,
        ROUND(l.close::numeric, 2)               AS close,
        NULL::numeric                             AS change_pct,
        l.volume,
        p.avg_vol                                 AS avg_volume,
        NULL::numeric                             AS ema200,
        NULL::numeric                             AS rsi,
        CASE WHEN (l.high - l.low) < p.max_hl_range THEN true ELSE false END AS nr7,
        CASE WHEN l.volume > p.max_vol             THEN true ELSE false END AS vr7,
        CASE WHEN l.volume > p.avg_vol * 1.5       THEN true ELSE false END AS volume_expansion,
        false                                     AS ema_crossover,
        NULL::numeric                             AS buy_zone_score
      FROM latest l
      LEFT JOIN prev_7 p ON p.symbol = l.symbol
      LEFT JOIN company_master cm ON cm.symbol = l.symbol
      WHERE (${sector} = '' OR cm.sector = ${sector})
        AND (${pattern} <> 'nr7'     OR (l.high - l.low) < p.max_hl_range)
        AND (${pattern} <> 'vr7'     OR l.volume > p.max_vol)
        AND (${pattern} <> 'vol_exp' OR l.volume > p.avg_vol * 1.5)
      ORDER BY l.volume DESC NULLS LAST
      LIMIT ${limit}
    `.catch(() => [])

    return NextResponse.json({
      success: true,
      data: rows,
      source: "raw_candles",
      timeframe,
      note: "Basic signals only — build run-technical-signals.ts for full computation",
    })

  } catch (error: unknown) {
    return NextResponse.json(
      { success: false, error: String(error) },
      { status: 500 }
    )
  }
}

