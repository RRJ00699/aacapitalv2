import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

// Daily floor/ceiling/verdict series for a symbol (listing day → +30d), newest last.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim()
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  try {
    const rows = await sql`
      SELECT trade_date, issue_price, listing_open, gap_pct, gap_bucket,
             day_open, day_high, day_low, day_close, session_vwap, close_vs_vwap,
             floor_price, floor_volume, floor_defenses, ceiling_price, ceiling_volume,
             poc_price, obir_open, obir_close, circuit_locked, verdict, risk_note,
             profile_json, tick_count, computed_at
      FROM ipo_level_analysis
      WHERE symbol = ${symbol}
      ORDER BY trade_date ASC
    `.catch(() => [] as any[])

    const series = rows as any[]
    const latest = series.length ? series[series.length - 1] : null
    return NextResponse.json({ symbol, latest, series, count: series.length })
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e), symbol, series: [], latest: null }, { status: 500 })
  }
}
