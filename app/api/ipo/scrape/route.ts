import { NextRequest, NextResponse } from "next/server"
import { IPO_PIPELINE } from "@/lib/ipo/pipeline"
import { scrapeIpoData } from "@/lib/scrapers/index"

export const maxDuration = 30

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))
    const { name } = body

    const targets = name
      ? IPO_PIPELINE.filter(i => i.name.toLowerCase().includes((name as string).toLowerCase()))
      : IPO_PIPELINE.filter(i => i.status === "OPEN" || i.status === "UPCOMING")

    if (targets.length === 0) {
      return NextResponse.json({ ok: false, error: "No matching IPOs found" }, { status: 404 })
    }

    // Scrape one at a time to respect rate limits
    const results = []
    for (const ipo of targets.slice(0, 3)) { // max 3 at once
      const scraped = await scrapeIpoData(ipo.name, ipo)
      // Convert ScrapedField objects to flat values for UI consumption
      results.push({
        name: scraped.name,
        qibX:       scraped.qibX.value,
        niiX:       scraped.niiX.value,
        retailX:    scraped.retailX.value,
        totalX:     scraped.totalX.value,
        gmpPrice:   scraped.gmpLatest.value,
        gmpMin:     scraped.gmpMin.value,
        gmpMax:     scraped.gmpMax.value,
        gmpTrend:   scraped.gmpTrend,
        anchors:    scraped.anchors.value,
        dataQuality: scraped.dataQuality,
        missingFields: scraped.missingFields,
        sourceAudit: scraped.sourceAudit,
        confidence: {
          gmp:          scraped.gmpLatest.confidence,
          subscription: scraped.qibX.confidence,
          anchors:      scraped.anchors.confidence,
        }
      })
    }

    return NextResponse.json({ ok: true, results, count: results.length })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
