// app/api/breakout-watch/route.ts
// SESSION 9 — Breakout Watch API
// Returns stocks coiled below their 52W high with building volume.
// Reads breakout_watch_score / breakout_watch_tier written by generate_signals.py
// Fallback: computes score client-side from existing columns if not yet populated.

import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

export async function GET() {
  try {
    // Check if breakout_watch_score column exists yet
    const colCheck = await sql`
      SELECT 1 FROM information_schema.columns
      WHERE table_name = 'technical_signals'
        AND column_name = 'breakout_watch_score'
      LIMIT 1
    `.catch(() => [])

    const hasColumn = colCheck.length > 0

    if (hasColumn) {
      // Fast path: column is populated — just query it
      const rows = await sql`
        SELECT
          ts.symbol,
          COALESCE(cm.company_name, ts.symbol) AS company_name,
          cm.sector,
          ts.close,
          ts.breakout_watch_score,
          ts.breakout_watch_tier,
          ts.pct_below_high,
          ts.is_nr7,
          ts.nr7,
          ts.above_ema200,
          ts.volume_ratio_20,
          ts.vol_compression,
          ts.momentum_6m,
          ts.stage,
          ts.stage_label,
          ts.mb_score,
          ts.buy_zone_score,
          ts.signal_date
        FROM technical_signals ts
        LEFT JOIN company_master cm ON cm.symbol = ts.symbol
        WHERE ts.timeframe = 'daily'
          AND ts.signal_date = (
            SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
          )
          AND ts.breakout_watch_score IS NOT NULL
          AND ts.breakout_watch_score >= 48
          AND (ts.symbol NOT SIMILAR TO '(ANTELOP|ACUTAAS|BMWVENTURE|UNKNOWN)%')
        ORDER BY ts.breakout_watch_score DESC NULLS LAST
        LIMIT 40
      `
      return NextResponse.json({
        success: true,
        data: rows,
        source: "precomputed",
        note: "Scores written by generate_signals.py",
      })
    }

    // Fallback: breakout_watch_score not yet computed — derive live from raw columns.
    // This runs until you do: python _scripts/generate_signals.py (which writes the column).
    const rows = await sql`
      SELECT
        ts.symbol,
        COALESCE(cm.company_name, ts.symbol) AS company_name,
        cm.sector,
        ts.close,
        ts.pct_below_high,
        ts.is_nr7,
        ts.nr7,
        ts.above_ema200,
        ts.volume_ratio_20,
        ts.vol_compression,
        ts.momentum_6m,
        ts.stage,
        ts.stage_label,
        ts.mb_score,
        ts.buy_zone_score,
        ts.signal_date,
        -- Inline breakout watch score approximation
        LEAST(100,
          -- Proximity to 52W high (32 pts)
          CASE
            WHEN ts.pct_below_high IS NULL THEN 0
            WHEN ts.pct_below_high < 0     THEN 8
            WHEN ts.pct_below_high <= 3    THEN GREATEST(22, ROUND(32 * (1.0 - ts.pct_below_high / 4.5)))
            WHEN ts.pct_below_high <= 8    THEN GREATEST(0,  ROUND(20 * (1.0 - (ts.pct_below_high - 3) / 8)))
            ELSE 0
          END
          -- NR7 (16 pts)
          + CASE WHEN COALESCE(ts.is_nr7, ts.nr7, false) THEN 16 ELSE 0 END
          -- Vol compression (10 pts)
          + CASE
              WHEN COALESCE(ts.vol_compression, 1.0) > 1.5 THEN LEAST(10, ROUND((COALESCE(ts.vol_compression,1.0) - 1.0) * 5))
              WHEN COALESCE(ts.vol_compression, 1.0) > 1.2 THEN 4
              ELSE 0
            END
          -- Above EMA200 (11 pts) + EMA30 proxy (7 pts)
          + CASE WHEN COALESCE(ts.above_ema200, false) THEN 11 ELSE 0 END
          + CASE WHEN COALESCE(ts.above_ema200, false) THEN 7 ELSE 0 END
          -- Volume building 1.3–5x (16 pts)
          + CASE
              WHEN COALESCE(ts.volume_ratio_20, 1.0) BETWEEN 1.3 AND 5.0
              THEN GREATEST(5, ROUND(16 * (1.0 - ABS(COALESCE(ts.volume_ratio_20,1.0) - 2.5) / 3.0)))
              WHEN COALESCE(ts.volume_ratio_20, 1.0) > 5.0 THEN 4
              ELSE 0
            END
          -- Stage 1 or 2 (8 pts)
          + CASE WHEN ts.stage IN ('1','2') THEN 8 ELSE 0 END
        ) AS breakout_watch_score,
        CASE
          WHEN LEAST(100,
            CASE WHEN COALESCE(ts.pct_below_high,100)<0 THEN 8
                 WHEN COALESCE(ts.pct_below_high,100)<=3 THEN GREATEST(22,ROUND(32*(1.0-COALESCE(ts.pct_below_high,100)/4.5)))
                 WHEN COALESCE(ts.pct_below_high,100)<=8 THEN GREATEST(0,ROUND(20*(1.0-(COALESCE(ts.pct_below_high,100)-3)/8)))
                 ELSE 0 END
            + CASE WHEN COALESCE(ts.is_nr7,ts.nr7,false) THEN 16 ELSE 0 END
            + CASE WHEN COALESCE(ts.vol_compression,1.0)>1.5 THEN LEAST(10,ROUND((COALESCE(ts.vol_compression,1.0)-1.0)*5))
                   WHEN COALESCE(ts.vol_compression,1.0)>1.2 THEN 4 ELSE 0 END
            + CASE WHEN COALESCE(ts.above_ema200,false) THEN 18 ELSE 0 END
            + CASE WHEN COALESCE(ts.volume_ratio_20,1.0) BETWEEN 1.3 AND 5.0 THEN GREATEST(5,ROUND(16*(1.0-ABS(COALESCE(ts.volume_ratio_20,1.0)-2.5)/3.0)))
                   WHEN COALESCE(ts.volume_ratio_20,1.0)>5.0 THEN 4 ELSE 0 END
            + CASE WHEN ts.stage IN ('1','2') THEN 8 ELSE 0 END
          ) >= 80 THEN 'COILED'
          WHEN LEAST(100,
            CASE WHEN COALESCE(ts.pct_below_high,100)<0 THEN 8
                 WHEN COALESCE(ts.pct_below_high,100)<=3 THEN GREATEST(22,ROUND(32*(1.0-COALESCE(ts.pct_below_high,100)/4.5)))
                 WHEN COALESCE(ts.pct_below_high,100)<=8 THEN GREATEST(0,ROUND(20*(1.0-(COALESCE(ts.pct_below_high,100)-3)/8)))
                 ELSE 0 END
            + CASE WHEN COALESCE(ts.is_nr7,ts.nr7,false) THEN 16 ELSE 0 END
            + CASE WHEN COALESCE(ts.vol_compression,1.0)>1.5 THEN LEAST(10,ROUND((COALESCE(ts.vol_compression,1.0)-1.0)*5))
                   WHEN COALESCE(ts.vol_compression,1.0)>1.2 THEN 4 ELSE 0 END
            + CASE WHEN COALESCE(ts.above_ema200,false) THEN 18 ELSE 0 END
            + CASE WHEN COALESCE(ts.volume_ratio_20,1.0) BETWEEN 1.3 AND 5.0 THEN GREATEST(5,ROUND(16*(1.0-ABS(COALESCE(ts.volume_ratio_20,1.0)-2.5)/3.0)))
                   WHEN COALESCE(ts.volume_ratio_20,1.0)>5.0 THEN 4 ELSE 0 END
            + CASE WHEN ts.stage IN ('1','2') THEN 8 ELSE 0 END
          ) >= 60 THEN 'BUILDING'
          WHEN LEAST(100,
            CASE WHEN COALESCE(ts.pct_below_high,100)<0 THEN 8
                 WHEN COALESCE(ts.pct_below_high,100)<=3 THEN GREATEST(22,ROUND(32*(1.0-COALESCE(ts.pct_below_high,100)/4.5)))
                 WHEN COALESCE(ts.pct_below_high,100)<=8 THEN GREATEST(0,ROUND(20*(1.0-(COALESCE(ts.pct_below_high,100)-3)/8)))
                 ELSE 0 END
            + CASE WHEN COALESCE(ts.is_nr7,ts.nr7,false) THEN 16 ELSE 0 END
            + CASE WHEN COALESCE(ts.vol_compression,1.0)>1.5 THEN LEAST(10,ROUND((COALESCE(ts.vol_compression,1.0)-1.0)*5))
                   WHEN COALESCE(ts.vol_compression,1.0)>1.2 THEN 4 ELSE 0 END
            + CASE WHEN COALESCE(ts.above_ema200,false) THEN 18 ELSE 0 END
            + CASE WHEN COALESCE(ts.volume_ratio_20,1.0) BETWEEN 1.3 AND 5.0 THEN GREATEST(5,ROUND(16*(1.0-ABS(COALESCE(ts.volume_ratio_20,1.0)-2.5)/3.0)))
                   WHEN COALESCE(ts.volume_ratio_20,1.0)>5.0 THEN 4 ELSE 0 END
            + CASE WHEN ts.stage IN ('1','2') THEN 8 ELSE 0 END
          ) >= 48 THEN 'EARLY'
          ELSE NULL
        END AS breakout_watch_tier
      FROM technical_signals ts
      LEFT JOIN company_master cm ON cm.symbol = ts.symbol
      WHERE ts.timeframe = 'daily'
        AND ts.signal_date = (
          SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
        )
        AND ts.pct_below_high IS NOT NULL
        AND ts.pct_below_high <= 10
        AND COALESCE(ts.above_ema200, false) = true
        AND (ts.symbol NOT SIMILAR TO '(ANTELOP|ACUTAAS|BMWVENTURE|UNKNOWN)%')
      ORDER BY 1 DESC  -- will re-order by breakout_watch_score below
      LIMIT 100
    `

    // Sort in JS since the inline SQL score is verbose to reference in ORDER BY
    const sorted = (rows as any[])
      .sort((a, b) => (Number(b.breakout_watch_score) || 0) - (Number(a.breakout_watch_score) || 0))
      .filter(r => Number(r.breakout_watch_score) >= 48)
      .slice(0, 40)

    return NextResponse.json({
      success: true,
      data: sorted,
      source: "fallback_sql",
      note: "Run python _scripts/generate_signals.py to pre-compute scores for faster queries",
    })

  } catch (error: unknown) {
    return NextResponse.json(
      { success: false, error: String(error) },
      { status: 500 }
    )
  }
}
