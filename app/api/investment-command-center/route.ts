import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

const n = (v: any, f = 0) => { const x = Number(v); return Number.isFinite(x) ? x : f }
const pick = (...v: any[]) => v.find(x => x !== null && x !== undefined && String(x) !== "")
const safe = async <T,>(p: Promise<T>, f: T): Promise<T> => { try { return await p } catch { return f } }

function calcLevels(price: number, w: any) {
  const p = price || n(w?.close, 100)
  const atr = Math.max(p * 0.035, n(w?.atr_14, p * 0.035))
  const support1 = n(w?.support_1, p - atr)
  const support2 = n(w?.support_2, p - atr * 1.8)
  const resistance1 = n(w?.resistance_1, p + atr)
  const resistance2 = n(w?.resistance_2, p + atr * 1.8)
  return {
    support: [Math.round(support1), Math.round(support2)],
    resistance: [Math.round(resistance1), Math.round(resistance2)],
    targets: [Math.round(p + atr * 1.2), Math.round(p + atr * 2.2), Math.round(p + atr * 3.5)],
    stopLoss: Math.round(Math.min(support1, p - atr * 1.3)),
  }
}

export async function GET(req: NextRequest) {
  const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })

  const [fRows, cmRows, tRows, eRows, shRows, valRows] = await Promise.all([
    safe(sql`SELECT * FROM stock_fundamentals WHERE UPPER(nse_symbol) = ${symbol} LIMIT 1`, [] as any[]),
    safe(sql`SELECT * FROM company_master WHERE UPPER(symbol) = ${symbol} LIMIT 1`, [] as any[]),
    safe(sql`SELECT * FROM technical_signals WHERE UPPER(symbol) = ${symbol} LIMIT 1`, [] as any[]),
    safe(sql`SELECT * FROM earnings_acceleration_scores WHERE UPPER(symbol) = ${symbol} ORDER BY scored_at DESC NULLS LAST LIMIT 1`, [] as any[]),
    safe(sql`SELECT promoter_pct, promoter_pledge, fii_pct, dii_pct, mf_pct, public_pct
             FROM shareholding_history WHERE UPPER(nse_symbol) = ${symbol}
             ORDER BY quarter DESC LIMIT 1`, [] as any[]),
    safe(sql`SELECT current_pb, current_pe FROM valuation WHERE UPPER(symbol) = ${symbol} LIMIT 1`, [] as any[]),
  ])

  const f = fRows[0] || {}
  const val = valRows[0] || {}
  const cm = cmRows[0] || {}
  const w: any = {}   // weekly_dna retired — support/resistance now fall back to ATR-derived defaults (or use technical_features descriptors)
  const ts = tRows[0] || {}
  const es = eRows[0] || {}
  const sm: any = {}   // smart_money_summary retired — score/signal now read from stock_fundamentals (f)
  const sh = shRows[0] || {}   // latest real shareholding (FII/DII/promoter) from scrape_shareholding

  // If no data at all, return graceful empty response (not 404)
  if (!Object.keys(f).length && !Object.keys(cm).length && !Object.keys(ts).length) {
    return NextResponse.json({
      ok: true,
      symbol,
      name: symbol,
      current_price: 0,
      industry: "Unknown",
      scores: { technical_dna: 0, business_dna: 0, earnings: 50, smart_money: 50, convergence: 0 },
      signals: { business: [], warnings: [`${symbol} not yet in fundamentals database`], earnings: [] },
      conviction: { expected_6m: "—", expected_12m: "—", position_size: "—", risk: "—" },
    })
  }

  const price = n(pick(f.current_price, ts.current_price, ts.close, w.close, 0))
  const business = Math.max(0, Math.min(100, n(pick(f.business_dna_score, f.business_score, 55))))
  const earnings = Math.max(0, Math.min(100, n(pick(es.score, es.earnings_momentum_score, f.earnings_score, 50))))
  const technical = Math.max(0, Math.min(100, n(pick(ts.score, ts.convergence_score, w.technical_score, 50)) + (w.is_nr7 ? 10 : 0) + (w.breakout_ready ? 8 : 0)))
  const smart = Math.max(0, Math.min(100, n(pick(f.smart_money_score, sm.smart_money_score, 50))))
  const sector = Math.max(0, Math.min(100, n(pick(f.sector_rotation_score, 50))))
  const convergence = Math.round(Math.max(0, Math.min(100, business * 0.28 + earnings * 0.22 + technical * 0.25 + smart * 0.15 + sector * 0.10)))
  const levels = calcLevels(price, w)
  const conviction = convergence >= 80 ? "Exceptional" : convergence >= 65 ? "High" : convergence >= 50 ? "Medium" : "Low"

  return NextResponse.json({
    ok: true,
    symbol,
    name: pick(f.name, cm.company_name, symbol),
    current_price: price,
    market_cap: n(pick(f.market_cap, cm.market_cap_cr, 0)),
    industry: pick(f.industry, cm.sector, "—"),
    scores: {
      technical_dna: Math.round(technical), business_dna: Math.round(business), business_grade: pick(f.business_dna_grade, business >= 80 ? "A+" : business >= 65 ? "A" : "B"),
      earnings: Math.round(earnings), earnings_category: pick(es.conviction_level, es.category, "Stable"), smart_money: Math.round(smart), smart_money_signal: pick(f.smart_money_signal, sm.signal, "Neutral"), convergence,
    },
    conviction: {
      rating: conviction,
      expected_6m: convergence >= 75 ? "25-40%" : convergence >= 60 ? "15-25%" : "5-15%",
      expected_12m: convergence >= 75 ? "40-80%" : convergence >= 60 ? "25-45%" : "10-25%",
      risk: convergence >= 70 ? "Medium" : convergence >= 50 ? "Medium-High" : "High",
      position_size: convergence >= 75 ? "5-7%" : convergence >= 60 ? "3-5%" : "1-3%",
    },
    fundamentals: {
      roce: n(pick(f.roce, cm.roce, 0)),
      roe: n(pick(f.roe, cm.roe, 0)),
      sales_cagr_3y: n(pick(f.sales_growth_3y, f.sales_growth, 0)),
      eps_cagr_3y: n(pick(f.eps_growth_3y, f.eps_cagr_3y, 0)),
      debt_equity: n(pick(f.debt_equity, f.debt_to_equity, 0)),
      interest_cover: n(pick(f.interest_coverage, f.interest_cover, 0)),
      pat_growth: n(pick(f.pat_growth_1y, f.profit_growth, f.pat_growth, 0)),
      pe_ratio: n(pick(f.pe_ratio, f.pe, 0)),
      pb_ratio: n(pick(f.pb_ratio, f.price_to_book, val.current_pb, 0)),
      promoter_holding: n(pick(sh.promoter_pct, f.promoter_holding, 0)),
      promoter_pledge: n(pick(sh.promoter_pledge, f.promoter_pledge, 0)),
      fii_holding: n(pick(sh.fii_pct, f.fii_holding, 0)),
      dii_holding: n(pick(sh.dii_pct, f.dii_holding, 0)),
      mf_holding: n(pick(sh.mf_pct, f.mf_holding, 0)),
      operating_margin: n(pick(f.opm_pct, f.operating_margin, f.opm, 0)),
      dividend_yield: n(pick(f.dividend_yield, 0)),
      market_cap: n(pick(f.market_cap, cm.market_cap_cr, 0)),
    },
    technical: {
      base_months: n(pick(w.base_months, 0)), vol_compression: n(pick(w.vol_contraction_pct, 0)), momentum_6m: n(pick(f.return_6m, 0)), is_nr7: !!w.is_nr7, pct_below_high: n(pick(w.pct_below_52w_high, 0)), predicted_tier: convergence >= 70 ? "Tier-1" : convergence >= 55 ? "Tier-2" : "Tier-3", stage: n(pick(w.stage, 2)), stage_label: pick(w.stage_label, "Setup"), breakout_ready: !!w.breakout_ready,
      support: levels.support, resistance: levels.resistance, targets: levels.targets, stop_loss: levels.stopLoss,
    },
    trade_plan: { support: levels.support, resistance: levels.resistance, targets: levels.targets, stopLoss: levels.stopLoss },
    signals: { business: [`Convergence ${convergence}/100`, `Technical DNA ${Math.round(technical)}/100`, `Earnings ${Math.round(earnings)}/100`], warnings: [], earnings: [] },
    bulk_deals: { buy_qty: Math.max(0, n(sm.net_flow_cr)), sell_qty: Math.max(0, -n(sm.net_flow_cr)), net_flow: n(sm.net_flow_cr), deal_count: n(sm.deal_count) },
  })
}
