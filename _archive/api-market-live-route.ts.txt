import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"
import { getBroker } from "@/lib/brokers"

function getSQL() { return neon(process.env.DATABASE_URL!) }

// Actual market_snapshot columns:
// id, snapshot_date, last_updated, nifty_price, banknifty_price,
// vix, pcr, advance_decline_ratio, fii_flow, dii_flow,
// nifty_vs_20dma, nifty_vs_50dma, nifty_vs_200dma,
// market_regime, market_risk_score, market_opportunity_score,
// recommended_exposure, sector_data_json, confidence, notes

const INDEX_KEYS = [
  "NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:INDIA VIX",
  "NSE:NIFTY IT", "NSE:NIFTY PHARMA", "NSE:NIFTY AUTO",
  "NSE:NIFTY REALTY", "NSE:NIFTY FMCG", "NSE:NIFTY METAL",
  "NSE:NIFTY ENERGY", "NSE:NIFTY INFRA", "NSE:NIFTY FINSERV",
]

async function fetchNSEPCR(): Promise<number | null> {
  try {
    const res = await fetch(
      "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
      {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          "Accept": "application/json",
          "Referer": "https://www.nseindia.com/",
        },
        signal: AbortSignal.timeout(5000),
      }
    )
    if (!res.ok) return null
    const data = await res.json()
    const records = data?.records?.data || []
    let putOI = 0, callOI = 0
    for (const rec of records) {
      if (rec.PE?.openInterest) putOI  += rec.PE.openInterest
      if (rec.CE?.openInterest) callOI += rec.CE.openInterest
    }
    return callOI === 0 ? null : +(putOI / callOI).toFixed(3)
  } catch { return null }
}

async function fetchFIIDII(): Promise<{ fii: number | null; dii: number | null }> {
  try {
    const res = await fetch("https://www.nseindia.com/api/fiidiiTradeReact", {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
      },
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) return { fii: null, dii: null }
    const data = await res.json()
    const latest = Array.isArray(data) ? data[0] : null
    if (!latest) return { fii: null, dii: null }
    return {
      fii: latest?.FII?.netBuySell ?? latest?.fiiNetBuySell ?? null,
      dii: latest?.DII?.netBuySell ?? latest?.diiNetBuySell ?? null,
    }
  } catch { return { fii: null, dii: null } }
}

async function fetchNiftyDMAsYahoo() {
  try {
    const res = await fetch(
      "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1y",
      { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(8000) }
    )
    if (!res.ok) return { vs20: 0, vs50: 0, vs200: 0 }
    const data = await res.json()
    const closes: number[] = (data?.chart?.result?.[0]?.indicators?.quote?.[0]?.close ?? [])
      .filter((c: number) => c != null && !isNaN(c))
    if (closes.length < 20) return { vs20: 0, vs50: 0, vs200: 0 }
    const last = closes[closes.length - 1]
    const sma = (n: number) =>
      closes.length >= n ? closes.slice(-n).reduce((a, b) => a + b, 0) / n : null
    const d20 = sma(20), d50 = sma(50), d200 = sma(200)
    return {
      vs20:  d20  ? +((last - d20)  / d20  * 100).toFixed(2) : 0,
      vs50:  d50  ? +((last - d50)  / d50  * 100).toFixed(2) : 0,
      vs200: d200 ? +((last - d200) / d200 * 100).toFixed(2) : 0,
    }
  } catch { return { vs20: 0, vs50: 0, vs200: 0 } }
}

function classifyRegime(d: { vix:number; pcr:number; vs20:number; vs50:number; vs200:number; fii:number }): string {
  const { vix, pcr, vs20, vs50, vs200 } = d
  if (vs200 < -8 && vix > 25)                                                      return "FROZEN"
  if (pcr < 0.7 && vix > 20 && vs200 > -10)                                        return "PANIC_OPPORTUNITY"
  if (vs20 > 0 && vs50 > 0 && vs200 > 0 && vix < 14 && pcr >= 0.8 && pcr <= 1.2) return "HOT"
  if (vs50 < -3 || (vix > 22 && vs200 < -3))                                       return "COLD"
  if (vs20 < -2 || vix > 18 || pcr > 1.3 || pcr < 0.7)                            return "CAUTION"
  return "NORMAL"
}

function calcRiskScore(d: any): number {
  let s = 25
  if (d.vix > 25)        s += 35; else if (d.vix > 20) s += 22; else if (d.vix > 16) s += 10
  if (d.vs200 < -8)      s += 25; else if (d.vs200 < -3) s += 12; else if (d.vs200 > 5) s -= 10
  if (d.vs50 < -5)       s += 15; else if (d.vs50 < -2) s += 8
  if ((d.fii||0) < -3000) s += 15; else if ((d.fii||0) < -1000) s += 7
  if (d.pcr > 1.4)       s += 10
  return Math.min(100, Math.max(0, s))
}

function calcOpportunityScore(d: any): number {
  let s = 40
  if (d.pcr < 0.7)       s += 25; else if (d.pcr < 0.9) s += 15; else if (d.pcr > 1.4) s -= 20
  if (d.vix > 25)        s -= 20; else if (d.vix > 20) s -= 10;  else if (d.vix < 13) s += 12
  if (d.vs200 < -5 && d.vix < 20) s += 15
  if (d.vs20 > 0 && d.vs50 > 0)   s += 10
  if ((d.fii||0) > 2000)           s += 10
  return Math.min(100, Math.max(0, s))
}

