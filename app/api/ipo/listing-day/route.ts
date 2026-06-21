// app/api/ipo/listing-day/route.ts
// Live listing day signals from Kite — VWAP, volume, bid/ask, hold/exit verdict

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

const API_KEY = process.env.KITE_API_KEY || "br9m41pn8nvvywnl"

async function getKiteToken(): Promise<string | null> {
  const sql = neon(process.env.DATABASE_URL!)
  const rows = await sql`SELECT value FROM platform_config WHERE key = 'kite_access_token' LIMIT 1`
  return rows[0]?.value || null
}

async function kiteQuote(token: string, symbol: string): Promise<any> {
  const r = await fetch(`https://api.kite.trade/quote?i=NSE:${symbol}`, {
    headers: { "X-Kite-Version": "3", "Authorization": `token ${API_KEY}:${token}` },
  })
  if (!r.ok) throw new Error(`Kite ${r.status}`)
  const data = await r.json()
  return data.data?.[`NSE:${symbol}`]
}

function computeHoldSignal(s: any): { signal: string; reason: string } {
  if (s.current_price <= s.lc_threshold * 1.01)
    return { signal: "EXIT", reason: "Hit lower circuit — exit immediately, avg -19.2% next 7 days" }
  if (s.price_vs_vwap < -2)
    return { signal: "EXIT", reason: "Price below VWAP — institutional distribution, exit by EOD" }
  if (s.qib >= 100)
    return { signal: "EXIT", reason: "QIB 100x+ — institutions sell on listing day (data: -6.9% avg 7d)" }
  if (s.current_price >= s.uc_threshold * 0.99)
    return { signal: "HOLD", reason: "Hitting UC — momentum intact, avg +25.9% next 7 days" }
  if (s.price_vs_vwap > 1 && s.ftr > 0.8 && s.qib >= 20 && s.qib < 100)
    return { signal: "HOLD", reason: `Above VWAP, ${(s.ftr*100).toFixed(0)}% float traded, QIB ${s.qib?.toFixed(0)}x — hold 7 days` }
  if (s.price_vs_vwap > 0 && s.ftr > 0.6 && s.bid_depth > s.ask_depth * 1.2)
    return { signal: "HOLD", reason: "Above VWAP, strong bid, good absorption — hold with trailing stop" }
  if (s.ftr < 0.3)
    return { signal: "WATCH", reason: "Low volume — insufficient data, check again at 10:30 AM" }
  return { signal: "WATCH", reason: "Mixed signals — wait for direction clarity before 10:30 AM" }
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim()
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  try {
    const sql = neon(process.env.DATABASE_URL!)
    const kiteToken = await getKiteToken()
    if (!kiteToken) return NextResponse.json({ error: "Kite token missing" }, { status: 503 })

    const [ipoRows, quote] = await Promise.all([
      sql`SELECT company_name, issue_price, listing_open, qib_subscription_x,
                 issue_size_cr, play_recommendation, play_confidence, hold_7_days,
                 anchor_lock30_date
          FROM ipo_intelligence
          WHERE nse_symbol = ${symbol} OR symbol = ${symbol} LIMIT 1`,
      kiteQuote(kiteToken, symbol),
    ])

    if (!quote) return NextResponse.json({ error: `No quote for ${symbol}` }, { status: 404 })

    const ipo      = ipoRows[0]
    const ohlc     = quote.ohlc || {}
    const depth    = quote.depth || {}
    const current  = quote.last_price || 0
    const open     = ohlc.open || ipo?.listing_open || current
    const high     = ohlc.high || current
    const low      = ohlc.low  || current
    const volume   = quote.volume_traded || quote.volume || 0
    const issue_px = ipo?.issue_price || 0
    const qib      = ipo?.qib_subscription_x || 0

    const vwap     = (high + low + current) / 3  // simplified intraday VWAP
    const bid_depth = (depth.buy  || []).reduce((s: number, b: any) => s + (b.quantity || 0), 0)
    const ask_depth = (depth.sell || []).reduce((s: number, s2: any) => s + (s2.quantity || 0), 0)

    const day1_float    = (ipo?.issue_size_cr > 0 && issue_px > 0)
      ? (ipo.issue_size_cr * 1e7) / issue_px : volume * 5
    const ftr           = volume / Math.max(day1_float, 1)
    const uc_threshold  = open * 1.20
    const lc_threshold  = open * 0.80
    const price_vs_vwap = vwap > 0 ? (current / vwap - 1) * 100 : 0
    const price_vs_open = open  > 0 ? (current / open  - 1) * 100 : 0

    const signals = {
      symbol, company: ipo?.company_name || symbol, issue_price: issue_px,
      listing_open: open, current_price: current, vwap: Math.round(vwap * 100) / 100,
      volume, day1_float: Math.round(day1_float), bid_depth, ask_depth, high, low,
      timestamp: new Date().toISOString(), qib,
      price_vs_vwap: Math.round(price_vs_vwap * 100) / 100,
      price_vs_open: Math.round(price_vs_open * 100) / 100,
      ftr: Math.round(ftr * 1000) / 1000,
      uc_threshold: Math.round(uc_threshold * 100) / 100,
      lc_threshold: Math.round(lc_threshold * 100) / 100,
    }

    const verdict = computeHoldSignal(signals)
    return NextResponse.json({
      signals: { ...signals, hold_signal: verdict.signal, hold_reason: verdict.reason },
      ipo_meta: { play_recommendation: ipo?.play_recommendation, hold_7_days: ipo?.hold_7_days }
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
