// app/api/ipo/post-listing/route.ts
// Capital-protection panel data for recently-listed IPOs.
// Token-independent: "current price" is derived from issue_price x (1 + latest populated
// return) so it works without a live Kite token, and refreshes as the daily returns
// backfill (fetch_ipo_post_listing_returns.py) fills return_day7/15/30. If you later want
// true real-time, layer a Kite quote on top of `currentPrice` (see listing-day/route.ts).

import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

const num = (v: unknown): number | null => {
  const x = parseFloat(String(v))
  return Number.isFinite(x) ? x : null
}
const round2 = (v: number | null) => (v === null ? null : Math.round(v * 100) / 100)

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const days = Math.min(120, Math.max(1, parseInt(searchParams.get("days") || "45", 10)))

    const rows = await sql`
      SELECT company_name, nse_symbol, symbol, issue_price, listing_open, listing_date,
             listing_day_close, return_listing_open, return_day7, return_day30,
             max_drawdown_30d, max_upside_30d, qib_subscription_x AS qib_x
      FROM ipo_intelligence
      WHERE listing_date IS NOT NULL
        AND listing_date >= (CURRENT_DATE - ${days}::int)
        AND listing_date <= CURRENT_DATE
      ORDER BY listing_date DESC
      LIMIT 50
    `.catch(() => [] as any[])

    const ipos = (rows as any[]).map((r) => {
      const issue = num(r.issue_price)
      // most-recent populated return → latest known price (0 is a valid return, keep it)
      const latestRet = [r.return_day30, r.return_day7, r.return_listing_open]
        .map(num)
        .find((v) => v != null)
      const derived =
        issue != null && latestRet != null ? issue * (1 + latestRet / 100) : null
      const currentPrice = derived ?? num(r.listing_day_close)

      const openRet = num(r.return_listing_open)
      const openPrice =
        num(r.listing_open) ??
        (issue != null && openRet != null ? issue * (1 + openRet / 100) : null)

      // ── Recovery signal (encodes backtest_strategies.py findings) ──
      const d7 = num(r.return_day7)
      const qib = num(r.qib_x)
      const ld = r.listing_date ? new Date(r.listing_date) : null
      const age = ld ? Math.floor((Date.now() - ld.getTime()) / 86_400_000) : null
      const strongQib = qib != null && qib >= 2
      let signal: { tier: string; tone: string; label: string; detail: string }
      if (openRet != null && openRet > 0) {
        signal = { tier: "NO EDGE", tone: "gray", label: "Premium listing — no buy edge",
          detail: "Chasing strong listers historically loses (avg −2.5%, PF 0.72)." }
      } else if ((openRet != null && openRet <= -10) || !strongQib) {
        signal = { tier: "AVOID", tone: "red", label: "Deep discount or weak QIB — catastrophe-tail zone",
          detail: "Where LIC / Paytm / Glottis sit. Protect capital; do not deploy fresh." }
      } else if (d7 != null && d7 >= 0) {
        signal = { tier: "CONFIRMED RECLAIM", tone: "amber", label: "Reclaimed issue by day 7 — strength, but edge has decayed",
          detail: "This pattern paid +12–14% in 2022–23 but was FLAT in 2024–25 (the edge compressed). Confirmation of strength, not a green-light trade." }
      } else if (age != null && age < 7) {
        signal = { tier: "WATCH", tone: "amber", label: "Discount + strong QIB — awaiting reclaim",
          detail: "Positive in 5 of 6 years but on tiny samples (n~7–21/yr, +4% avg, high variance). Watch the reclaim; do not size up." }
      } else {
        signal = { tier: "UNCONFIRMED", tone: "gray", label: "Below issue at day 7 — not confirmed",
          detail: "Most names still under at day 7 stay underwater. No confirmed entry." }
      }

      return {
        id: r.nse_symbol || r.symbol || r.company_name,
        name: r.company_name,
        symbol: r.nse_symbol || r.symbol || "",
        status: "LISTED",
        issuePrice: issue,
        currentPrice: round2(currentPrice),
        openPrice: round2(openPrice),
        listingDate: r.listing_date,
        openPct: openRet,
        day7Pct: d7,
        qib: qib,
        daysSinceListing: age,
        signal,
      }
    })

    return NextResponse.json({ success: true, ipos, source: "ipo_intelligence" })
  } catch (error: unknown) {
    return NextResponse.json({ success: false, ipos: [], error: String(error) })
  }
}