function calcExposure(regime: string): number {
  return ({ HOT:100, NORMAL:75, CAUTION:50, COLD:25, FROZEN:10, PANIC_OPPORTUNITY:40 } as any)[regime] ?? 75
}

// ── GET: return last snapshot ─────────────────────────────────────────────
export async function GET() {
  try {
    const sql  = getSQL()
    const rows = await sql`
      SELECT * FROM market_snapshot
      ORDER BY last_updated DESC
      LIMIT 1
    `
    return NextResponse.json({ ok: true, snapshot: rows[0] || null })
  } catch (err: any) {
    console.error("market/live GET:", err.message)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

// ── POST: fetch live data and store ──────────────────────────────────────
export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))

    let quotes: any = {}
    let source = "manual"

    try {
      const broker = getBroker()
      if (await broker.isConnected()) {
        quotes = await (broker as any).getQuotes(INDEX_KEYS)
        source = "zerodha"
      }
    } catch { /* Zerodha unavailable — continue */ }

    const [dmas, autoPCR, autoFII] = await Promise.all([
      fetchNiftyDMAsYahoo(),
      fetchNSEPCR(),
      fetchFIIDII(),
    ])

    const nifty  = quotes["NIFTY 50"]   || quotes["NSE:NIFTY 50"]
    const bnifty = quotes["NIFTY BANK"] || quotes["NSE:NIFTY BANK"]
    const vixQ   = quotes["INDIA VIX"]  || quotes["NSE:INDIA VIX"]

    // Yahoo Finance fallback for Nifty when Zerodha not connected
    let niftyPrice  = +(nifty?.lastPrice  || body.niftyPrice  || 0)
    let bniftyPrice = +(bnifty?.lastPrice || body.bankNiftyPrice || 0)
    let vix         = +(vixQ?.lastPrice   || body.vix || 15)

    if (!niftyPrice) {
      try {
        const [nsei, bnk, vixData] = await Promise.allSettled([
          fetch("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d", { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(5000) }).then(r => r.json()),
          fetch("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEBANK?interval=1d&range=1d", { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(5000) }).then(r => r.json()),
          fetch("https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?interval=1d&range=1d", { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(5000) }).then(r => r.json()),
        ])
        if (nsei.status === "fulfilled") niftyPrice  = nsei.value?.chart?.result?.[0]?.meta?.regularMarketPrice ?? 0
        if (bnk.status  === "fulfilled") bniftyPrice = bnk.value?.chart?.result?.[0]?.meta?.regularMarketPrice ?? 0
        if (vixData.status === "fulfilled") vix = vixData.value?.chart?.result?.[0]?.meta?.regularMarketPrice ?? 15
        if (niftyPrice) source = "yahoo"
      } catch { /* stay with zeros */ }
    }
    const sectorData: Record<string, number> = {}
    for (const s of ["IT","PHARMA","AUTO","REALTY","FMCG","METAL","ENERGY","INFRA","FINSERV"]) {
      const q = quotes[`NIFTY ${s}`] || quotes[`NSE:NIFTY ${s}`]
      if (q) sectorData[s] = +(q.changePct || 0).toFixed(2)
    }

    const pcr         = autoPCR ?? +(body.pcr || 1.0)
    const fii         = autoFII.fii ?? +(body.fiiFlow || 0)
    const dii         = autoFII.dii ?? +(body.diiFlow || 0)
    const adRatio     = +(body.advanceDecline || 1.0)

    const regime   = classifyRegime({ vix, pcr, vs20:dmas.vs20, vs50:dmas.vs50, vs200:dmas.vs200, fii })
    const riskScore = calcRiskScore({ vix, pcr, ...dmas, fii })
    const oppScore  = calcOpportunityScore({ vix, pcr, ...dmas, fii })
    const exposure  = calcExposure(regime)

    const sql = getSQL()
    await sql`
      INSERT INTO market_snapshot (
        nifty_price, banknifty_price, vix, pcr,
        advance_decline_ratio, fii_flow, dii_flow,
        nifty_vs_20dma, nifty_vs_50dma, nifty_vs_200dma,
        market_regime, market_risk_score, market_opportunity_score,
        recommended_exposure, sector_data_json,
        confidence, notes
      ) VALUES (
        ${niftyPrice}, ${bniftyPrice}, ${vix}, ${pcr},
        ${adRatio}, ${fii}, ${dii},
        ${dmas.vs20}, ${dmas.vs50}, ${dmas.vs200},
        ${regime}, ${riskScore}, ${oppScore},
        ${exposure}, ${JSON.stringify(sectorData)},
        ${source === "zerodha" ? "live" : "manual"},
        ${body.notes || null}
      )
    `

    return NextResponse.json({
      ok: true, source, regime,
      riskScore, oppScore, exposure,
      nifty: niftyPrice, vix, pcr, fii, dii,
      dmas, sectors: sectorData,
      autoFetched: { pcr: autoPCR !== null, fii: autoFII.fii !== null }
    })
  } catch (err: any) {
    console.error("market/live POST:", err.message)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
