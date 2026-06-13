// app/api/ipo/route.ts
import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"
import { IPO_PIPELINE, getIposByStatus } from "@/lib/ipo/pipeline"
import { calcScore } from "@/lib/ipo/scoring"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const status = searchParams.get("status") || ""
    const limit  = Math.min(50, parseInt(searchParams.get("limit") || "20"))

    const dbIpos = await sql`
      SELECT id, name, symbol, open_date, close_date,
        price_band_low, price_band_high, issue_size, lot_size,
        fresh_issue, ofs_size, status, listing_exchange, listing_date,
        gmp, subscription_qib, subscription_nii,
        subscription_retail, subscription_total,
        sector, source, score_recommendation, score_conviction, updated_at
      FROM ipo_live
      WHERE (${status} = '' OR status = ${status})
      ORDER BY CASE status
        WHEN 'OPEN'     THEN 1
        WHEN 'UPCOMING' THEN 2
        WHEN 'CLOSED'   THEN 3
        ELSE 4 END, updated_at DESC
      LIMIT ${limit}
    `.catch(() => [])

    if (dbIpos.length > 0) {
      const scored = dbIpos.map((ipo: any) => {
        // Map DB columns to exact IpoData interface fields
        const ipoData = {
          name:           ipo.name         || "",
          sector:         ipo.sector       || "",
          issueSize:      Number(ipo.issue_size      || 0),
          freshIssuePct:  Number(ipo.fresh_issue     || 0),
          ofsPct:         Number(ipo.ofs_size        || 0),
          priceBandLow:   Number(ipo.price_band_low  || 0),
          priceBandHigh:  Number(ipo.price_band_high || 0),
          lotSize:        Number(ipo.lot_size        || 0),
          gmpPrice:       Number(ipo.gmp             || 0),
          retailX:        Number(ipo.subscription_retail || 0),
          niiX:           Number(ipo.subscription_nii    || 0),
          qibX:           Number(ipo.subscription_qib    || 0),
          totalX:         Number(ipo.subscription_total  || 0),
          status:         ipo.status       || "UPCOMING",
          listingDate:    ipo.listing_date || "",
          anchors:        [] as string[],
        }
        return {
          ...ipo,
          id: String(ipo.id),
          priceBandLow:  ipoData.priceBandLow,
          priceBandHigh: ipoData.priceBandHigh,
          score: ipo.score_recommendation
            ? { recommendation: ipo.score_recommendation, listingScore: ipo.score_conviction }
            : calcScore(ipoData),
        }
      })
      return NextResponse.json({ success: true, ipos: scored, source: "db" })
    }

    // Static fallback
    const staticIpos = status
      ? getIposByStatus(status as "UPCOMING" | "OPEN" | "LISTED")
      : IPO_PIPELINE.slice(0, limit)
    return NextResponse.json({
      success: true,
      ipos: staticIpos.map((ipo: any) => ({ ...ipo, score: calcScore(ipo) })),
      source: "static",
    })

  } catch (error: unknown) {
    try {
      return NextResponse.json({
        success: true,
        ipos: IPO_PIPELINE.slice(0, 20).map((ipo: any) => ({ ...ipo, score: calcScore(ipo) })),
        source: "static_fallback",
      })
    } catch {
      return NextResponse.json({ success: false, ipos: [], error: String(error) })
    }
  }
}
