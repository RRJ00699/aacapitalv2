// app/api/search/route.ts — V2 with convergence V3 scoring inline
import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

function hasOrderBook(industry: string): boolean {
  const lower = (industry ?? "").toLowerCase()
  return ["infrastructure","defence","capital goods","construction","power",
    "railways","real estate","it services","electrical equipment",
    "compressors","water supply","engineering","aerospace"].some(s => lower.includes(s))
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim()
  if (!q || q.length < 2) return NextResponse.json({ results: [] })

  const sql = db()
  const search = `%${q.toUpperCase()}%`
  const nameSearch = `%${q}%`

  try {
    const rows = await sql`
      SELECT f.nse_symbol, f.name, f.industry,
        f.current_price, f.market_cap,
        f.business_dna_score, f.business_dna_grade,
        f.earnings_score, f.smart_money_score, f.smart_money_signal,
        f.sector_rotation_score, f.return_3m, f.return_6m,
        obs.ob_score, obs.coverage_tier AS ob_coverage, obs.current_ob_cr,
        es.earnings_momentum_score, es.consecutive_beats,
        w.is_nr7, w.stage, w.breakout_ready, w.rs_vs_nifty_4w,
        CASE WHEN UPPER(f.nse_symbol) = ${q.toUpperCase()} THEN 1
             WHEN UPPER(f.nse_symbol) LIKE ${search} THEN 2
             WHEN UPPER(f.name) LIKE ${nameSearch.toUpperCase()} THEN 3
             ELSE 4 END AS match_rank
      FROM stock_fundamentals f
      LEFT JOIN order_book_signals obs ON obs.nse_symbol = f.nse_symbol
      LEFT JOIN earnings_signals   es  ON es.nse_symbol  = f.nse_symbol
      LEFT JOIN weekly_dna         w   ON w.tradingsymbol = f.nse_symbol
      WHERE UPPER(f.nse_symbol) LIKE ${search}
         OR UPPER(f.name)       LIKE ${nameSearch.toUpperCase()}
         OR UPPER(f.industry)   LIKE ${nameSearch.toUpperCase()}
      ORDER BY match_rank ASC, f.business_dna_score DESC NULLS LAST
      LIMIT 10
    `

    const results = rows.map(r => {
      const e1 = Math.min(100, Math.max(0, Number(r.business_dna_score ?? 50)))
      const e2 = Math.min(100, Math.max(0, Math.round(50 + Number(r.return_3m ?? 0) * 0.8 + Number(r.return_6m ?? 0) * 0.4)))
      const stage = Number(r.stage ?? 2)
      const e3 = Math.min(100, Math.max(0, Math.round((stage===1?35:stage===2?25:10) + (r.is_nr7?20:0) + (r.breakout_ready?15:0) + (Number(r.rs_vs_nifty_4w??0)>5?15:8))))
      const e4 = r.earnings_momentum_score ? Math.min(100, Number(r.earnings_momentum_score)) : Math.min(100, Number(r.earnings_score ?? 50))
      const e5 = Math.min(100, Number(r.smart_money_score ?? 50))
      const e6 = Math.min(100, Number(r.sector_rotation_score ?? 50))
      const eligibleOB = hasOrderBook(r.industry ?? "")
      const e9 = eligibleOB && r.ob_score ? Math.min(100, Number(r.ob_score)) : 0
      const w9 = eligibleOB ? 10 : 0
      const mult = w9 === 0 ? 100/90 : 1
      const convergence = Math.min(100, Math.max(0, Math.round((e1*25+e2*15+e3*12+e4*16+e5*13+e6*9)*mult/100+(e9*w9)/100)))

      return {
        symbol: r.nse_symbol, name: r.name, industry: r.industry,
        price: Number(r.current_price ?? 0), market_cap: Number(r.market_cap ?? 0),
        convergence, business_grade: r.business_dna_grade,
        business_score: Number(r.business_dna_score ?? 0),
        earnings_score: Number(r.earnings_score ?? 0),
        sm_score: Number(r.smart_money_score ?? 0), sm_signal: r.smart_money_signal,
        ob_score: r.ob_score ? Number(r.ob_score) : null,
        ob_coverage: r.ob_coverage ?? null, current_ob_cr: r.current_ob_cr ? Number(r.current_ob_cr) : null,
        earnings_momentum: r.earnings_momentum_score ? Number(r.earnings_momentum_score) : null,
        consecutive_beats: r.consecutive_beats ? Number(r.consecutive_beats) : null,
        is_nr7: r.is_nr7 ?? false, stage: r.stage ?? null, breakout_ready: r.breakout_ready ?? false,
      }
    })

    return NextResponse.json({ ok: true, query: q, count: results.length, results })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
