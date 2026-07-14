// app/api/broker/quote/route.ts
// Returns live quote: Zerodha (primary) → Yahoo Finance (fallback)
// Stock page uses this for live price display.
import { NextRequest, NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"
import { audit, clientIp } from "@/lib/security/audit"
import { getCloudflareContext } from "@opennextjs/cloudflare"

// KV cache for live quotes — the journey poll hits this every 60s. Caching the
// price ~30s per symbol means we don't hammer Zerodha/Yahoo (or Neon) on every
// poll, exactly like a real trading app throttles its price feed.
const QUOTE_TTL_S = 30
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null }
  catch { return null }
}

async function yahooQuote(sym: string) {
  // Try Yahoo Finance v8 chart for latest price
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${sym}.NS?interval=1d&range=5d`
  const r = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
    signal: AbortSignal.timeout(5000),
    next: { revalidate: 60 },      // cache 60s — not hammering Yahoo
  })
  if (!r.ok) throw new Error(`Yahoo ${r.status}`)
  const data = await r.json()
  const result = data?.chart?.result?.[0]
  if (!result) throw new Error("No Yahoo data")
  const meta   = result.meta
  const price  = meta.regularMarketPrice ?? meta.previousClose ?? 0
  const prev   = meta.chartPreviousClose ?? meta.previousClose ?? price
  const change = price - prev
  const changePct = prev > 0 ? (change / prev) * 100 : 0
  return {
    ok:          true,
    symbol:      sym,
    last_price:  price,
    change:      parseFloat(change.toFixed(2)),
    change_pct:  parseFloat(changePct.toFixed(2)),
    volume:      meta.regularMarketVolume ?? 0,
    day_high:    result.indicators?.quote?.[0]?.high?.at(-1) ?? price,
    day_low:     result.indicators?.quote?.[0]?.low?.at(-1)  ?? price,
    prev_close:  prev,
    source:      "yahoo",
  }
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const sym      = searchParams.get("sym")?.toUpperCase()
  const exchange = searchParams.get("exchange") || "NSE"

  if (!sym)
    return NextResponse.json({ error: "sym required" }, { status: 400 })

  const cacheKey = `quote:${exchange}:${sym}`
  const kv = await getKV()
  if (kv) {
    try {
      const hit = await kv.get(cacheKey)
      if (hit) return new NextResponse(hit, { headers: { "content-type": "application/json", "x-cache": "HIT" } })
    } catch { /* fall through to live fetch */ }
  }

  // Try Zerodha first
  try {
    const broker    = getBroker()
    const connected = await broker.isConnected()
    if (connected) {
      const quote = await broker.getQuote(sym, exchange)
      await audit("broker.quote.read", { ip: clientIp(req), detail: { sym, exchange } })
      const body = JSON.stringify({ ok: true, ...quote, source: "zerodha" })
      if (kv) { try { await kv.put(cacheKey, body, { expirationTtl: QUOTE_TTL_S }) } catch {} }
      return new NextResponse(body, { headers: { "content-type": "application/json", "x-cache": "MISS" } })
    }
  } catch { /* fall through */ }

  // Zerodha offline → Yahoo Finance fallback
  try {
    const quote = await yahooQuote(sym)
    const body = JSON.stringify(quote)
    if (kv) { try { await kv.put(cacheKey, body, { expirationTtl: QUOTE_TTL_S }) } catch {} }
    return new NextResponse(body, { headers: { "content-type": "application/json", "x-cache": "MISS" } })
  } catch (err: any) {
    return NextResponse.json(
      { error: "Price unavailable", sym, source: "none" },
      { status: 503 }
    )
  }
}
