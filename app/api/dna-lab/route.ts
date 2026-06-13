// app/api/multibagger-discovery/route.ts
// Fixed: window function calls inside aggregate error
// Uses CTEs to pre-compute row numbers before aggregation

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const limit    = parseInt(req.nextUrl.searchParams.get("limit") ?? "30")
  const minScore = parseInt(req.nextUrl.searchParams.get("min_score") ?? "40")

  try {
    const sql = db()

    const candidates = await sql`
      WITH ranked AS (
        SELECT
          tradingsymbol, close, volume, date,
          ROW_NUMBER() OVER (PARTITION BY tradingsymbol ORDER BY date DESC) AS rn
        FROM price_monthly
      ),
      latest_price AS (
        SELECT tradingsymbol, close AS current_price, date AS latest_date
        FROM ranked WHERE rn = 1
      ),
      recent_candles AS (
        SELECT
          tradingsymbol,
          COALESCE(
            AVG(CASE WHEN rn <= 3 THEN volume END) /
            NULLIF(AVG(CASE WHEN rn BETWEEN 4 AND 6 THEN volume END), 0), 1
          ) AS vol_comp,
          CASE WHEN MAX(CASE WHEN rn = 6  THEN close END) > 0
            THEN (MAX(CASE WHEN rn = 1 THEN close END) - MAX(CASE WHEN rn = 6  THEN close END)) /
                  MAX(CASE WHEN rn = 6  THEN close END) * 100 ELSE 0 END AS mom_6m,
          CASE WHEN MAX(CASE WHEN rn = 12 THEN close END) > 0
            THEN (MAX(CASE WHEN rn = 1 THEN close END) - MAX(CASE WHEN rn = 12 THEN close END)) /
                  MAX(CASE WHEN rn = 12 THEN close END) * 100 ELSE 0 END AS mom_12m,
          COUNT(CASE WHEN rn <= 24 THEN 1 END) AS base_months,
          MAX(CASE WHEN rn <= 12 THEN close END) AS high_52w
        FROM ranked WHERE rn <= 24
        GROUP BY tradingsymbol
      ),
      scored AS (
        SELECT
          r.tradingsymbol,
          lp.current_price,
          lp.latest_date,
          r.vol_comp,
          r.mom_6m,
          r.mom_12m,
          r.base_months,
          r.high_52w,
          CASE WHEN r.high_52w > 0
            THEN (r.high_52w - lp.current_price) / r.high_52w * 100
            ELSE 0 END AS pct_below_high,
          LEAST(100, GREATEST(0, ROUND((
            CASE WHEN r.base_months >= 18 THEN 25 WHEN r.base_months >= 12 THEN 20
                 WHEN r.base_months >= 6 THEN 12 ELSE 5 END +
            CASE WHEN r.vol_comp < 0.5 THEN 25 WHEN r.vol_comp < 0.65 THEN 20
                 WHEN r.vol_comp < 0.8 THEN 12 WHEN r.vol_comp < 1.0 THEN 6 ELSE 0 END +
            CASE WHEN r.mom_6m > 30 THEN 20 WHEN r.mom_6m > 15 THEN 15
                 WHEN r.mom_6m > 5 THEN 10 WHEN r.mom_6m > 0 THEN 5 ELSE 0 END +
            CASE WHEN (r.high_52w - lp.current_price) / NULLIF(r.high_52w,0)*100 < 3 THEN 15
                 WHEN (r.high_52w - lp.current_price) / NULLIF(r.high_52w,0)*100 < 8 THEN 12
                 WHEN (r.high_52w - lp.current_price) / NULLIF(r.high_52w,0)*100 < 15 THEN 7
                 ELSE 2 END +
            CASE WHEN r.mom_12m > 50 THEN 15 WHEN r.mom_12m > 25 THEN 10
                 WHEN r.mom_12m > 10 THEN 6 ELSE 0 END
          )::numeric, 0))) AS dna_score,
          CASE
            WHEN r.vol_comp < 0.65 AND r.mom_6m > 15 AND r.base_months >= 12 THEN '5x_candidate'
            WHEN r.vol_comp < 0.8 AND r.base_months >= 6 THEN '2x_candidate'
            ELSE 'watch'
          END AS predicted_tier
        FROM recent_candles r
        JOIN latest_price lp ON lp.tradingsymbol = r.tradingsymbol
      )
      SELECT
        s.tradingsymbol,
        s.current_price,
        s.latest_date,
        s.dna_score,
        s.predicted_tier,
        s.base_months,
        s.vol_comp AS vol_compression,
        s.mom_6m AS momentum_6m,
        s.mom_12m AS momentum_12m,
        s.pct_below_high,
        f.name,
        f.industry,
        f.business_dna_score,
        f.business_dna_grade,
        f.earnings_score,
        f.smart_money_score,
        f.smart_money_signal,
        f.roce,
        f.market_cap,
        COALESCE(w.is_nr7, false) AS is_nr7,
        COALESCE(w.is_nr4, false) AS is_nr4,
        w.stage,
        ARRAY_REMOVE(ARRAY[
          CASE WHEN s.vol_comp < 0.65 THEN 'Vol compression' END,
          CASE WHEN s.mom_6m > 15 THEN '6M momentum' END,
          CASE WHEN s.base_months >= 12 THEN 'Long base' END,
          CASE WHEN w.is_nr7 THEN 'NR7 coil' END,
          CASE WHEN f.business_dna_grade IN ('A+','A') THEN 'Strong DNA' END,
          CASE WHEN f.smart_money_signal LIKE '%Accum%' THEN 'SM accumulation' END
        ], NULL) AS signals,
        ARRAY_REMOVE(ARRAY[
          CASE WHEN s.mom_6m < -10 THEN 'Negative momentum' END,
          CASE WHEN f.business_dna_score < 50 THEN 'Weak fundamentals' END,
          CASE WHEN s.vol_comp > 1.2 THEN 'Volume expanding' END
        ], NULL) AS warnings
      FROM scored s
      LEFT JOIN stock_fundamentals f ON f.nse_symbol = s.tradingsymbol
      LEFT JOIN weekly_dna w ON w.tradingsymbol = s.tradingsymbol
      WHERE s.dna_score >= ${minScore}
        AND (f.market_cap IS NULL OR f.market_cap > 200)
      ORDER BY s.dna_score DESC, f.business_dna_score DESC NULLS LAST
      LIMIT ${limit}
    `

    return NextResponse.json({ ok: true, count: candidates.length, min_score: minScore, data: candidates })

  } catch (err: any) {
    console.error("multibagger-discovery:", err.message)
    if (err.message?.includes("does not exist")) {
      return NextResponse.json({ ok: false, error: "Tables missing. Run import scripts." }, { status: 503 })
    }
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
