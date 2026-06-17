// app/api/market/global/route.ts
// India data: Zerodha Kite (token from Neon platform_config)
// Global data: Yahoo Finance (US, Gold, BTC, DXY, Asia, Europe)
// Yahoo cache in Neon for after-hours fallback

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

const db = () => neon((process.env.DATABASE_URL || process.env.NEON_DATABASE_URL)! )

// ── Global symbols (non-India only) ──────────────────────────────────────────
const GLOBAL_SYMBOLS = [
  "^GSPC","^NDX","^DJI",
  "DX-Y.NYB","USDINR=X",
  "GC=F","CL=F",
  "BTC-USD",
  "^N225","^HSI",
  "^FTSE","^GDAXI",
]

const META: Record<string, { label: string; region: string; flag: string }> = {
  "^GSPC":    { label:"S&P 500",    region:"us",        flag:"🇺🇸" },
  "^NDX":     { label:"Nasdaq 100", region:"us",        flag:"🇺🇸" },
  "^DJI":     { label:"Dow Jones",  region:"us",        flag:"🇺🇸" },
  "DX-Y.NYB": { label:"DXY",        region:"fx",        flag:"💵" },
  "USDINR=X": { label:"USD/INR",    region:"fx",        flag:"₹"  },
  "GC=F":     { label:"Gold",       region:"commodity", flag:"🥇" },
  "CL=F":     { label:"Crude Oil",  region:"commodity", flag:"🛢" },
  "BTC-USD":  { label:"Bitcoin",    region:"crypto",    flag:"₿"  },
  "^N225":    { label:"Nikkei",     region:"asia",      flag:"🇯🇵" },
  "^HSI":     { label:"Hang Seng",  region:"asia",      flag:"🇭🇰" },
  "^FTSE":    { label:"FTSE 100",   region:"europe",    flag:"🇬🇧" },
  "^GDAXI":   { label:"DAX",        region:"europe",    flag:"🇩🇪" },
}

const toNum = (v: any) => { const n = Number(v); return Number.isFinite(n) ? n : null }
const first = (...vals: any[]) => vals.find(v => v !== null && v !== undefined && v !== "") ?? null

// ── Zerodha: get Indian market data using token from Neon ─────────────────────
async function getKiteIndia(sql: ReturnType<typeof db>) {
  try {
    const rows = await sql`SELECT value FROM platform_config WHERE key = 'kite_access_token' LIMIT 1`
    if (!rows.length || !process.env.KITE_API_KEY) return null

    const token  = rows[0].value as string
    const apiKey = process.env.KITE_API_KEY

    // Fetch Nifty 50, Bank Nifty, India VIX in one call
    const res = await fetch(
      "https://api.kite.trade/quote?i=NSE%3ANIFTY+50&i=NSE%3ANIFTY+BANK&i=NSE%3AINDIA+VIX&i=BSE%3ASENSEX",
      {
        headers: {
          "X-Kite-Version": "3",
          "Authorization": `token ${apiKey}:${token}`,
        },
        signal: AbortSignal.timeout(5000),
        cache: "no-store",
      }
    )

    if (!res.ok) {
      console.warn(`Kite API ${res.status}: ${await res.text().catch(() => "")}`)
      return null
    }

    const data = await res.json()
    const d    = data?.data ?? {}

    const nifty     = d["NSE:NIFTY 50"]
    const bankNifty = d["NSE:NIFTY BANK"]
    const vix       = d["NSE:INDIA VIX"]
    const sensex    = d["BSE:SENSEX"]

    if (!nifty) return null

    return {
      nifty:        toNum(nifty.last_price),
      niftyChg:     toNum(nifty.net_change),
      niftyChgPct:  nifty.last_price && nifty.ohlc?.close
                      ? toNum(((nifty.last_price - nifty.ohlc.close) / nifty.ohlc.close) * 100)
                      : null,
      bankNifty:    toNum(bankNifty?.last_price),
      sensex:       toNum(sensex?.last_price),
      bankNiftyChgPct: bankNifty?.last_price && bankNifty?.ohlc?.close
                        ? toNum(((bankNifty.last_price - bankNifty.ohlc.close) / bankNifty.ohlc.close) * 100)
                        : null,
      vix:          toNum(vix?.last_price),
      source:       "kite_live",
    }
  } catch (e) {
    console.warn("Kite India fetch failed:", e)
    return null
  }
}

// ── Yahoo Finance: global assets only ────────────────────────────────────────
async function fetchYahooGlobal(): Promise<Record<string, any>> {
  const global: Record<string, any> = {}
  const YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
  }
  // v8 per-symbol works when v7 batch is rate-limited
  await Promise.allSettled(GLOBAL_SYMBOLS.map(async (sym) => {
    try {
      const res = await fetch(
        `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=1d`,
        { headers: YF_HEADERS, cache: "no-store", signal: AbortSignal.timeout(5000) }
      )
      if (!res.ok) return
      const data = await res.json()
      const m = data?.chart?.result?.[0]?.meta
      if (!m) return
      const price = toNum(m.regularMarketPrice)
      const prev  = toNum(m.previousClose ?? m.chartPreviousClose)
      if (!price) return
      const changePct = prev ? toNum(((price - prev) / prev) * 100) : null
      const meta = META[sym]
      if (!meta) return
      global[sym] = { ...meta, symbol: sym, price, changePct, change: prev ? toNum(price - prev) : null }
    } catch {}
  }))
  return global
}

