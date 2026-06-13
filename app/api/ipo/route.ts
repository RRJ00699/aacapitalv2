// app/api/ipo/route.ts
// IPO API — reads from ipo_live table (populated by fetch_live_ipos.py)
// Falls back to lib/ipo/pipeline.ts static data if table empty

import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"
import { getIpoPipeline } from "@/lib/ipo/pipeline"
import { scoreIpo } from "@/lib/ipo/scoring"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const status = searchParams.get("status") || ""    // OPEN|UPCOMING|CLOSED
    const limit  = Math.min(50, parseInt(searchParams.get("limit") || "20"))

    // Try DB first (populated by cron)
    const dbIpos = await sql`
      SELECT
        id, name, symbol, open_date, close_date,
        price_band_low, price_band_high, issue_size, lot_size,
        fresh_issue, ofs_size, status, listing_exchange, listing_date,
        gmp, gmp_pct,
        subscription_qib, subscription_nii, subscription_retail, subscription_total,
        anchor_allotment, sector, source,
        score_recommendation, score_conviction, score_reason,
        updated_at
      FROM ipo_live
      WHERE (${status} = '' OR status = ${status})
      ORDER BY
        CASE status
          WHEN 'OPEN'     THEN 1
          WHEN 'UPCOMING' THEN 2
          WHEN 'CLOSED'   THEN 3
          ELSE 4
        END,
        updated_at DESC
      LIMIT ${limit}
    `.catch(() => [])

    if (dbIpos.length > 0) {
      // Score each IPO using our scoring engine
      const scored = dbIpos.map((ipo: any) => {
        const scoreResult = scoreIpo({
          name:           ipo.name,
          priceBandLow:   ipo.price_band_low,
          priceBandHigh:  ipo.price_band_high,
          issueSize:      ipo.issue_size,
          freshIssue:     ipo.fresh_issue,
          gmpPrice:       ipo.gmp,
          openDate:       ipo.open_date,
          closeDate:      ipo.close_date,
          status:         ipo.status,
          sector:         ipo.sector,
          subscriptionX:  ipo.subscription_total,
        })
        return {
          ...ipo,
          id:     String(ipo.id),
          score:  ipo.score_recommendation
            ? { recommendation: ipo.score_recommendation, listingScore: ipo.score_conviction, reason: ipo.score_reason }
            : scoreResult,
        }
      })

      return NextResponse.json({ success: true, ipos: scored, source: "db", count: scored.length })
    }

    // Fallback to static pipeline
    const staticIpos = getIpoPipeline()
    const scored = staticIpos.map((ipo: any) => ({
      ...ipo,
      score: scoreIpo(ipo),
    }))

    return NextResponse.json({ success: true, ipos: scored, source: "static", count: scored.length })

  } catch (error: unknown) {
    // Final fallback — never crash IPO page
    try {
      const staticIpos = getIpoPipeline()
      return NextResponse.json({
        success: true,
        ipos: staticIpos.map((ipo: any) => ({ ...ipo, score: scoreIpo(ipo) })),
        source: "static_fallback",
      })
    } catch {
      return NextResponse.json({ success: false, ipos: [], error: String(error) })
    }
  }
}
