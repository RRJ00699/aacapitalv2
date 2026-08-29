import { NextRequest, NextResponse } from "next/server"
import { d1All } from "@/lib/d1"
import { getCloudflareContext } from "@opennextjs/cloudflare"

export const dynamic = "force-dynamic"

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

  const wantLiveOnly = searchParams.get("live") === "1"
  const kv = liveKV()
  let kvLatest: unknown = null
  if (kv) {
    try {
      const hit = await kv.get(`live:tick:${symbol}`)
      if (hit) kvLatest = JSON.parse(hit)
    } catch { /* miss */ }
  }
  if (wantLiveOnly) {
    return NextResponse.json({ symbol, latest: kvLatest, series: [], count: 0, source: kvLatest ? "kv" : "empty" })
  }

  try {
    const rows = await d1All<{
      ltp: number | null; day_volume: number | null; recorded_at: string;
    }>(`
      SELECT CAST(m.close_rs AS REAL) AS ltp,
             m.volume_shares AS day_volume,
             m.ts AS recorded_at
      FROM market_bars m
      JOIN ipo i ON i.id=m.ipo_id
      WHERE UPPER(i.nse_symbol)=? AND m.interval='5m'
      ORDER BY m.ts DESC
      LIMIT ?
    `, [symbol, limit])

    const series = rows.slice().reverse().map(r => ({
      ...r,
      vwap: null,
      vwap_dist: null,
      obir: null,
      momentum: null,
      divergence: null,
      signal: null,
    }))
    const d1Latest = series.length ? series[series.length - 1] : null
    return NextResponse.json({
      symbol,
      latest: kvLatest ?? d1Latest,
      series,
      count: series.length,
      source: kvLatest ? "kv+d1_5m" : "d1_5m",
    })
  } catch (e: unknown) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "query failed", symbol, series: [], latest: kvLatest }, { status: 500 })
  }
}