export async function GET() {
  try {
    const sql = db()

    // Run all fetches in parallel
    const [kiteResult, yahooResult, regimeRows, flowRows, snapRows] = await Promise.allSettled([
      getKiteIndia(sql),
      fetchYahooGlobal(),
      sql`SELECT active_regime, nifty_close, nifty_ema_200, breadth_percentage,
                 india_vix, evaluation_date,
                 recommended_allocation_min, recommended_allocation_max
          FROM market_regimes ORDER BY evaluation_date DESC LIMIT 1`.catch(() => []),
      sql`SELECT fii_net, dii_net, trade_date
          FROM daily_institutional_flows ORDER BY trade_date DESC LIMIT 1`.catch(() => []),
      sql`SELECT * FROM market_snapshot WHERE id = 1 LIMIT 1`.catch(() => []),
    ])

    const kite   = kiteResult.status   === "fulfilled" ? kiteResult.value   : null
    const regime = regimeRows.status   === "fulfilled" ? (regimeRows.value   as any[])[0] ?? {} : {}
    const flow   = flowRows.status     === "fulfilled" ? (flowRows.value     as any[])[0] ?? {} : {}
    const snap   = snapRows.status     === "fulfilled" ? (snapRows.value     as any[])[0] ?? {} : {}

    // ── Global markets: Yahoo fresh → Neon cache fallback ──────────────────
    let global = yahooResult.status === "fulfilled" ? yahooResult.value : {}
    const gotYahoo = Object.keys(global).length > 3

    if (gotYahoo) {
      // Save fresh data to cache — bind as variable to avoid SQL injection issues
      const cacheJson = JSON.stringify(global)
      sql`INSERT INTO platform_config (key, value, updated_at)
          VALUES ('global_cache', ${cacheJson}, NOW())
          ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()`
        .catch(() => {})
    } else {
      // Load from Neon cache (populated by seed_global_cache.py daily at 4:30PM)
      try {
        const cached = await sql`SELECT value FROM platform_config WHERE key = 'global_cache' LIMIT 1`
        if (cached.length && cached[0].value) {
          const parsed = JSON.parse(cached[0].value as string)
          Object.assign(global, parsed)
        }
      } catch (cacheErr) {
        console.warn("Global cache parse error:", cacheErr)
      }
    }

    // ── India: Kite live → regime → snapshot fallback ───────────────────────
    const india = {
      // Prices
      nifty:              first(kite?.nifty,        regime.nifty_close,  snap.nifty_price),
      bankNifty:          first(kite?.bankNifty,    snap.banknifty_price),
      vix:                first(kite?.vix,          regime.india_vix,    snap.vix, snap.india_vix),
      sensex:             first(kite?.sensex,       snap.sensex_price),
      // Change % — both aliases for compatibility with today-screen pickFirst chains
      niftyChg:           first(kite?.niftyChgPct,  snap.nifty_change_pct),
      nifty_change_pct:   first(kite?.niftyChgPct,  snap.nifty_change_pct),
      bankNiftyChg:       first(kite?.bankNiftyChgPct, snap.banknifty_change_pct),
      sensexChg:          first(snap.sensex_change_pct),
      banknifty_change_pct: first(kite?.bankNiftyChgPct, snap.banknifty_change_pct),
      // Flows
      pcr:      first(snap.pcr, snap.nifty_pcr),
      fii:      first(flow.fii_net, snap.fii_flow,  snap.fii_cash_flow),
      fii_flow: first(flow.fii_net, snap.fii_flow,  snap.fii_cash_flow),
      dii:      first(flow.dii_net, snap.dii_flow,  snap.dii_cash_flow),
      dii_flow: first(flow.dii_net, snap.dii_flow,  snap.dii_cash_flow),
      // Regime
      regime:    first(regime.active_regime, snap.market_regime, "NORMAL"),
      breadthPct:first(regime.breadth_percentage, snap.breadth_pct),
      deployMin: first(regime.recommended_allocation_min, snap.deploy_min),
      deployMax: first(regime.recommended_allocation_max, snap.deploy_max),
      source:    kite ? "kite_live" : "neon_fallback",
    }

    return NextResponse.json({
      ok:        true,
      global,
      india,
      composite: {
        dataSource:   kite ? "kite+yahoo" : gotYahoo ? "yahoo_only" : "neon_cache",
        yahooFresh:   gotYahoo,
        kiteLive:     !!kite,
      },
      fetchedAt: new Date().toISOString(),
    })

  } catch (err: any) {
    console.error("Global market error:", err)
    return NextResponse.json({ ok: false, global: {}, india: {}, error: err.message }, { status: 200 })
  }
}
