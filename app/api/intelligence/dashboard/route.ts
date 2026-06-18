import { NextResponse } from 'next/server';
import { neon } from "@neondatabase/serverless"

const sql = () => neon(process.env.DATABASE_URL!)
export const dynamic = 'force-dynamic';

async function safe<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try { return await promise } catch { return fallback }
}

export async function GET() {
  const db = sql()
  try {
    const [topCommentary, amfi, cautiousCommentary] = await Promise.all([
      safe(db`SELECT nse_symbol AS symbol, company_name, management_tone AS commentary_status,
               mgmt_quality_score AS total_score, guidance_direction, quarter
               FROM management_commentary ORDER BY mgmt_quality_score DESC NULLS LAST LIMIT 10`, []),
      safe(db`SELECT * FROM latest_amfi_liquidity_score LIMIT 1`, []),
      safe(db`SELECT nse_symbol AS symbol, company_name, management_tone AS commentary_status,
               mgmt_quality_score AS total_score, quarter
               FROM management_commentary
               WHERE management_tone IN ('CAUTIOUS','BEARISH')
               ORDER BY mgmt_quality_score ASC NULLS LAST LIMIT 10`, []),
    ])

    // Earnings from technical_signals as proxy (no quarterly_results table yet)
    const topSignals = await safe(db`
      SELECT ts.symbol, COALESCE(f.name, ts.symbol) AS company_name,
             COALESCE(ts.buy_zone_score, 50) AS total_score,
             'STABLE' AS acceleration_status
      FROM technical_signals ts
      LEFT JOIN stock_fundamentals f ON f.nse_symbol = ts.symbol
      WHERE ts.symbol NOT IN ('ANTELOPUS','ACUTAAS')
      ORDER BY COALESCE(ts.buy_zone_score,0) DESC LIMIT 10
    `, [])

    return NextResponse.json({
      success: true,
      data: {
        top_earnings:        topSignals,
        top_commentary:      topCommentary,
        amfi_liquidity:      (amfi as any[])[0] || null,
        warning_earnings:    [],
        cautious_commentary: cautiousCommentary,
      }
    })
  } catch (error: any) {
    return NextResponse.json({ success: false, error: error.message }, { status: 500 })
  }
}
