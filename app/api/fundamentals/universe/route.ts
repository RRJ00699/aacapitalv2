import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

//  /api/fundamentals/universe
// One row per stock joining the THREE validated fundamental engines onto company_master:
//   financial_dna (quality grade + sub-scores) + valuation (P/E percentile vs own history) +
//   quarterly_financials (latest quarter net-profit & sales YoY).
// This single endpoint powers the Quality+Value screen, the sortable DNA/valuation columns, and
// the sector peer panel. Research/context, NOT buy calls. Optional ?sector= narrows to one sector.

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}

export async function GET(req: NextRequest) {
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const sector = req.nextUrl.searchParams.get("sector")

    const rows = await sql`
      WITH latest AS (
        SELECT DISTINCT ON (symbol) symbol, fiscal_label, net_profit, sales
        FROM quarterly_financials
        ORDER BY symbol, period DESC
      ),
      yoy AS (
        SELECT l.symbol, l.fiscal_label, l.net_profit, l.sales,
               py.net_profit AS np_prev, py.sales AS sales_prev
        FROM latest l
        LEFT JOIN quarterly_financials py
          ON py.symbol = l.symbol
         AND py.fiscal_label =
             ((split_part(l.fiscal_label,'-',1)::int - 1)::text || '-' || split_part(l.fiscal_label,'-',2))
      )
      SELECT cm.nse_symbol            AS symbol,
             cm.company_name          AS name,
             cm.sector                AS sector,
             cm.industry              AS industry,
             cm.market_cap_cr         AS market_cap_cr,
             d.dna_score, d.grade,
             d.growth, d.profitability, d.cashflow, d.balancesheet,
             d.capalloc, d.efficiency, d.earnings_quality, d.risk,
             v.current_pe, v.ttm_pe, v.current_pb, v.pe_percentile, v.pb_percentile,
             v.pe_median, v.verdict   AS val_verdict, v.years AS val_years,
             y.fiscal_label           AS q_label,
             y.net_profit             AS q_net_profit,
             y.sales                  AS q_sales,
             CASE WHEN y.np_prev IS NOT NULL AND y.np_prev <> 0
                  THEN (y.net_profit - y.np_prev) / abs(y.np_prev) * 100 END AS np_yoy,
             CASE WHEN y.sales_prev IS NOT NULL AND y.sales_prev <> 0
                  THEN (y.sales - y.sales_prev) / abs(y.sales_prev) * 100 END AS sales_yoy
      FROM company_master cm
      JOIN financial_dna d ON d.symbol = cm.nse_symbol
      LEFT JOIN valuation v ON v.symbol = cm.nse_symbol
      LEFT JOIN yoy y ON y.symbol = cm.nse_symbol
      WHERE cm.nse_symbol IS NOT NULL
        AND COALESCE(cm.is_active, true) = true
        AND (${sector}::text IS NULL OR cm.sector = ${sector})
      ORDER BY d.dna_score DESC NULLS LAST`

    const stocks = (rows as any[]).map(r => ({
      symbol: r.symbol,
      name: r.name || r.symbol,
      sector: r.sector || null,
      industry: r.industry || null,
      market_cap_cr: num(r.market_cap_cr),
      dna_score: num(r.dna_score),
      grade: r.grade || null,
      subs: {
        growth: num(r.growth), profitability: num(r.profitability), cashflow: num(r.cashflow),
        balancesheet: num(r.balancesheet), capalloc: num(r.capalloc),
        efficiency: num(r.efficiency), earnings_quality: num(r.earnings_quality), risk: num(r.risk),
      },
      pe: num(r.current_pe), ttm_pe: num(r.ttm_pe), pb: num(r.current_pb),
      pe_percentile: num(r.pe_percentile), pb_percentile: num(r.pb_percentile),
      pe_median: num(r.pe_median), val_verdict: r.val_verdict || null, val_years: num(r.val_years),
      q_label: r.q_label || null,
      np_yoy: num(r.np_yoy), sales_yoy: num(r.sales_yoy),
    }))

    return NextResponse.json({ count: stocks.length, stocks },
      { headers: { "Cache-Control": "public, max-age=1800" } })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
