import { NextRequest, NextResponse } from "next/server"
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
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  // Live-only fast path: ?live=1 returns the KV snapshot, ZERO Neon.
  const wantLiveOnly = new URL(req.url).searchParams.get("live") === "1"
  const kv = liveKV()
  let kvLatest: unknown = null
  if (kv) {
    try {
      const hit = await kv.get(`live:tick:${symbol}`)
      if (hit) kvLatest = JSON.parse(hit)
    } catch { /* controlled empty state below */ }
  }
  if (wantLiveOnly) {
    return NextResponse.json({ symbol, latest: kvLatest, series: [], count: 0, source: kvLatest ? "kv" : "empty" })
  }

  return NextResponse.json({ symbol, latest: kvLatest, series: [], count: 0, unavailable: true, reason: "historical_snapshot_unavailable", source: kvLatest ? "kv" : "empty" }, { status: 503, headers: { "retry-after": "300" } })
}
