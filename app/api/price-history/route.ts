// app/api/price-history/route.ts
// Chart data: tries Neon tables first, falls back to Yahoo Finance v8
import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

const months: Record<string, number> = { "1Y": 12, "2Y": 24, "3Y": 36, "5Y": 60, "10Y": 120 }

function mapRows(rows: any[]) {
  return rows.map(r => ({
    date:   r.date ?? r.timestamp ?? r.candle_date,
    open:   Number(r.open   ?? r.close ?? 0),
    high:   Number(r.high   ?? r.close ?? 0),
    low:    Number(r.low    ?? r.close ?? 0),
    close:  Number(r.close  ?? 0),
    volume: Number(r.volume ?? 0),
  })).filter(r => r.date && r.close > 0)
}

async function fetchYahoo(symbol: string, months: number) {
  const range    = months <= 12 ? "1y" : months <= 36 ? "3y" : months <= 60 ? "5y" : "10y"
  const interval = months <= 12 ? "1wk" : "1mo"
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${symbol}.NS?interval=${interval}&range=${range}`
  const r = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
    signal: AbortSignal.timeout(8000),
  })
  if (!r.ok) throw new Error(`Yahoo ${r.status}`)
  const data = await r.json()
  const result = data?.chart?.result?.[0]
  if (!result) throw new Error("No Yahoo data")
  const { timestamp, indicators: { quote: [q] } } = result
  return timestamp.map((ts: number, i: number) => ({
    date:   new Date(ts * 1000).toISOString().slice(0, 10),
    open:   Number((q.open[i]   ?? q.close[i] ?? 0).toFixed(2)),
    high:   Number((q.high[i]   ?? q.close[i] ?? 0).toFixed(2)),
    low:    Number((q.low[i]    ?? q.close[i] ?? 0).toFixed(2)),
    close:  Number((q.close[i]  ?? 0).toFixed(2)),
    volume: Number(q.volume[i]  ?? 0),
  })).filter((r: any) => r.date && r.close > 0)
}

export async function GET(req: NextRequest) {
  const symbol  = req.nextUrl.searchParams.get("symbol")?.toUpperCase().trim()
  const period  = req.nextUrl.searchParams.get("period") ?? "3Y"
  const months_ = req.nextUrl.searchParams.get("months")
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })
  const lookback = months_ ? parseInt(months_) : (months[period] ?? 36)
  const sql = db()

  // 1. Try Neon tables
  try {
    let rows: any[] = []
    let source = "price_monthly"
    rows = await sql`
      SELECT date, open, high, low, close, volume FROM price_monthly
      WHERE symbol = ${symbol}
        AND date >= NOW() - INTERVAL '1 month' * ${lookback}
      ORDER BY date ASC`
    if (!rows.length) {
      source = "price_candles_monthly"
      rows = await sql`
        SELECT date, open, high, low, close, volume FROM price_candles_monthly
        WHERE symbol = ${symbol}
          AND date >= NOW() - INTERVAL '1 month' * ${lookback}
        ORDER BY date ASC`
    }
    if (!rows.length) {
      // Daily price_candles IS populated by the daily sync — aggregate to monthly.
      source = "price_candles_daily_agg"
      rows = await sql`
        SELECT date_trunc('month', date)::date AS date,
               (array_agg(open  ORDER BY date ASC ))[1] AS open,
               MAX(high) AS high,
               MIN(low)  AS low,
               (array_agg(close ORDER BY date DESC))[1] AS close,
               SUM(volume) AS volume
        FROM price_candles
        WHERE symbol = ${symbol}
          AND date >= NOW() - INTERVAL '1 month' * ${lookback}
        GROUP BY 1
        ORDER BY 1 ASC`
    }
    if (rows.length >= 3) {
      const data = mapRows(rows)
      if (data.length >= 3) return NextResponse.json({ ok: true, source, data })
    }
  } catch {}

  // 2. Fallback: Yahoo Finance
  try {
    const data = await fetchYahoo(symbol, lookback)
    if (data.length > 0) return NextResponse.json({ ok: true, source: "yahoo", data })
  } catch {}

  return NextResponse.json({ ok: true, source: "none", data: [] })
}
