// app/api/multibagger-discovery/route.ts
// Fixed v3: renamed CTEs to avoid reserved word conflicts

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const limit    = parseInt(req.nextUrl.searchParams.get("limit") ?? "30")
  const minScore = parseInt(req.nextUrl.searchParams.get("min_score") ?? "40")

  try {
    const sql = db()

    const candidates = await sql`
      WITH rn_data AS (
        SELECT
          tradingsymbol, close, volume, date,
          ROW_NUMBER() OVER (PARTITION BY tradingsymbol ORDER BY date DESC) AS rn
        FROM price_monthly
      ),
      agg_data AS (
        SELECT
          tradingsymbol,
          MAX(CASE WHEN rn = 1  THEN close  END) AS price_now,
          MAX(CASE WHEN rn = 1  THEN date   END) AS latest_date,
          MAX(CASE WHEN rn = 6  THEN close  END) AS price_6m,
          MAX(CASE WHEN rn = 12 THEN close  END) AS price_12m,
          MAX(CASE WHEN rn <= 12 THEN close END) AS high_52w,
          AVG(CASE WHEN rn <= 3 THEN volume END) AS vol_recent,
          AVG(CASE WHEN rn BETWEEN 4 AND 6 THEN volume END) AS vol_prior,
          COUNT(CASE WHEN rn <= 24 THEN 1 END) AS months_cnt
        FROM rn_data
        WHERE rn <= 24
        GROUP BY tradingsymbol
      ),
      calc_data AS (
        SELECT
          tradingsymbol,
          price_now,
          latest_date,
          high_52w,
          months_cnt,
          COALESCE(vol_recent / NULLIF(vol_prior, 0), 1.0) AS vol_ratio,
          CASE WHEN price_6m  > 0 THEN (price_now - price_6m)  / price_6m  * 100 ELSE 0 END AS ret_6m,
          CASE WHEN price_12m > 0 THEN (price_now - price_12m) / price_12m * 100 ELSE 0 END AS ret_12m,
          CASE WHEN high_52w  > 0 THEN (high_52w  - price_now) / high_52w  * 100 ELSE 0 END AS below_high
        FROM agg_data
        WHERE price_now IS NOT NULL
      ),
      final_score AS (
        SELECT
          tradingsymbol,
          price_now,
          latest_date,
          high_52w,
          months_cnt,
          vol_ratio,
          ret_6m,
          ret_12m,
          below_high,
          LEAST(100, GREATEST(0, ROUND((
            CASE WHEN months_cnt >= 18 THEN 25 WHEN months_cnt >= 12 THEN 20
                 WHEN months_cnt >= 6  THEN 12 ELSE 5 END
            +
            CASE WHEN vol_ratio < 0.50 THEN 25 WHEN vol_ratio < 0.65 THEN 20
                 WHEN vol_ratio < 0.80 THEN 12 WHEN vol_ratio < 1.00 THEN 6 ELSE 0 END
            +
            CASE WHEN ret_6m > 30 THEN 20 WHEN ret_6m > 15 THEN 15
                 WHEN ret_6m > 5  THEN 10 WHEN ret_6m > 0  THEN 5 ELSE 0 END
            +
            CASE WHEN below_high < 3  THEN 15 WHEN below_high < 8  THEN 12
                 WHEN below_high < 15 THEN 7  ELSE 2 END
            +
            CASE WHEN ret_12m > 50 THEN 15 WHEN ret_12m > 25 THEN 10
                 WHEN ret_12m > 10 THEN 6  ELSE 0 END
          )::numeric, 0))) AS dna_score
        FROM calc_data
      )
      SELECT
        fs.tradingsymbol,
        fs.price_now AS current_price,
        fs.latest_date,
        fs.dna_score,
        CASE
          WHEN fs.vol_ratio < 0.65 AND fs.ret_6m > 15 AND fs.months_cnt >= 12 THEN '5x_candidate'
          WHEN fs.vol_ratio < 0.80 AND fs.months_cnt >= 6 THEN '2x_candidate'
          ELSE 'watch'
        END AS predicted_tier,
        fs.months_cnt AS base_months,
        fs.vol_ratio AS vol_compression,
        fs.ret_6m AS momentum_6m,
        fs.ret_12m AS momentum_12m,
        fs.below_high AS pct_below_high,
        f.name,
        f.industry,
        f.business_dna_score,
        f.business_dna_grade,
        f.earnings_score,
        f.smart_money_score,
        f.smart_money_signal,
        f.roce,
        f.market_cap,
        false AS is_nr7,
        false AS is_nr4,
        NULL AS stage,
        ARRAY_REMOVE(ARRAY[
          CASE WHEN fs.vol_ratio < 0.65     THEN 'Vol compression'   END,
          CASE WHEN fs.ret_6m > 15          THEN '6M momentum'       END,
          CASE WHEN fs.months_cnt >= 12     THEN 'Long base'         END,
          CASE WHEN f.business_dna_grade IN ('A+','A') THEN 'Strong DNA' END,
          CASE WHEN f.smart_money_signal LIKE '%Accum%' THEN 'SM accumulation' END
        ], NULL) AS signals,
        ARRAY_REMOVE(ARRAY[
          CASE WHEN fs.ret_6m < -10       THEN 'Negative momentum'     END,
          CASE WHEN f.business_dna_score < 50 THEN 'Weak fundamentals' END,
          CASE WHEN fs.vol_ratio > 1.2    THEN 'Volume expanding'      END
        ], NULL) AS warnings
      FROM final_score fs
      LEFT JOIN stock_fundamentals f ON f.nse_symbol = fs.tradingsymbol
      WHERE fs.dna_score >= ${minScore}
        AND (f.market_cap IS NULL OR f.market_cap > 200)
      ORDER BY fs.dna_score DESC, f.business_dna_score DESC NULLS LAST
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
