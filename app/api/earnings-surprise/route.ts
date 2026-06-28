import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

//  /api/earnings-surprise
// Serves earnings_surprise (compute_earnings_surprise.py): each landed quarter's actual vs our HOUSE
// estimate, classified BEAT/MISS/INLINE using the model's own backtested error as the noise floor
// (revenue ±7.5%, PAT ±25%) + a consecutive beat/miss streak. Surprise is "vs our estimate" (no street
// consensus). ?symbol=X -> that stock's history; no symbol -> latest quarter per stock (for screening).

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}
const shape = (r: any) => ({
  symbol: r.symbol, quarter: r.quarter_label, period: r.period,
  est_revenue: num(r.est_revenue), act_revenue: num(r.act_revenue),
  revenue_surprise_pct: num(r.revenue_surprise_pct), revenue_verdict: r.revenue_verdict || null,
  est_pat: num(r.est_pat), act_pat: num(r.act_pat),
  pat_surprise_pct: num(r.pat_surprise_pct), pat_verdict: r.pat_verdict || null,
  verdict: r.verdict || null, streak: num(r.streak), confidence: num(r.est_confidence),
})

export async function GET(req: NextRequest) {
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()

    if (symbol) {
      const rows = await sql`
        SELECT * FROM earnings_surprise WHERE symbol = ${symbol} ORDER BY period DESC LIMIT 12`
      return NextResponse.json({ symbol, quarters: (rows as any[]).map(shape) },
        { headers: { "Cache-Control": "public, max-age=1800" } })
    }

    // screening: latest scored quarter per symbol
    const rows = await sql`
      SELECT DISTINCT ON (es.symbol) es.*, cm.sector, cm.company_name AS name
      FROM earnings_surprise es
      LEFT JOIN company_master cm ON cm.nse_symbol = es.symbol
      ORDER BY es.symbol, es.period DESC`
    const stocks = (rows as any[]).map(r => ({ ...shape(r), sector: r.sector || null, name: r.name || r.symbol }))
    return NextResponse.json({ count: stocks.length, stocks },
      { headers: { "Cache-Control": "public, max-age=1800" } })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
