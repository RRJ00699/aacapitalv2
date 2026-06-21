import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

const n = (v: any, f: any = null) => { const x = Number(v); return Number.isFinite(x) ? x : f }
const pick = (...vals: any[]) => vals.find(v => v !== null && v !== undefined && String(v) !== "") ?? null
const safe = async <T,>(p: Promise<T>, f: T): Promise<T> => { try { return await p } catch { return f } }

export async function GET() {
  const [snapshot, regime, flows] = await Promise.all([
    safe(sql`SELECT * FROM market_snapshot WHERE id=1 LIMIT 1`, [] as any[]),
    safe(sql`SELECT * FROM market_regimes ORDER BY evaluation_date DESC LIMIT 1`, [] as any[]),
    safe(sql`SELECT * FROM daily_institutional_flows ORDER BY trade_date DESC LIMIT 1`, [] as any[]),
  ])

  const snap = snapshot[0] || {}
  const reg = regime[0] || {}
  const flow = flows[0] || {}
  const payload = typeof snap.payload === "string" ? (() => { try { return JSON.parse(snap.payload) } catch { return {} } })() : (snap.payload || {})

  const regimeName = pick(reg.active_regime, snap.market_regime, "NORMAL")
  const deployMin = n(pick(reg.recommended_allocation_min, snap.deploy_min, payload.deploy_min), regimeName === "BEARISH" ? 10 : 50)
  const deployMax = n(pick(reg.recommended_allocation_max, snap.deploy_max, payload.deploy_max), regimeName === "BEARISH" ? 30 : 70)

  // Live price fetch from Yahoo (fallback when DB has stale/null data)
  let liveNifty = 0, liveBankNifty = 0, liveVix = 0
  try {
    const [nRes, bRes, vRes] = await Promise.all([
      fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d",
        { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(4000) }).then(r=>r.json()).catch(()=>null),
      fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEBANK?interval=1d&range=1d",
        { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(4000) }).then(r=>r.json()).catch(()=>null),
      fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?interval=1d&range=1d",
        { headers: { "User-Agent": "Mozilla/5.0" }, signal: AbortSignal.timeout(4000) }).then(r=>r.json()).catch(()=>null),
    ])
    const price = (d: any) => d?.chart?.result?.[0]?.meta?.regularMarketPrice ?? 0
    liveNifty     = price(nRes)
    liveBankNifty = price(bRes)
    liveVix       = price(vRes)
  } catch {}

  const finalNifty     = liveNifty     || n(pick(snap.nifty_price, reg.nifty_close, payload.nifty_price))
  const finalBankNifty = liveBankNifty || n(pick(snap.banknifty_price, payload.banknifty_price))
  const finalVix       = liveVix       || n(pick(snap.vix, snap.india_vix, payload.vix))

  return NextResponse.json({
    ok: true,
    data: {
      regime: regimeName,
      market_regime: regimeName,
      nifty_price: finalNifty,
      nifty_change_pct: n(pick(snap.nifty_change_pct, payload.nifty_change_pct)),
      sensex_price: n(pick(snap.sensex_price, payload.sensex_price)),
      sensex_change_pct: n(pick(snap.sensex_change_pct, payload.sensex_change_pct)),
      banknifty_price: finalBankNifty,
      banknifty_change_pct: n(pick(snap.banknifty_change_pct, payload.banknifty_change_pct)),
      nifty_ema200: n(pick(reg.nifty_ema_200, payload.ema200)),
      breadth_pct: n(pick(reg.breadth_percentage, snap.breadth_pct, payload.breadth)),
      deploy_min: deployMin,
      deploy_max: deployMax,
      vix: n(pick(snap.vix, snap.india_vix, reg.india_vix, payload.vix)),
      pcr: n(pick(snap.pcr, snap.nifty_pcr, payload.pcr)),
      fii_flow: n(pick(flow.fii_net, snap.fii_flow, payload.fii_flow)),
      dii_flow: n(pick(flow.dii_net, snap.dii_flow, payload.dii_flow)),
      last_updated: pick(snap.last_updated, reg.evaluation_date),
    }
  })
}
