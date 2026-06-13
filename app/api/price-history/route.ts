// app/api/price-history/route.ts
// GET /api/price-history?symbol=WABAG&period=1Y
// Returns OHLCV from price_monthly table for charts

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol")?.toUpperCase()
  const period = req.nextUrl.searchParams.get("period") ?? "3Y"
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  const sql = db()

  // Map period to months
  const months: Record<string, number> = {
    "1Y": 12, "2Y": 24, "3Y": 36, "5Y": 60, "10Y": 120
  }
  const lookback = months[period] ?? 36

  try {
    const rows = await sql`
      SELECT date, close, volume
      FROM price_monthly
      WHERE tradingsymbol = ${symbol}
        AND date >= CURRENT_DATE - (${lookback} || ' months')::INTERVAL
      ORDER BY date ASC
    `

    if (!rows.length) {
      return NextResponse.json({ ok: false, error: "No price data found", symbol }, { status: 404 })
    }

    return NextResponse.json({
      ok: true, symbol, period, count: rows.length,
      data: rows.map(r => ({
        date:   r.date,
        open:   Number(r.close ?? 0),
        high:   Number(r.close ?? 0),
        low:    Number(r.close ?? 0),
        close:  Number(r.close ?? 0),
        volume: Number(r.volume ?? 0),
      }))
    })

  } catch (err: any) {
    console.error("price-history:", err.message)
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
