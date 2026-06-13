// app/api/convergence-v3/route.ts
// Convergence V3 — 9 engines including Order Book + Earnings Signals
// GET /api/convergence-v3?symbol=WABAG

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

const ORDER_BOOK_INDUSTRIES = [
  "infrastructure","defence","capital goods","construction","power",
  "railways","real estate","it services","electrical equipment",
  "compressors","water supply","engineering","aerospace"
]

function hasOrderBook(industry: string): boolean {
  const lower = (industry ?? "").toLowerCase()
  return ORDER_BOOK_INDUSTRIES.some(s => lower.includes(s))
}

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol")?.toUpperCase()
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  const sql = db()

  const [fundRows, weeklyRows, obRows, esRows, mgmtRows] = await Promise.all([
    sql`SELECT * FROM stock_fundamentals WHERE nse_symbol = ${symbol} LIMIT 1`,
    sql`SELECT * FROM weekly_dna WHERE tradingsymbol = ${symbol} LIMIT 1`,
    sql`SELECT * FROM order_book_signals WHERE nse_symbol = ${symbol} LIMIT 1`,
    sql`SELECT * FROM earnings_signals WHERE nse_symbol = ${symbol} LIMIT 1`,
    sql`SELECT management_tone, guidance_direction FROM management_commentary
        WHERE nse_symbol = ${symbol} ORDER BY created_at DESC LIMIT 1`,
  ]).catch(() => [[], [], [], [], []] as any)

  const f    = fundRows[0]
  const w    = weeklyRows[0]
  const ob   = obRows[0]
  const es   = esRows[0]
  const mgmt = mgmtRows[0]

  if (!f) return NextResponse.json({ error: "Stock not found" }, { status: 404 })

  // Engine scores
  const e1 = Math.min(100, Math.max(0, Number(f.business_dna_score ?? 50)))
  const e2 = Math.min(100, Math.max(0, Math.round(50 + Number(f.return_3m ?? 0) * 0.8 + Number(f.return_6m ?? 0) * 0.4)))
  const e3 = w ? Math.min(100, Math.max(0, Math.round(
    (Number(w.stage ?? 2) === 1 ? 35 : Number(w.stage ?? 2) === 2 ? 25 : 10) +
    (w.is_nr7 ? 20 : 0) + (w.breakout_ready ? 15 : 0) +
    (Number(w.rs_vs_nifty_4w ?? 0) > 5 ? 15 : Number(w.rs_vs_nifty_4w ?? 0) > 0 ? 8 : -5)
  ))) : 50
  const e4 = es ? Math.min(100, Math.max(0, Number(es.earnings_momentum_score ?? 50)))
              : Math.min(100, Math.max(0, Number(f.earnings_score ?? 50)))
  const e5 = Math.min(100, Math.max(0, Number(f.smart_money_score ?? 50)))
  const e6 = Math.min(100, Math.max(0, Number(f.sector_rotation_score ?? 50)))
  const eligibleOB = hasOrderBook(f.industry ?? "")
  const e9 = eligibleOB && ob ? Math.min(100, Math.max(0, Number(ob.ob_score ?? 0))) : 0
  const w9 = eligibleOB ? 10 : 0
  const mult = w9 === 0 ? 100/90 : 1

  // Weighted score
  let score = Math.round(
    (e1*25 + e2*15 + e3*12 + e4*16 + e5*13 + e6*9) * mult / 100 +
    (e9 * w9) / 100
  )

  // Boosts
  let boost = 0
  if (mgmt?.guidance_direction === "RAISED")   boost += 10
  if (mgmt?.guidance_direction === "LOWERED")  boost -= 15
  if (mgmt?.guidance_direction === "WITHDRAWN") boost -= 10
  if (mgmt?.management_tone === "BULLISH")     boost += 5
  if (mgmt?.management_tone === "DEFENSIVE")   boost -= 5
  if (es) {
    if (Number(es.consecutive_beats ?? 0) >= 4) boost += 8
    else if (Number(es.consecutive_beats ?? 0) >= 2) boost += 4
    if (es.eps_acceleration) boost += 5
    if (Number(es.consecutive_misses ?? 0) >= 2) boost -= 10
  }

  score = Math.min(100, Math.max(0, score + boost))

  return NextResponse.json({
    ok: true, symbol, name: f.name, industry: f.industry,
    convergence: score,
    conviction: score >= 80 ? "Exceptional" : score >= 65 ? "High" : score >= 50 ? "Medium" : "Low",
    expected_6m:  score >= 75 ? "25-40%" : score >= 60 ? "15-25%" : "5-15%",
    expected_12m: score >= 75 ? "40-80%" : score >= 60 ? "25-45%" : "10-25%",
    engines: {
      business_dna:      { score: Math.round(e1), weight: Math.round(25*mult) },
      technical_monthly: { score: Math.round(e2), weight: Math.round(15*mult) },
      technical_weekly:  { score: Math.round(e3), weight: Math.round(12*mult) },
      earnings:          { score: Math.round(e4), weight: Math.round(16*mult), source: es ? "earnings_signals" : "fundamentals" },
      smart_money:       { score: Math.round(e5), weight: Math.round(13*mult) },
      sector_rotation:   { score: Math.round(e6), weight: Math.round(9*mult) },
      order_book:        { score: Math.round(e9), weight: w9, eligible: eligibleOB, coverage_tier: ob?.coverage_tier ?? null },
      mgmt_boost:        boost,
    },
    signals: {
      is_nr7: w?.is_nr7 ?? false,
      stage: w?.stage ?? null,
      breakout_ready: w?.breakout_ready ?? false,
      consecutive_beats: Number(es?.consecutive_beats ?? 0),
      ob_coverage_tier: ob?.coverage_tier ?? null,
      current_ob_cr: ob ? Number(ob.current_ob_cr) : null,
    }
  })
}
