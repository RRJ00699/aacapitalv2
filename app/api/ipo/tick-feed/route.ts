import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"
import { getCloudflareContext } from "@opennextjs/cloudflare"

export const dynamic = "force-dynamic"

// Live latest-tick lives in KV (ticker writes it every few seconds via
// /api/admin/kv-put) so the listing-day live view never wakes Neon. History
// (the series) still comes from Neon, but only when the chart is expanded.
function liveKV() {
  try {
    return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null> } }).CACHE ?? null
  } catch { return null }
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim()
  const limit = Math.min(360, Math.max(1, parseInt(searchParams.get("limit") || "150", 10)))
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  // Live-only fast path: ?live=1 returns the KV snapshot, ZERO Neon.
  const wantLiveOnly = new URL(req.url).searchParams.get("live") === "1"
  const kv = liveKV()
  let kvLatest: unknown = null
  if (kv) {
    try {
      const hit = await kv.get(`live:tick:${symbol}`)
      if (hit) kvLatest = JSON.parse(hit)
    } catch { /* KV miss -> fall to Neon */ }
  }
  if (wantLiveOnly) {
    return NextResponse.json({ symbol, latest: kvLatest, series: [], count: 0, source: kvLatest ? "kv" : "empty" })
  }

  try {
    const rows = await sql`
      SELECT ltp, vwap, vwap_dist, obir, day_volume, momentum, divergence, signal, recorded_at
      FROM ipo_tick_feed
      WHERE symbol = ${symbol}
      ORDER BY recorded_at DESC
      LIMIT ${limit}
    `.catch(() => [] as any[])

    const series = (rows as any[]).slice().reverse() // chronological
    const dbLatest = series.length ? series[series.length - 1] : null
    return NextResponse.json({ symbol, latest: kvLatest ?? dbLatest, series, count: series.length, source: kvLatest ? "kv+db" : "db" })
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e), symbol, series: [], latest: null }, { status: 500 })
  }
}
