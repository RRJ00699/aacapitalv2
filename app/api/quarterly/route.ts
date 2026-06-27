import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

//  /api/quarterly
// Serves quarterly P&L from quarterly_financials (loaded by import_screener_quarters.py from the
// Screener Data Sheet "Quarters" section). Per-quarter sales / operating profit / OPM% / net profit,
// with YoY (vs the same quarter a year earlier) and QoQ growth computed here. Research/context, not
// a buy call. ?symbol=RELIANCE [&limit=12]

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}
const growth = (cur: number | null, prev: number | null): number | null => {
  if (cur === null || prev === null || prev === 0) return null
  return ((cur - prev) / Math.abs(prev)) * 100
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()
    if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })
    const limit = Math.min(20, Math.max(1, Number(req.nextUrl.searchParams.get("limit") || 12) || 12))

    const rows = await sql`
      SELECT period, fiscal_label, sales, operating_profit, opm_pct, net_profit
      FROM quarterly_financials
      WHERE symbol = ${symbol}
      ORDER BY period ASC`

    if (!rows.length) return NextResponse.json({ symbol, quarters: [] },
      { headers: { "Cache-Control": "public, max-age=3600" } })

    // index by YYYY-MM so YoY can find the same quarter a year earlier regardless of gaps
    const byLabel = new Map<string, any>()
    for (const r of rows) byLabel.set(r.fiscal_label, r)

    const all = rows.map((r: any) => {
      const [y, m] = String(r.fiscal_label).split("-")
      const yoyKey = `${Number(y) - 1}-${m}`
      const prevYear = byLabel.get(yoyKey)
      return {
        period: r.period,
        label: r.fiscal_label,
        sales: num(r.sales),
        operating_profit: num(r.operating_profit),
        opm_pct: num(r.opm_pct),
        net_profit: num(r.net_profit),
        sales_yoy: growth(num(r.sales), prevYear ? num(prevYear.sales) : null),
        np_yoy: growth(num(r.net_profit), prevYear ? num(prevYear.net_profit) : null),
      }
    })

    // QoQ on the trailing slice (sequential), then return most-recent-first
    const recent = all.slice(-limit)
    for (let i = 1; i < recent.length; i++) {
      ;(recent[i] as any).np_qoq = growth(recent[i].net_profit, recent[i - 1].net_profit)
    }
    recent.reverse()

    return NextResponse.json({ symbol, quarters: recent },
      { headers: { "Cache-Control": "public, max-age=3600" } })
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "failed" }, { status: 500 })
  }
}
