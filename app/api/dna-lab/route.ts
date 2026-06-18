import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const view     = req.nextUrl.searchParams.get("view") || "top20"
  const limit    = parseInt(req.nextUrl.searchParams.get("limit") ?? "30")
  const minScore = parseInt(req.nextUrl.searchParams.get("min_score") ?? "40")
  const sql      = db()

  try {
    // ── Top candidates from technical_signals + stock_fundamentals ──────────
    if (view === "top20" || view === "list") {
      const rows = await sql`
        SELECT
          ts.symbol                                   AS tradingsymbol,
          COALESCE(f.name, ts.symbol)                  AS name,
          COALESCE(f.industry, '')                     AS industry,
          COALESCE(f.market_cap, 0)                    AS market_cap,
          COALESCE(f.business_dna_score, 0)            AS business_dna_score,
          COALESCE(f.business_dna_grade, '—')          AS business_dna_grade,
          COALESCE(f.earnings_score, 50)               AS earnings_score,
          COALESCE(f.smart_money_score, 50)            AS smart_money_score,
          COALESCE(f.smart_money_signal, 'Neutral')    AS smart_money_signal,
          COALESCE(f.roce, 0)                          AS roce,
          COALESCE(ts.buy_zone_score, ts.score, 50)    AS dna_score,
          COALESCE(ts.convergence_score, 0)            AS convergence_score,
          ts.is_nr7,
          ts.base_months,
          ts.vol_compression,
          ts.momentum_6m,
          ts.above_ema200,
          CASE
            WHEN COALESCE(ts.buy_zone_score,0) >= 80 THEN '5x_candidate'
            WHEN COALESCE(ts.buy_zone_score,0) >= 65 THEN '2x_candidate'
            ELSE 'watch'
          END AS predicted_tier
        FROM technical_signals ts
        LEFT JOIN stock_fundamentals f ON f.nse_symbol = ts.symbol
        WHERE COALESCE(ts.buy_zone_score, ts.score, 0) >= ${minScore}
          AND ts.symbol NOT IN ('ANTELOPUS','ACUTAAS')
        ORDER BY COALESCE(ts.buy_zone_score, ts.score, 0) DESC NULLS LAST
        LIMIT ${limit}
      `
      return NextResponse.json({ ok: true, count: rows.length, data: rows })
    }

    // ── Regime analysis from market_regimes ────────────────────────────────
    if (view === "regime") {
      const rows = await sql`
        SELECT
          active_regime         AS regime_at_base,
          COUNT(*)              AS stocks,
          ROUND(AVG(breadth_percentage),1) AS avg_breadth,
          evaluation_date
        FROM market_regimes
        GROUP BY active_regime, evaluation_date
        ORDER BY evaluation_date DESC
        LIMIT 10
      `
      return NextResponse.json({ ok: true, data: rows })
    }

    // ── Sector breakdown from technical_signals + stock_fundamentals ────────
    if (view === "sectors") {
      const rows = await sql`
        SELECT
          COALESCE(f.industry_group, f.industry, 'Unknown') AS sector,
          COUNT(*)                                            AS stock_count,
          ROUND(AVG(COALESCE(ts.buy_zone_score, 0)), 1)      AS avg_score,
          SUM(CASE WHEN ts.is_nr7 THEN 1 ELSE 0 END)         AS nr7_count
        FROM technical_signals ts
        LEFT JOIN stock_fundamentals f ON f.nse_symbol = ts.symbol
        WHERE ts.symbol NOT IN ('ANTELOPUS','ACUTAAS')
        GROUP BY COALESCE(f.industry_group, f.industry, 'Unknown')
        ORDER BY avg_score DESC NULLS LAST
        LIMIT 20
      `
      return NextResponse.json({ ok: true, data: rows })
    }

    // ── DNA stats summary ──────────────────────────────────────────────────
    if (view === "dna_stats") {
      const rows = await sql`
        SELECT
          COUNT(*)                                            AS total_candidates,
          COUNT(CASE WHEN COALESCE(ts.buy_zone_score,0)>=80 THEN 1 END) AS five_x,
          COUNT(CASE WHEN COALESCE(ts.buy_zone_score,0)>=65 AND COALESCE(ts.buy_zone_score,0)<80 THEN 1 END) AS two_x,
          COUNT(CASE WHEN ts.is_nr7 THEN 1 END)              AS nr7_count,
          ROUND(AVG(COALESCE(ts.buy_zone_score,0)),1)        AS avg_score
        FROM technical_signals ts
        WHERE ts.symbol NOT IN ('ANTELOPUS','ACUTAAS')
      `
      return NextResponse.json({ ok: true, data: rows[0] || {} })
    }

    return NextResponse.json({ ok: false, error: "Unknown view" }, { status: 400 })

  } catch (err: any) {
    console.error("dna-lab:", err.message)
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
