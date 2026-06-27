import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

//  /api/valuation
// Serves the Valuation Lens (valuation table, computed by _scripts/compute_valuation.py):
// today's P/E and P/B placed as a PERCENTILE within the stock's own ~10yr history (point-in-time,
// no look-ahead). The "are you overpaying?" complement to DNA's "is it a good business?".
// Research/context, NOT a buy call.  ?symbol=RELIANCE

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()
    if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

    const rows = await sql`
      SELECT symbol, current_price, current_pe, ttm_pe, current_pb,
             pe_min, pe_median, pe_max, pe_percentile, pb_median, pb_percentile,
             verdict, years, n_obs
      FROM valuation WHERE symbol = ${symbol} LIMIT 1`

    if (!rows.length) return NextResponse.json({ symbol, available: false },
      { headers: { "Cache-Control": "public, max-age=3600" } })

    const r: any = rows[0]
    return NextResponse.json({
      symbol: r.symbol, available: true,
      current_price: num(r.current_price), current_pe: num(r.current_pe), ttm_pe: num(r.ttm_pe),
      current_pb: num(r.current_pb), pe_min: num(r.pe_min), pe_median: num(r.pe_median),
      pe_max: num(r.pe_max), pe_percentile: num(r.pe_percentile), pb_median: num(r.pb_median),
      pb_percentile: num(r.pb_percentile), verdict: r.verdict || null,
      years: num(r.years), n_obs: num(r.n_obs),
    }, { headers: { "Cache-Control": "public, max-age=3600" } })
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "failed" }, { status: 500 })
  }
}
