import { NextResponse } from "next/server"
import { d1First } from "@/lib/d1"
import { getCloudflareContext } from "@opennextjs/cloudflare"

export const dynamic = "force-dynamic"

const CACHE_KEY = "market-snapshot:v2"
const CACHE_TTL_S = 300
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null }
  catch { return null }
}

const n = (v: unknown, f: number | null = null) => { const x = Number(v); return Number.isFinite(x) ? x : f }

export async function GET() {
  const kv = await getKV()
  if (kv) {
    try {
      const cached = await kv.get(CACHE_KEY)
      if (cached) return new NextResponse(cached, { headers: { "content-type": "application/json", "x-cache": "HIT" } })
    } catch { /* miss */ }
  }

  const ctx = await d1First<{
    d: string; regime: string | null; vix_close: string | null; breadth_pct: string | null;
    advances: number | null; declines: number | null; pcr: string | null;
  }>(`SELECT d,regime,vix_close,breadth_pct,advances,declines,pcr FROM market_context_daily ORDER BY d DESC LIMIT 1`)

  let liveNifty = 0, liveBankNifty = 0, liveVix = 0
  try {
    const [nRes, bRes, vRes] = await Promise.all([
      fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d", { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(4000) }).then(r=>r.json()).catch(()=>null),
      fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEBANK?interval=1d&range=1d", { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(4000) }).then(r=>r.json()).catch(()=>null),
      fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?interval=1d&range=1d", { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(4000) }).then(r=>r.json()).catch(()=>null),
    ])
    const price = (d: any) => d?.chart?.result?.[0]?.meta?.regularMarketPrice ?? 0
    liveNifty = price(nRes); liveBankNifty = price(bRes); liveVix = price(vRes)
  } catch {}

  const regimeName = ctx?.regime ?? "NORMAL"
  const payloadOut = JSON.stringify({
    ok: true,
    data: {
      regime: regimeName,
      market_regime: regimeName,
      nifty_price: liveNifty || null,
      nifty_change_pct: null,
      sensex_price: null,
      sensex_change_pct: null,
      banknifty_price: liveBankNifty || null,
      banknifty_change_pct: null,
      nifty_ema200: null,
      breadth_pct: n(ctx?.breadth_pct),
      advances: ctx?.advances ?? null,
      declines: ctx?.declines ?? null,
      deploy_min: regimeName === "BEARISH" ? 10 : 50,
      deploy_max: regimeName === "BEARISH" ? 30 : 70,
      vix: liveVix || n(ctx?.vix_close),
      pcr: n(ctx?.pcr),
      fii_flow: null,
      dii_flow: null,
      last_updated: ctx?.d ?? null,
    }
  })
  if (kv) { try { await kv.put(CACHE_KEY, payloadOut, { expirationTtl: CACHE_TTL_S }) } catch {} }
  return new NextResponse(payloadOut, { headers: { "content-type": "application/json", "x-cache": "MISS" } })
}
