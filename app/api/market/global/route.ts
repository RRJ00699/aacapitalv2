// app/api/market/global/route.ts
// Global markets + India snapshot for Today screen
// Yahoo Finance with Neon cache fallback when blocked on Vercel

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"
import { getBroker } from "@/lib/brokers"

export const dynamic = "force-dynamic"

const YF_BASES = [
  "https://query1.finance.yahoo.com",
  "https://query2.finance.yahoo.com",
]
const YF_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
  "Accept": "application/json,text/plain,*/*",
  "Referer": "https://finance.yahoo.com",
}

const SYMBOLS = [
  "^GSPC","^NDX","^DJI","^RUT",
  "DX-Y.NYB","USDINR=X",
  "GC=F","SI=F","CL=F","NG=F","HG=F",
  "BTC-USD","ETH-USD",
  "^N225","^HSI","000001.SS","^KS11",
  "^FTSE","^GDAXI","^FCHI",
]

const META: Record<string, { label: string; region: string; flag: string }> = {
  "^GSPC":     { label:"S&P 500",    region:"us",        flag:"🇺🇸" },
  "^NDX":      { label:"Nasdaq 100", region:"us",        flag:"🇺🇸" },
  "^DJI":      { label:"Dow Jones",  region:"us",        flag:"🇺🇸" },
  "^RUT":      { label:"Russell 2K", region:"us",        flag:"🇺🇸" },
  "DX-Y.NYB":  { label:"DXY",        region:"fx",        flag:"💵" },
  "USDINR=X":  { label:"USD/INR",    region:"fx",        flag:"₹"  },
  "GC=F":      { label:"Gold",       region:"commodity", flag:"🥇" },
  "SI=F":      { label:"Silver",     region:"commodity", flag:"🥈" },
  "CL=F":      { label:"Crude Oil",  region:"commodity", flag:"🛢" },
  "NG=F":      { label:"Nat Gas",    region:"commodity", flag:"🔥" },
  "HG=F":      { label:"Copper",     region:"commodity", flag:"🔶" },
  "BTC-USD":   { label:"Bitcoin",    region:"crypto",    flag:"₿"  },
  "ETH-USD":   { label:"Ethereum",   region:"crypto",    flag:"Ξ"  },
  "^N225":     { label:"Nikkei 225", region:"asia",      flag:"🇯🇵" },
  "^HSI":      { label:"Hang Seng",  region:"asia",      flag:"🇭🇰" },
  "000001.SS": { label:"Shanghai",   region:"asia",      flag:"🇨🇳" },
  "^KS11":     { label:"KOSPI",      region:"asia",      flag:"🇰🇷" },
  "^FTSE":     { label:"FTSE 100",   region:"europe",    flag:"🇬🇧" },
  "^GDAXI":    { label:"DAX",        region:"europe",    flag:"🇩🇪" },
  "^FCHI":     { label:"CAC 40",     region:"europe",    flag:"🇫🇷" },
}

const toNum = (v: any) => { const n = Number(v); return Number.isFinite(n) ? n : null }
const first = (...vals: any[]) => vals.find(v => v !== null && v !== undefined && v !== "") ?? null
const db = () => neon(process.env.DATABASE_URL!)

async function fetchYahoo(): Promise<Record<string, any>> {
  const global: Record<string, any> = {}
  for (const base of YF_BASES) {
    try {
      const res = await fetch(
        `${base}/v7/finance/quote?symbols=${encodeURIComponent(SYMBOLS.join(","))}`,
        { headers: YF_HEADERS, cache: "no-store", signal: AbortSignal.timeout(6000) }
      )
      if (!res.ok) continue
      const data = await res.json()
      for (const q of data?.quoteResponse?.result || []) {
        const meta = META[q.symbol]
        if (!meta) continue
        global[q.symbol] = {
          ...meta, symbol: q.symbol,
          price:     toNum(q.regularMarketPrice),
          change:    toNum(q.regularMarketChange),
          changePct: toNum(q.regularMarketChangePercent),
          time:      q.regularMarketTime ?? null,
        }
      }
      if (Object.keys(global).length > 3) break
    } catch {}
  }
  return global
}

