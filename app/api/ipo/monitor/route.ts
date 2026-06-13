import { NextRequest, NextResponse } from "next/server"
import { HISTORICAL_IPOS } from "@/lib/ipo/historical"

export async function GET(req: NextRequest) {
  // Find IPOs that: listed weak BUT have strong quality scores
  // These are the "future Kaynes" type opportunities
  const opportunities = HISTORICAL_IPOS
    .filter(h => {
      const weakListing  = h.d1Return < 15         // listed weak or flat
      const strongBiz    = h.ipoScore >= 65         // strong business quality
      const recentEnough = h.year >= 2021           // recent enough to still be investable
      return weakListing && strongBiz && recentEnough
    })
    .map(h => ({
      name:           h.name,
      sector:         h.sector,
      year:           h.year,
      listingGain:    h.d1Return,
      ipoScore:       h.ipoScore,
      m1Return:       h.m1Return,
      m3Return:       h.m3Return,
      m6Return:       h.m6Return,
      m12Return:      h.m12Return,
      signal:         h.m6Return > 30 ? "BUY AFTER LISTING"
                    : h.m6Return > 10 ? "ACCUMULATE"
                    : "WATCHLIST",
      reason:         `Listed +${h.d1Return}% but quality score ${h.ipoScore}/100. `
                    + (h.m6Return > 30 ? `6M return: +${h.m6Return}% — classic late compounder.` : `Monitor for base formation.`)
    }))
    .sort((a,b) => b.m6Return - a.m6Return)
    .slice(0, 15)

  // GMP trend for active IPOs (placeholder — real data from scraper)
  const gmpTrends = {
    rising:    "GMP trending up — institutional accumulation signal",
    stable:    "GMP stable — base building",
    falling:   "GMP falling — caution",
    collapsing:"GMP collapsing — consider avoiding",
  }

  return NextResponse.json({
    ok: true,
    postListingOpportunities: opportunities,
    opportunityCount: opportunities.length,
    gmpTrendKey: gmpTrends,
  })
}
