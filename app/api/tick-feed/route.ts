import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim()
  const limit = Math.min(360, Math.max(1, parseInt(searchParams.get("limit") || "150", 10)))
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  try {
    const rows = await sql`
      SELECT ltp, vwap, vwap_dist, obir, day_volume, momentum, divergence, signal, recorded_at
      FROM ipo_tick_feed
      WHERE symbol = ${symbol}
      ORDER BY recorded_at DESC
      LIMIT ${limit}
    `.catch(() => [] as any[])

    const series = (rows as any[]).slice().reverse() // chronological
    const latest = series.length ? series[series.length - 1] : null
    return NextResponse.json({ symbol, latest, series, count: series.length })
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e), symbol, series: [], latest: null }, { status: 500 })
  }
}