export async function GET() {
  try {
    const sql = db()

    const [yahooRes, snapshotRows, regimeRows, flowRows, indiaLive] = await Promise.allSettled([
      fetchYahoo(),
      sql`SELECT * FROM market_snapshot WHERE id = 1 LIMIT 1`.catch(() => []),
      sql`SELECT * FROM market_regimes ORDER BY evaluation_date DESC LIMIT 1`.catch(() => []),
      sql`SELECT * FROM daily_institutional_flows ORDER BY trade_date DESC LIMIT 1`.catch(() => []),
      (async () => {
        try {
          const broker = getBroker()
          if (!(await broker.isConnected())) return null
          return await (broker as any).getQuotes(["NSE:NIFTY 50","NSE:NIFTY BANK","NSE:INDIA VIX"])
        } catch { return null }
      })(),
    ])

    // Process Yahoo — with Neon cache fallback
    const global: Record<string, any> = yahooRes.status === "fulfilled" ? yahooRes.value : {}

    const gotYahoo = Object.keys(global).length > 3
    if (gotYahoo) {
      // Cache fresh data for after-hours use
      sql`
        INSERT INTO platform_config (key, value, updated_at)
        VALUES ('global_cache', ${JSON.stringify(global)}, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
      `.catch(() => {})
    } else {
      // Yahoo blocked — load from cache
      try {
        const cached = await sql`SELECT value, updated_at FROM platform_config WHERE key = 'global_cache' LIMIT 1`
        if (cached.length) Object.assign(global, JSON.parse(cached[0].value as string))
      } catch {}
    }

    const snap = snapshotRows.status === "fulfilled" ? ((snapshotRows.value as any[])[0] ?? {}) : {}
    const reg  = regimeRows.status  === "fulfilled" ? ((regimeRows.value  as any[])[0] ?? {}) : {}
    const flow = flowRows.status    === "fulfilled" ? ((flowRows.value    as any[])[0] ?? {}) : {}
    const iq   = indiaLive.status   === "fulfilled" ? indiaLive.value : null

    const niftyLive = iq?.["NSE:NIFTY 50"]
    const bankLive  = iq?.["NSE:NIFTY BANK"]
    const vixLive   = iq?.["NSE:INDIA VIX"]

    const india = {
      nifty:        first(niftyLive?.lastPrice, snap.nifty_price, reg.nifty_close),
      niftyChg:     first(niftyLive?.changePct, snap.nifty_change_pct),
      bankNifty:    first(bankLive?.lastPrice,  snap.banknifty_price),
      bankNiftyChg: first(bankLive?.changePct,  snap.banknifty_change_pct),
      vix:          first(vixLive?.lastPrice,   snap.vix, snap.india_vix, reg.india_vix),
      pcr:          first(snap.pcr, snap.nifty_pcr),
      fii:          first(flow.fii_net, snap.fii_flow, snap.fii_cash_flow),
      dii:          first(flow.dii_net, snap.dii_flow, snap.dii_cash_flow),
      regime:       first(reg.active_regime, snap.market_regime, "NORMAL"),
      breadthPct:   first(reg.breadth_percentage, snap.breadth_pct),
      deployMin:    first(reg.recommended_allocation_min, snap.deploy_min),
      deployMax:    first(reg.recommended_allocation_max, snap.deploy_max),
      sectors:      snap.sector_data_json ? JSON.parse(snap.sector_data_json) : {},
      source:       iq ? "zerodha_live" : gotYahoo ? "yahoo_fresh" : "neon_cache",
    }

    const avg = (keys: string[]) => {
      const vals = keys.map(k => global[k]?.changePct).filter((v: any) => typeof v === "number")
      return vals.length ? vals.reduce((a: number, b: number) => a + b, 0) / vals.length : 0
    }
    const usAvg   = avg(["^GSPC","^NDX","^DJI"])
    const dxyChg  = global["DX-Y.NYB"]?.changePct ?? 0
    const goldChg = global["GC=F"]?.changePct ?? 0
    const btcChg  = global["BTC-USD"]?.changePct ?? 0
    const riskOff = usAvg < -0.5 && dxyChg > 0 && goldChg > 0
    const riskOn  = usAvg > 0.5  && btcChg > 0  && dxyChg < 0

    return NextResponse.json({
      ok: true,
      global,
      india,
      composite: {
        usAvg, asiaAvg: avg(["^N225","^HSI","000001.SS","^KS11"]),
        euroAvg: avg(["^FTSE","^GDAXI","^FCHI"]),
        capitalFlow: riskOff ? "Risk-Off → Bonds + Dollar" : riskOn ? "Risk-On → Equities + Crypto" : "Mixed",
        riskOffSignal: riskOff, riskOnSignal: riskOn,
        dataSource: gotYahoo ? "yahoo_live" : "neon_cache",
      },
      fetchedAt: new Date().toISOString(),
    })
  } catch (err: any) {
    console.error("Global market error:", err)
    return NextResponse.json({ ok: false, error: err?.message }, { status: 500 })
  }
}
