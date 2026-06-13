// app/api/guidance-accuracy/route.ts
// Compares management guidance from quarter N vs actuals in quarter N+1
// Uses existing earnings_events + management_commentary data
// GET /api/guidance-accuracy?symbol=WABAG
// GET /api/guidance-accuracy?view=all (all stocks ranked by accuracy)

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

// Quarter sequence for comparing guidance vs actuals
const QUARTER_SEQUENCE = [
  "Q1FY25","Q2FY25","Q3FY25","Q4FY25",
  "Q1FY26","Q2FY26","Q3FY26","Q4FY26",
  "Q1FY27","Q2FY27"
]

function nextQuarter(q: string): string | null {
  const idx = QUARTER_SEQUENCE.indexOf(q)
  return idx >= 0 && idx < QUARTER_SEQUENCE.length - 1 ? QUARTER_SEQUENCE[idx + 1] : null
}

function assessAccuracy(guidanceChange: string | null, revenueGrowth: number | null): string {
  if (!guidanceChange || revenueGrowth === null) return "UNKNOWN"
  if (guidanceChange === "RAISED" && revenueGrowth > 5)   return "DELIVERED"
  if (guidanceChange === "RAISED" && revenueGrowth <= 0)  return "MISSED"
  if (guidanceChange === "RAISED" && revenueGrowth > 0)   return "PARTIAL"
  if (guidanceChange === "MAINTAINED" && revenueGrowth > -5) return "DELIVERED"
  if (guidanceChange === "MAINTAINED" && revenueGrowth <= -5) return "MISSED"
  if (guidanceChange === "LOWERED" && revenueGrowth < 0)  return "DELIVERED"
  if (guidanceChange === "LOWERED" && revenueGrowth >= 5) return "EXCEEDED"
  return "INLINE"
}

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol")?.toUpperCase()
  const view   = req.nextUrl.searchParams.get("view") ?? "symbol"
  const sql    = db()

  try {

    if (symbol || view === "symbol") {
      const sym = symbol ?? ""

      // Get management guidance per quarter
      const guidance = await sql`
        SELECT quarter, guidance_direction, management_tone, revenue_guidance
        FROM management_commentary
        WHERE nse_symbol = ${sym}
        ORDER BY quarter ASC
      `

      // Get actual results per quarter
      const actuals = await sql`
        SELECT quarter, actual_revenue_cr, revenue_yoy_pct, pat_yoy_pct,
               surprise_type, actual_eps
        FROM earnings_events
        WHERE nse_symbol = ${sym}
        ORDER BY quarter ASC
      `

      const actualsMap = new Map(actuals.map((a: any) => [a.quarter, a]))

      // Compare each guidance quarter vs next quarter actuals
      const comparisons = guidance.map((g: any) => {
        const next = nextQuarter(g.quarter)
        const actual = next ? actualsMap.get(next) : null

        const revenueGrowth = actual?.revenue_yoy_pct ? Number(actual.revenue_yoy_pct) : null
        const accuracy = assessAccuracy(g.guidance_direction, revenueGrowth)

        return {
          guidance_quarter:   g.quarter,
          actuals_quarter:    next,
          guidance_given:     g.guidance_direction,
          management_tone:    g.management_tone,
          revenue_guidance_text: g.revenue_guidance,
          actual_revenue_yoy: revenueGrowth,
          actual_eps:         actual?.actual_eps ? Number(actual.actual_eps) : null,
          surprise_type:      actual?.surprise_type ?? null,
          accuracy,
          verdict: accuracy === "DELIVERED" || accuracy === "EXCEEDED" ? "✓ Accurate"
                 : accuracy === "MISSED" ? "✗ Missed"
                 : accuracy === "PARTIAL" ? "~ Partial"
                 : "— Unknown",
        }
      }).filter((c: any) => c.actuals_quarter) // only where we have next quarter data

      // Management quality score
      const scored = comparisons.filter((c: any) => c.accuracy !== "UNKNOWN")
      const delivered = scored.filter((c: any) => ["DELIVERED","EXCEEDED"].includes(c.accuracy)).length
      const mgmtScore = scored.length > 0 ? Math.round((delivered / scored.length) * 100) : null

      return NextResponse.json({
        ok: true, symbol: sym,
        mgmt_accuracy_score: mgmtScore,
        mgmt_accuracy_label: mgmtScore === null ? "Insufficient data"
          : mgmtScore >= 80 ? "Highly reliable management"
          : mgmtScore >= 60 ? "Generally reliable"
          : "Guidance often misses",
        quarters_analyzed: scored.length,
        quarters_delivered: delivered,
        comparisons,
      })
    }

    // All stocks ranked by guidance accuracy
    if (view === "all") {
      const stocks = await sql`
        SELECT DISTINCT mc.nse_symbol, f.name, f.industry
        FROM management_commentary mc
        JOIN stock_fundamentals f ON f.nse_symbol = mc.nse_symbol
        WHERE mc.guidance_direction IS NOT NULL
        ORDER BY mc.nse_symbol
        LIMIT 50
      `

      const results = []
      for (const stock of stocks) {
        const guidance = await sql`
          SELECT quarter, guidance_direction FROM management_commentary
          WHERE nse_symbol = ${stock.nse_symbol} AND guidance_direction IS NOT NULL
          ORDER BY quarter ASC
        `
        const actuals = await sql`
          SELECT quarter, revenue_yoy_pct FROM earnings_events
          WHERE nse_symbol = ${stock.nse_symbol} ORDER BY quarter ASC
        `
        const actualsMap = new Map(actuals.map((a: any) => [a.quarter, a]))
        let delivered = 0, total = 0

        for (const g of guidance) {
          const next = nextQuarter(g.quarter)
          const actual = next ? actualsMap.get(next) : null
          if (!actual) continue
          const acc = assessAccuracy(g.guidance_direction, Number(actual.revenue_yoy_pct ?? 0))
          if (acc !== "UNKNOWN") {
            total++
            if (["DELIVERED","EXCEEDED"].includes(acc)) delivered++
          }
        }

        if (total >= 2) {
          results.push({
            symbol: stock.nse_symbol,
            name: stock.name,
            mgmt_score: Math.round((delivered / total) * 100),
            quarters: total,
            delivered,
          })
        }
      }

      results.sort((a, b) => b.mgmt_score - a.mgmt_score)

      return NextResponse.json({ ok: true, view: "all", stocks: results })
    }

    return NextResponse.json({ error: "provide symbol or view=all" }, { status: 400 })

  } catch (err: any) {
    console.error("guidance-accuracy:", err.message)
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
