// app/api/ipo/journey/route.ts
// The HOLD engine: computes lock8/trail12 exit levels from stored candles,
// then compares against a LIVE price (Kite via /api/broker/quote) so the exit
// fires INTRADAY — not at EOD close. Rakesh's rule: if the floor breaks at 11am,
// exit at the floor, don't ride it down to close.
import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

const ARM = 0.08     // arm the floor once high hits +8%
const FLOOR = 0.03   // protect +3% once armed
const TRAIL = 0.12   // 12% trailing stop from peak

export async function GET(req: NextRequest) {
  const sym = req.nextUrl.searchParams.get("sym")?.toUpperCase()
  if (!sym) return NextResponse.json({ ok: false, error: "sym required" }, { status: 400 })
  const sql = db()

  try {
    // Phase-1 fix #3: price_candles holds the FULL NSE universe (kite-sync-candles),
    // so the earliest candle for a symbol is NOT necessarily its listing day.
    // Floor the window at ipo_intelligence.listing_date so entry/floor/trail math
    // starts at the true listing open. MIN() on purpose: if a junk duplicate row
    // carries a wrong LATER date, MIN degrades gracefully to more candles instead
    // of silently cutting real ones. No IPO row -> no floor (previous behavior).
    const rows = (await sql`
      WITH ld AS (
        SELECT MIN(listing_date) AS listing_date
        FROM ipo_intelligence
        WHERE UPPER(COALESCE(nse_symbol, symbol)) = ${sym}
          AND listing_date IS NOT NULL
      )
      SELECT c.date, c.open, c.high, c.low, c.close, c.volume
      FROM price_candles c, ld
      WHERE UPPER(c.symbol) = ${sym}
        AND (ld.listing_date IS NULL OR c.date >= ld.listing_date)
      ORDER BY c.date ASC LIMIT 40`) as Array<Record<string, unknown>>
    if (!rows.length) {
      return NextResponse.json({ ok: true, sym, hasData: false,
        note: "No candles yet — the journey begins once it lists and trades." })
    }

    const entry = Number(rows[0].open) || 0
    if (entry <= 0) return NextResponse.json({ ok: true, sym, hasData: false, note: "No valid open price." })

    let peak = entry, armed = false, lowSince = entry
    const series = rows.map((r) => {
      const hi = Number(r.high), lo = Number(r.low), cl = Number(r.close)
      peak = Math.max(peak, hi)
      lowSince = Math.min(lowSince, lo)
      if (hi >= entry * (1 + ARM)) armed = true
      return { date: r.date, close: cl, high: hi, low: lo }
    })
    const lastClose = Number(rows[rows.length - 1].close) || entry
    const floorLevel = entry * (1 + FLOOR)
    const trailLevel = peak * (1 - TRAIL)
    const daysHeld = rows.length
    const lockinDaysLeft = Math.max(0, 30 - daysHeld)

    let live = lastClose, liveSource = "close"
    try {
      const q = await fetch(`${req.nextUrl.origin}/api/broker/quote?sym=${sym}&exchange=NSE`,
        { signal: AbortSignal.timeout(5000) })
      if (q.ok) {
        const j = await q.json()
        const lp = Number(j.last_price ?? j.lastPrice ?? j.ltp)
        if (lp > 0) { live = lp; liveSource = j.source || "live" }
      }
    } catch { /* fallback to lastClose */ }

    const gainNow = ((live / entry) - 1) * 100
    const offPeak = ((live / peak) - 1) * 100
    let decision = "HOLD", reason = "", tone = "good"
    if (armed && live <= floorLevel) {
      decision = "EXIT"; tone = "bad"
      reason = `Floor broken. Price is at or below your +3% floor. You were up 8%+ — lock the gain now rather than watch it bleed to close.`
    } else if (live <= trailLevel) {
      decision = "EXIT"; tone = "bad"
      reason = `Trailing stop hit. Price is 12%+ off the peak. The run is over — take what's left.`
    } else if (armed) {
      reason = `Holding. Up ${gainNow.toFixed(1)}%, floor armed. Your urge to sell early is the mistake — the rule exits you if it breaks, not before.`
    } else {
      reason = `Holding. Not yet +8% to arm the floor. Trailing stop protects the downside.`
    }

    return NextResponse.json({
      ok: true, sym, hasData: true,
      entry: Math.round(entry * 10) / 10,
      peak: Math.round(peak * 10) / 10,
      low: Math.round(lowSince * 10) / 10,
      live: Math.round(live * 10) / 10,
      liveSource, armed,
      floorLevel: Math.round(floorLevel * 10) / 10,
      trailLevel: Math.round(trailLevel * 10) / 10,
      gainNow: Math.round(gainNow * 10) / 10,
      offPeak: Math.round(offPeak * 10) / 10,
      daysHeld, lockinDaysLeft,
      decision, reason, tone, series,
    })
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
