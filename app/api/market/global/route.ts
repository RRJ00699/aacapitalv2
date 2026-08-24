// app/api/market/global/route.ts
// Global markets from Yahoo + live India quotes from Zerodha.
// D1 supplies only compact persisted market context. No Neon fallback.

import { NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"
import { cached } from "@/lib/kv-cache"
import { d1First } from "@/lib/d1"

const YF = "https://query1.finance.yahoo.com"
const YF_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "Accept": "application/json",
}

const SYMBOLS = [
  "^NSEI","^NSEBANK","^INDIAVIX",
  "^GSPC","^NDX","^DJI","^RUT",
  "DX-Y.NYB","USDINR=X",
  "GC=F","SI=F","CL=F","NG=F","HG=F",
  "BTC-USD","ETH-USD",
  "^N225","^HSI","000001.SS","^KS11",
  "^FTSE","^GDAXI","^FCHI",
]

const META: Record<string, { label: string; region: string; flag: string }> = {
  "^GSPC": { label: "S&P 500", region: "us", flag: "🇺🇸" },
  "^NDX": { label: "Nasdaq 100", region: "us", flag: "🇺🇸" },
  "^DJI": { label: "Dow Jones", region: "us", flag: "🇺🇸" },
  "^RUT": { label: "Russell 2K", region: "us", flag: "🇺🇸" },
  "DX-Y.NYB": { label: "DXY", region: "fx", flag: "💵" },
  "USDINR=X": { label: "USD/INR", region: "fx", flag: "₹" },
  "GC=F": { label: "Gold", region: "commodity", flag: "🥇" },
  "SI=F": { label: "Silver", region: "commodity", flag: "🥈" },
  "CL=F": { label: "Crude Oil", region: "commodity", flag: "🛢" },
  "NG=F": { label: "Nat Gas", region: "commodity", flag: "🔥" },
  "HG=F": { label: "Copper", region: "commodity", flag: "🔶" },
  "BTC-USD": { label: "Bitcoin", region: "crypto", flag: "₿" },
  "ETH-USD": { label: "Ethereum", region: "crypto", flag: "Ξ" },
  "^N225": { label: "Nikkei 225", region: "asia", flag: "🇯🇵" },
  "^HSI": { label: "Hang Seng", region: "asia", flag: "🇭🇰" },
  "000001.SS": { label: "Shanghai", region: "asia", flag: "🇨🇳" },
  "^KS11": { label: "KOSPI", region: "asia", flag: "🇰🇷" },
  "^FTSE": { label: "FTSE 100", region: "europe", flag: "🇬🇧" },
  "^GDAXI": { label: "DAX", region: "europe", flag: "🇩🇪" },
  "^FCHI": { label: "CAC 40", region: "europe", flag: "🇫🇷" },
}

export async function GET() {
  try {
    const body = await cached("market:global:v3", async () => {
      const [yahooRes, indiaLive, context] = await Promise.allSettled([
        Promise.all(SYMBOLS.map(sym =>
          fetch(`${YF}/v8/finance/chart/${encodeURIComponent(sym)}?range=1d&interval=15m`,
                { headers: YF_HEADERS, next: { revalidate: 300 } })
            .then(r => r.json())
            .then(j => {
              const m = j?.chart?.result?.[0]?.meta
              if (!m?.regularMarketPrice) return null
              const prev = m.chartPreviousClose || m.previousClose || null
              return {
                symbol: sym,
                regularMarketPrice: m.regularMarketPrice,
                regularMarketChange: prev ? m.regularMarketPrice - prev : null,
                regularMarketChangePercent: prev ? ((m.regularMarketPrice - prev) / prev) * 100 : null,
              }
            }).catch(() => null))
        ).then(rows => rows.filter(Boolean)),
        (async () => {
          try {
            const broker = getBroker()
            if (!(await broker.isConnected())) return null
            return await (broker as any).getQuotes(["NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:INDIA VIX"])
          } catch { return null }
        })(),
        d1First<any>(`SELECT d, regime, vix_close, breadth_pct, advances, declines, pcr
                      FROM market_context_daily ORDER BY d DESC LIMIT 1`),
      ])

      const global: Record<string, any> = {}
      if (yahooRes.status === "fulfilled") {
        for (const q of yahooRes.value as any[]) {
          const m = META[q.symbol]
          if (!m) continue
          global[q.symbol] = {
            ...m,
            symbol: q.symbol,
            price: q.regularMarketPrice,
            change: q.regularMarketChange == null ? null : +q.regularMarketChange.toFixed(2),
            changePct: q.regularMarketChangePercent == null ? null : +q.regularMarketChangePercent.toFixed(2),
          }
        }
      }

      const iq = indiaLive.status === "fulfilled" ? indiaLive.value : null
      const ctx = context.status === "fulfilled" ? context.value : null
      const india = {
        nifty: iq?.["NSE:NIFTY 50"]?.lastPrice ?? global["^NSEI"]?.price ?? null,
        niftyChg: iq?.["NSE:NIFTY 50"]?.changePct ?? global["^NSEI"]?.changePct ?? null,
        bankNifty: iq?.["NSE:NIFTY BANK"]?.lastPrice ?? global["^NSEBANK"]?.price ?? null,
        bankNiftyChg: iq?.["NSE:NIFTY BANK"]?.changePct ?? global["^NSEBANK"]?.changePct ?? null,
        vix: iq?.["NSE:INDIA VIX"]?.lastPrice ?? global["^INDIAVIX"]?.price ?? ctx?.vix_close ?? null,
        pcr: ctx?.pcr ?? null,
        fii: null,
        dii: null,
        regime: ctx?.regime ?? null,
        breadth: ctx?.breadth_pct ?? null,
        advances: ctx?.advances ?? null,
        declines: ctx?.declines ?? null,
        source: iq ? "zerodha_live+d1_context" : "yahoo+d1_context",
      }

      const avg = (keys: string[]) => keys.reduce((s, k) => s + (global[k]?.changePct ?? 0), 0) / keys.length
      const usAvg = avg(["^GSPC","^NDX","^DJI"])
      const asiaAvg = avg(["^N225","^HSI","000001.SS","^KS11"])
      const euroAvg = avg(["^FTSE","^GDAXI","^FCHI"])
      const btcChg = global["BTC-USD"]?.changePct ?? 0
      const dxyChg = global["DX-Y.NYB"]?.changePct ?? 0
      const goldChg = global["GC=F"]?.changePct ?? 0
      const riskOffSignal = usAvg < -0.5 && dxyChg > 0 && goldChg > 0
      const riskOnSignal = usAvg > 0.5 && btcChg > 0 && dxyChg < 0
      const capitalFlow = riskOffSignal ? "Risk-Off → Bonds + Dollar"
        : riskOnSignal ? "Risk-On → Equities + Crypto"
        : "Mixed — no clear directional signal"

      return JSON.stringify({
        as_of: new Date().toISOString(),
        ok: true,
        global,
        india,
        composite: { usAvg, asiaAvg, euroAvg, capitalFlow, riskOffSignal, riskOnSignal },
        fetchedAt: new Date().toISOString(),
      })
    }, 300)

    return new NextResponse(body, { headers: { "content-type": "application/json" } })
  } catch (err: any) {
    console.error("Global market error:", err)
    return NextResponse.json({ ok: false, global: {}, india: {}, error: err.message }, { status: 200 })
  }
}
