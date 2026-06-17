// app/api/price-history/route.ts
// Robust chart data endpoint for Stock Research Workspace.
// Falls back across the common AACapital candle tables so search-open charts do not render blank.

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

const months: Record<string, number> = { "1Y": 12, "2Y": 24, "3Y": 36, "5Y": 60, "10Y": 120 }

function mapRows(rows: any[]) {
  return rows.map(r => ({
    date: r.date ?? r.timestamp ?? r.candle_date,
    open: Number(r.open ?? r.close ?? 0),
    high: Number(r.high ?? r.close ?? 0),
    low: Number(r.low ?? r.close ?? 0),
    close: Number(r.close ?? 0),
    volume: Number(r.volume ?? 0),
  })).filter(r => r.date && r.close > 0)
}

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol")?.toUpperCase().trim()
  const period = req.nextUrl.searchParams.get("period") ?? "3Y"
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })

  const lookback = months[period] ?? 36
  const sql = db()

  try {
    let source = "price_monthly"
    let rows: any[] = await sql`
      SELECT date, close, volume
      FROM price_monthly
      WHERE tradingsymbol = ${symbol}
        AND date >= CURRENT_DATE - (${lookback} || ' months')::INTERVAL
      ORDER BY date ASC
    `.catch(() => [])

    if (!rows.length) {
      source = "price_candles_monthly"
      rows = await sql`
        SELECT date, open, high, low, close, volume
        FROM price_candles_monthly
        WHERE symbol = ${symbol}
          AND date >= CURRENT_DATE - (${lookback} || ' months')::INTERVAL
        ORDER BY date ASC
      `.catch(() => [])
    }

    if (!rows.length) {
      source = "price_candles_daily"
      rows = await sql`
        SELECT date, open, high, low, close, volume
        FROM price_candles
        WHERE symbol = ${symbol}
          AND date >= CURRENT_DATE - (${lookback} || ' months')::INTERVAL
        ORDER BY date ASC
      `.catch(() => [])
    }

    const data = mapRows(rows)
    if (!data.length) {
      return NextResponse.json({ ok: false, error: "No price data found", symbol, period }, { status: 404 })
    }

    return NextResponse.json({ ok: true, symbol, period, source, count: data.length, data })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
