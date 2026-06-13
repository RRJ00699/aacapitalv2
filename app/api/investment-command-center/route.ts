// app/api/investment-command-center/route.ts
// Serves full stock detail for StockResearchWorkspace
// GET /api/investment-command-center?symbol=WABAG

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol")?.toUpperCase()
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  const sql = db()

  try {
    const safe = (p: Promise<any>) => p.catch(() => [])

    const [fRows, wRows, smRows, obRows, esRows, mgmtRows] = await Promise.all([
      sql`SELECT * FROM stock_fundamentals WHERE nse_symbol = ${symbol} LIMIT 1`,
      safe(sql`SELECT * FROM weekly_dna WHERE tradingsymbol = ${symbol} LIMIT 1`),
      safe(sql`SELECT net_flow_cr, tier1_count, top_buyer, deal_count FROM smart_money_summary WHERE nse_symbol = ${symbol} LIMIT 1`),
      safe(sql`SELECT * FROM order_book_signals WHERE nse_symbol = ${symbol} LIMIT 1`),
      safe(sql`SELECT * FROM earnings_signals WHERE nse_symbol = ${symbol} LIMIT 1`),
      safe(sql`SELECT management_tone, guidance_direction FROM management_commentary WHERE nse_symbol = ${symbol} ORDER BY created_at DESC LIMIT 1`),
    ])

    const f  = fRows[0]
    const w  = wRows[0]
    const sm = smRows[0]
    const ob = obRows[0]
    const es = esRows[0]
    const mg = mgmtRows[0]

    if (!f) return NextResponse.json({ error: "Symbol not found" }, { status: 404 })

    // Compute convergence V3
    const e1 = Math.min(100, Math.max(0, Number(f.business_dna_score ?? 50)))
    const e2 = Math.min(100, Math.max(0, Math.round(50 + Number(f.return_3m ?? 0) * 0.8 + Number(f.return_6m ?? 0) * 0.4)))
    const stage = Number(w?.stage ?? 2)
    const e3 = w ? Math.min(100, Math.max(0, Math.round(
      (stage === 1 ? 35 : stage === 2 ? 25 : 10) +
      (w.is_nr7 ? 20 : 0) + (w.breakout_ready ? 15 : 0) +
      (Number(w.rs_vs_nifty_4w ?? 0) > 5 ? 15 : 8)
    ))) : 50
    const e4 = es ? Math.min(100, Number(es.earnings_momentum_score ?? 50))
              : Math.min(100, Number(f.earnings_score ?? 50))
    const e5 = Math.min(100, Number(f.smart_money_score ?? 50))
    const e6 = Math.min(100, Number(f.sector_rotation_score ?? 50))

    const OB_INDUSTRIES = ["infrastructure","defence","capital goods","construction","power","railways","real estate","it services","electrical","compressors","water supply","engineering","aerospace"]
    const eligibleOB = OB_INDUSTRIES.some(s => (f.industry ?? "").toLowerCase().includes(s))
    const e9 = eligibleOB && ob ? Math.min(100, Number(ob.ob_score ?? 0)) : 0
    const w9 = eligibleOB ? 10 : 0
    const mult = w9 === 0 ? 100/90 : 1

    let convergence = Math.min(100, Math.max(0, Math.round(
      (e1*25 + e2*15 + e3*12 + e4*16 + e5*13 + e6*9) * mult / 100 + (e9 * w9) / 100
    )))

    // Boosts
    if (mg?.guidance_direction === "RAISED")    convergence = Math.min(100, convergence + 10)
    if (mg?.guidance_direction === "LOWERED")   convergence = Math.max(0,   convergence - 15)
    if (mg?.management_tone === "BULLISH")      convergence = Math.min(100, convergence + 5)
    if (mg?.management_tone === "DEFENSIVE")    convergence = Math.max(0,   convergence - 5)
    if (Number(es?.consecutive_beats ?? 0) >= 4) convergence = Math.min(100, convergence + 8)
    else if (Number(es?.consecutive_beats ?? 0) >= 2) convergence = Math.min(100, convergence + 4)

    // Conviction
    const conviction = convergence >= 80 ? "Exceptional"
                     : convergence >= 65 ? "High"
                     : convergence >= 50 ? "Medium" : "Low"

    // Signals
    const bizSignals: string[] = []
    if (Number(f.roce ?? 0) > 25) bizSignals.push(`ROCE ${Number(f.roce).toFixed(0)}% — excellent capital efficiency`)
    if (Number(f.eps_growth_3y ?? f.eps_cagr_3y ?? 0) > 20) bizSignals.push(`EPS CAGR ${Number(f.eps_growth_3y ?? f.eps_cagr_3y).toFixed(0)}% over 3Y`)
    if (Number(f.sales_growth ?? 0) > 20) bizSignals.push(`Revenue growing ${Number(f.sales_growth).toFixed(0)}% YoY`)
    if (f.business_dna_grade === "A+") bizSignals.push("A+ grade business — top 5% of all listed stocks")
    if (Number(f.debt_equity ?? 0) < 0.3) bizSignals.push("Virtually debt-free balance sheet")

    const warnings: string[] = []
    if (Number(f.debt_equity ?? 0) > 2) warnings.push(`High D/E ratio: ${Number(f.debt_equity).toFixed(1)}x`)
    if (Number(f.roce ?? 0) < 10) warnings.push(`Low ROCE: ${Number(f.roce).toFixed(0)}%`)
    if (Number(es?.consecutive_misses ?? 0) >= 2) warnings.push(`${es.consecutive_misses} consecutive earnings misses`)
    if (mg?.guidance_direction === "LOWERED") warnings.push("Management lowered guidance last quarter")

    const earningsSignals: string[] = []
    if (es) {
      if (Number(es.consecutive_beats) >= 2) earningsSignals.push(`${es.consecutive_beats} consecutive earnings beats`)
      if (es.eps_acceleration) earningsSignals.push("EPS growth accelerating YoY")
      if (es.margin_trend === "EXPANDING") earningsSignals.push("Margins expanding")
      if (es.signal_summary) earningsSignals.push(es.signal_summary)
    }

    return NextResponse.json({
      ok: true,
      symbol,
      name: f.name,
      current_price: Number(f.current_price ?? 0),
      market_cap: Number(f.market_cap ?? 0),
      industry: f.industry,
      scores: {
        technical_dna:     Math.round(e3),
        business_dna:      Math.round(e1),
        business_grade:    f.business_dna_grade ?? "B",
        earnings:          Math.round(e4),
        earnings_category: es?.margin_trend ?? "Stable",
        smart_money:       Math.round(e5),
        smart_money_signal: f.smart_money_signal ?? "Neutral",
        convergence,
        order_book:        ob ? Math.round(e9) : null,
        ob_coverage_tier:  ob?.coverage_tier ?? null,
      },
      conviction: {
        rating:       conviction,
        expected_6m:  convergence >= 75 ? "25-40%" : convergence >= 60 ? "15-25%" : "5-15%",
        expected_12m: convergence >= 75 ? "40-80%" : convergence >= 60 ? "25-45%" : "10-25%",
        risk:         convergence >= 70 ? "Medium" : convergence >= 50 ? "Medium-High" : "High",
        position_size: convergence >= 75 ? "5-7%" : convergence >= 60 ? "3-5%" : "1-3%",
      },
      fundamentals: {
        roce:          Number(f.roce ?? 0),
        roe:           Number(f.roe ?? 0),
        sales_cagr_3y: Number(f.sales_growth_3y ?? f.sales_growth ?? 0),
        eps_cagr_3y:   Number(f.eps_growth_3y ?? f.eps_cagr_3y ?? 0),
        debt_equity:   Number(f.debt_equity ?? 0),
        interest_cover: Number(f.interest_coverage ?? 0),
        pat_growth:    Number(f.profit_growth ?? 0),
      },
      technical: {
        base_months:     Number(w?.base_months ?? 0),
        vol_compression: Number(w?.vol_contraction_pct ?? 0),
        momentum_6m:     Number(f.return_6m ?? 0),
        is_nr7:          w?.is_nr7 ?? false,
        pct_below_high:  Number(w?.pct_below_52w_high ?? 0),
        predicted_tier:  convergence >= 70 ? "Tier-1" : convergence >= 55 ? "Tier-2" : "Tier-3",
        stage:           stage,
        stage_label:     stage === 1 ? "Basing" : stage === 2 ? "Advancing" : stage === 3 ? "Topping" : "Declining",
        breakout_ready:  w?.breakout_ready ?? false,
      },
      signals: {
        business: bizSignals,
        warnings,
        earnings: earningsSignals,
      },
      bulk_deals: {
        buy_qty:    Number(sm?.net_flow_cr ?? 0) > 0 ? Number(sm?.net_flow_cr) : 0,
        sell_qty:   Number(sm?.net_flow_cr ?? 0) < 0 ? Math.abs(Number(sm?.net_flow_cr)) : 0,
        net_flow:   Number(sm?.net_flow_cr ?? 0),
        deal_count: Number(sm?.deal_count ?? 0),
      },
    })

  } catch (err: any) {
    console.error("investment-command-center:", err.message)
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
