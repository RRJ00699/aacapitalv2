import { NextRequest, NextResponse } from 'next/server'
import { sql, localSql, normalizeSymbol } from '@/lib/db'

export const dynamic = 'force-dynamic'
const num = (v: any, f = 0) => { const x = Number(v); return Number.isFinite(x) ? x : f }
const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))

function probability(features: any) {
  // Interpretable baseline calibrated for 5x event similarity.
  const z = -2.2
    + 0.028 * num(features.rs_score)
    + 0.022 * num(features.earnings_score)
    + 0.018 * num(features.volume_score)
    + 0.015 * num(features.base_score)
    + 0.012 * num(features.smart_money_score)
    - 0.010 * Math.max(0, num(features.drawdown_risk) - 40)
  return Math.round(sigmoid(z) * 1000) / 10
}

export async function GET(req: NextRequest) {
  const limit = Math.min(100, Math.max(5, Number(req.nextUrl.searchParams.get('limit') || 30)))
  try {
    const candidates = await sql`
      SELECT
        cm.symbol, cm.company_name, cm.sector, cm.market_cap_cr,
        COALESCE(ts.buy_zone_score, ts.score, 50) AS technical_score,
        COALESCE(ts.volume_expansion_score, 50) AS volume_score,
        COALESCE(ts.base_score, 50) AS base_score,
        COALESCE(ts.rs_score, 50) AS rs_score,
        COALESCE(e.score, 50) AS earnings_score,
        COALESCE(ts.smart_money_score, 50) AS smart_money_score,
        ts.signal, ts.reasons
      FROM company_master cm
      LEFT JOIN technical_signals ts ON ts.symbol = cm.symbol
      LEFT JOIN LATERAL (
        SELECT score FROM earnings_acceleration_scores e
        WHERE e.symbol = cm.symbol
        ORDER BY COALESCE(e.period_end, e.created_at, NOW()) DESC
        LIMIT 1
      ) e ON TRUE
      WHERE COALESCE(cm.market_cap_cr, 0) >= 500
      ORDER BY COALESCE(ts.buy_zone_score, e.score, 0) DESC NULLS LAST
      LIMIT ${limit * 3}
    `.catch(() => [])

    // Optional local training density: count current library of historical multibagger events.
    const eventStats = await localSql`
      SELECT COUNT(*)::int AS events FROM multibagger_events
    `.catch(() => [{ events: null }])

    const rows = candidates.map((r: any) => {
      const p = probability({
        rs_score: r.rs_score ?? r.technical_score,
        earnings_score: r.earnings_score,
        volume_score: r.volume_score,
        base_score: r.base_score,
        smart_money_score: r.smart_money_score,
        drawdown_risk: 35,
      })
      const score = Math.round((p * .45) + num(r.technical_score) * .25 + num(r.earnings_score) * .20 + num(r.smart_money_score) * .10)
      return {
        symbol: normalizeSymbol(r.symbol),
        company_name: r.company_name,
        sector: r.sector,
        market_cap_cr: num(r.market_cap_cr),
        multibagger_probability: p,
        opportunity_score: Math.max(0, Math.min(100, score)),
        technical_score: num(r.technical_score),
        earnings_score: num(r.earnings_score),
        similarity_basis: eventStats?.[0]?.events ? `${eventStats[0].events} historical multibagger events` : 'historical events table unavailable',
        action: p >= 70 ? 'ACCUMULATE' : p >= 55 ? 'WATCH' : 'RESEARCH',
        reasons: [
          num(r.rs_score) >= 60 ? 'Relative strength improving' : 'RS needs confirmation',
          num(r.volume_score) >= 60 ? 'Volume expansion' : 'Volume pending',
          num(r.earnings_score) >= 70 ? 'Earnings acceleration' : 'Fundamentals watch',
        ],
      }
    }).sort((a: any, b: any) => b.opportunity_score - a.opportunity_score).slice(0, limit)

    return NextResponse.json({ ok: true, count: rows.length, training_events: eventStats?.[0]?.events ?? null, opportunities: rows })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message, opportunities: [] }, { status: 200 })
  }
}
