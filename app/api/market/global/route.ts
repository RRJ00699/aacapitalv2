// app/api/market/global/route.ts
// Fetches all 20 global assets in ONE Yahoo Finance batch call.
// India data: Zerodha live quote (fixes 24,400 stale bug) with Neon snapshot fallback.

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"
import { getBroker } from "@/lib/brokers"

const YF = "https://query1.finance.yahoo.com"
const YF_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "Accept": "application/json",
}

// All global symbols — one batch call
const SYMBOLS = [
  "^GSPC","^NDX","^DJI","^RUT",           // US
  "DX-Y.NYB","USDINR=X",                  // FX
  "GC=F","SI=F","CL=F","NG=F","HG=F",    // Commodities
  "BTC-USD","ETH-USD",                     // Crypto
  "^N225","^HSI","000001.SS","^KS11",     // Asia
  "^FTSE","^GDAXI","^FCHI",              // Europe
]

const META: Record<string, { label: string; region: string; flag: string }> = {
  "^GSPC":     { label: "S&P 500",    region: "us",        flag: "🇺🇸" },
  "^NDX":      { label: "Nasdaq 100", region: "us",        flag: "🇺🇸" },
  "^DJI":      { label: "Dow Jones",  region: "us",        flag: "🇺🇸" },
  "^RUT":      { label: "Russell 2K", region: "us",        flag: "🇺🇸" },
  "DX-Y.NYB":  { label: "DXY",        region: "fx",        flag: "💵" },
  "USDINR=X":  { label: "USD/INR",    region: "fx",        flag: "₹" },
  "GC=F":      { label: "Gold",       region: "commodity", flag: "🥇" },
  "SI=F":      { label: "Silver",     region: "commodity", flag: "🥈" },
  "CL=F":      { label: "Crude Oil",  region: "commodity", flag: "🛢" },
  "NG=F":      { label: "Nat Gas",    region: "commodity", flag: "🔥" },
  "HG=F":      { label: "Copper",     region: "commodity", flag: "🔶" },
  "BTC-USD":   { label: "Bitcoin",    region: "crypto",    flag: "₿" },
  "ETH-USD":   { label: "Ethereum",   region: "crypto",    flag: "Ξ" },
  "^N225":     { label: "Nikkei 225", region: "asia",      flag: "🇯🇵" },
  "^HSI":      { label: "Hang Seng",  region: "asia",      flag: "🇭🇰" },
  "000001.SS": { label: "Shanghai",   region: "asia",      flag: "🇨🇳" },
  "^KS11":     { label: "KOSPI",      region: "asia",      flag: "🇰🇷" },
  "^FTSE":     { label: "FTSE 100",   region: "europe",    flag: "🇬🇧" },
  "^GDAXI":    { label: "DAX",        region: "europe",    flag: "🇩🇪" },
  "^FCHI":     { label: "CAC 40",     region: "europe",    flag: "🇫🇷" },
}

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET() {
  try {
    const [yahooRes, snapRows, indiaLive, flowRows] = await Promise.allSettled([
      // Single batch call — all 20 assets
      fetch(
        `${YF}/v7/finance/quote?symbols=${SYMBOLS.join(",")}`,
        { headers: YF_HEADERS, next: { revalidate: 60 } }
      ).then(r => r.json()),

      // Latest India snapshot from Neon
      db()`SELECT * FROM market_snapshot ORDER BY created_at DESC LIMIT 1`,
      // FII/DII from daily flows (most recent)
      db()`SELECT fii_net, dii_net, trade_date FROM daily_institutional_flows ORDER BY trade_date DESC LIMIT 1`.catch(() => []),

      // Live Nifty/BankNifty/VIX from Zerodha (most accurate)
      (async () => {
        try {
          const broker = getBroker()
          if (!(await broker.isConnected())) return null
          return await (broker as any).getQuotes([
            "NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:INDIA VIX",
          ])
        } catch { return null }
      })(),
    ])

    // ── Process Yahoo global quotes ───────────────────────────────────────────
    const global: Record<string, any> = {}
    if (yahooRes.status === "fulfilled") {
      for (const q of yahooRes.value?.quoteResponse?.result || []) {
        const m = META[q.symbol]
        if (!m) continue
        const pct = +(q.regularMarketChangePercent ?? 0).toFixed(2)
        global[q.symbol] = {
          ...m,
          symbol:    q.symbol,
          price:     q.regularMarketPrice,
          change:    +(q.regularMarketChange ?? 0).toFixed(2),
          changePct: pct,
        }
      }
    }

    // If Yahoo failed or returned empty, try Neon cache
    if (Object.keys(global).length < 3) {
      try {
        const cached = await db()`SELECT value FROM platform_config WHERE key = 'global_cache' LIMIT 1`
        if (cached.length && cached[0].value) {
          Object.assign(global, JSON.parse(cached[0].value as string))
        }
      } catch {}
    } else {
      // Save fresh data to cache for after-hours use
      const cacheVal = JSON.stringify(global)
      db()`INSERT INTO platform_config (key, value, updated_at) VALUES ('global_cache', ${cacheVal}, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()`.catch(() => {})
    }

    // ── India data: Zerodha live > Neon snapshot ──────────────────────────────
    const snap = snapRows.status === "fulfilled"
      ? (snapRows.value as any[])[0] ?? null
      : null
    const iq = indiaLive.status === "fulfilled" ? indiaLive.value : null

    const india = {
      nifty:        iq?.["NSE:NIFTY 50"]?.lastPrice    ?? snap?.nifty_price        ?? null,
      niftyChg:     iq?.["NSE:NIFTY 50"]?.changePct     ?? snap?.nifty_change_pct   ?? null,
      bankNifty:    iq?.["NSE:NIFTY BANK"]?.lastPrice   ?? snap?.banknifty_price    ?? null,
      bankNiftyChg: iq?.["NSE:NIFTY BANK"]?.changePct   ?? snap?.banknifty_change_pct ?? null,
      vix:          iq?.["NSE:INDIA VIX"]?.lastPrice    ?? snap?.india_vix          ?? null,
      pcr:          snap?.pcr          ?? null,
      fii:          (flowRows.status === "fulfilled" ? (flowRows.value as any[])[0]?.fii_net : null) ?? snap?.fii_cash_flow ?? null,
      dii:          (flowRows.status === "fulfilled" ? (flowRows.value as any[])[0]?.dii_net : null) ?? snap?.dii_cash_flow ?? null,
      regime:       snap?.market_regime ?? null,
      riskScore:    snap?.market_risk_score ?? null,
      oppScore:     snap?.market_opportunity_score ?? null,
      vs200dma:     snap?.nifty_vs_200dma ?? null,
      sectors:      snap?.sector_data_json
                      ? JSON.parse(snap.sector_data_json)
                      : {},
      source:       iq ? "zerodha_live" : "neon_snapshot",
      snapshotAge:  snap?.created_at
                      ? Math.round((Date.now() - new Date(snap.created_at).getTime()) / 60000)
                      : null,
    }

    // ── Derive composite risk signal ─────────────────────────────────────────
    const usAvg = ["^GSPC","^NDX","^DJI"].reduce(
      (s, k) => s + (global[k]?.changePct ?? 0), 0) / 3
    const asiaAvg = ["^N225","^HSI","000001.SS","^KS11"].reduce(
      (s, k) => s + (global[k]?.changePct ?? 0), 0) / 4
    const euroAvg = ["^FTSE","^GDAXI","^FCHI"].reduce(
      (s, k) => s + (global[k]?.changePct ?? 0), 0) / 3
    const btcChg  = global["BTC-USD"]?.changePct ?? 0
    const dxyChg  = global["DX-Y.NYB"]?.changePct ?? 0
    const goldChg = global["GC=F"]?.changePct ?? 0

    // Risk-Off: falling equities + rising DXY + rising Gold
    const riskOffSignal = (usAvg < -0.5 && dxyChg > 0 && goldChg > 0)
    // Risk-On: rising equities + rising crypto + falling DXY
    const riskOnSignal  = (usAvg > 0.5 && btcChg > 0 && dxyChg < 0)
    const capitalFlow   = riskOffSignal ? "Risk-Off → Bonds + Dollar"
                        : riskOnSignal  ? "Risk-On → Equities + Crypto"
                        : "Mixed — no clear directional signal"

    return NextResponse.json({
      ok: true,
      global,
      india,
      composite: { usAvg, asiaAvg, euroAvg, capitalFlow, riskOffSignal, riskOnSignal },
      fetchedAt: new Date().toISOString(),
    })
  } catch (err: any) {
    console.error("Global market error:", err)
    return NextResponse.json({ ok: false, global: {}, india: {}, error: err.message }, { status: 200 })
  }
}
