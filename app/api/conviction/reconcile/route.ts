import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

// ── /api/conviction/reconcile ────────────────────────────────────────────────
// Cross-checks the smart-money CONVICTION signal against actual FILED shareholding.
//   conviction side : stock_fundamentals.smart_money_signal + mf_conviction_flags.n_funds
//   filed side      : ownership_signals.fii_trend/dii_trend + mf_pct delta across
//                     the last quarters in shareholding_history
// Verdict:
//   confirmed    — signal bullish AND filings show institutions adding (no contradiction)
//   contradicted — signal bullish BUT filings show institutions reducing  ← the useful flag
//   mixed        — some adding, some reducing
//   no_move      — filings flat / no trend
//   no_filing    — no recent shareholding data to check against
//   neutral      — no strong conviction signal to reconcile
// Research signal, not a buy call.
//
// Usage: GET ?symbol=RELIANCE

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}
const dir = (t: any): "up" | "down" | "flat" | null => {
  const s = String(t ?? "").toLowerCase()
  if (!s) return null
  if (s.includes("incr")) return "up"
  if (s.includes("decr") || s.includes("redu")) return "down"
  return "flat"
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()
    if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })

    // conviction side
    let smartSignal: string | null = null
    try {
      const f = await sql`SELECT smart_money_signal FROM stock_fundamentals WHERE nse_symbol = ${symbol} LIMIT 1`
      smartSignal = (f as any[])[0]?.smart_money_signal ?? null
    } catch { smartSignal = null }

    let nFunds = 0
    try {
      const c = await sql`SELECT n_funds FROM mf_conviction_flags
                          WHERE nse_symbol = ${symbol} AND expires_on >= CURRENT_DATE
                          ORDER BY n_funds DESC LIMIT 1`
      nFunds = Number((c as any[])[0]?.n_funds || 0)
    } catch { nFunds = 0 }

    // filed side — ownership_signals (precomputed trends) + raw quarters for the MF delta
    let signalRow: any = null
    try {
      const o = await sql`SELECT fii_trend, dii_trend, promoter_trend, fii_pct, dii_pct, latest_quarter, updated_at
                          FROM ownership_signals WHERE nse_symbol = ${symbol} LIMIT 1`
      signalRow = (o as any[])[0] ?? null
    } catch { signalRow = null }

    let quarters: any[] = []
    try {
      const h = await sql`SELECT quarter, quarter_date, promoter_pct, fii_pct, dii_pct, mf_pct
                          FROM shareholding_history WHERE nse_symbol = ${symbol}
                          ORDER BY quarter_date DESC NULLS LAST, quarter DESC LIMIT 4`
      quarters = h as any[]
    } catch { quarters = [] }

    // MF % delta: latest quarter vs the most recent prior quarter that has a value
    const mfSeries = quarters.map(q => num(q.mf_pct))
    const latestMf = mfSeries.length ? mfSeries[0] : null
    let priorMf: number | null = null
    for (let i = 1; i < mfSeries.length; i++) { if (mfSeries[i] !== null) { priorMf = mfSeries[i]; break } }
    const mfDelta = latestMf !== null && priorMf !== null ? +(latestMf - priorMf).toFixed(2) : null

    // assemble filing direction
    const up: string[] = [], down: string[] = []
    const fiiDir = dir(signalRow?.fii_trend), diiDir = dir(signalRow?.dii_trend)
    if (fiiDir === "up") up.push("FII"); else if (fiiDir === "down") down.push("FII")
    if (diiDir === "up") up.push("DII"); else if (diiDir === "down") down.push("DII")
    if (mfDelta !== null) { if (mfDelta > 0.05) up.push("MF"); else if (mfDelta < -0.05) down.push("MF") }

    const sigText = String(smartSignal || "").toLowerCase()
    const bullish = /accum/.test(sigText) || nFunds > 0
    const bearish = /distrib/.test(sigText)
    const hasFiling = !!signalRow || mfDelta !== null

    let verdict: string
    if (!hasFiling) verdict = "no_filing"
    else if (!bullish && !bearish) verdict = "neutral"
    else {
      const withSignal = bullish ? up : down       // moves that agree with the signal
      const against    = bullish ? down : up       // moves that contradict it
      if (withSignal.length && !against.length) verdict = "confirmed"
      else if (against.length && !withSignal.length) verdict = "contradicted"
      else if (withSignal.length && against.length) verdict = "mixed"
      else verdict = "no_move"
    }

    const q = signalRow?.latest_quarter || quarters[0]?.quarter || null
    const sideText = (arr: string[]) => arr.join(" & ")
    let note: string
    switch (verdict) {
      case "confirmed":
        note = `Filings corroborate — ${sideText(bullish ? up : down)} ${bullish ? "adding" : "reducing"}${q ? ` (as of ${q})` : ""}.`
        break
      case "contradicted":
        note = bullish
          ? `⚠ Signal reads accumulation, but filings show ${sideText(down)} reducing${q ? ` (${q})` : ""}.`
          : `⚠ Signal reads distribution, but filings show ${sideText(up)} adding${q ? ` (${q})` : ""}.`
        break
      case "mixed":
        note = `Mixed: ${sideText(up)} up, ${sideText(down)} down since last filing${q ? ` (${q})` : ""}.`
        break
      case "no_move":
        note = `No institutional trend in the latest filing${q ? ` (${q})` : ""} to confirm the signal.`
        break
      case "no_filing":
        note = "No recent shareholding filing on record to cross-check."
        break
      default:
        note = "No strong conviction signal to reconcile against filings."
    }

    return NextResponse.json({
      ok: true,
      symbol,
      verdict,
      note,
      conviction: { signal: smartSignal, n_funds: nFunds, direction: bullish ? "bullish" : bearish ? "bearish" : "neutral" },
      filings: {
        latest_quarter: q,
        fii_pct: num(signalRow?.fii_pct), dii_pct: num(signalRow?.dii_pct), mf_pct: latestMf,
        fii_trend: signalRow?.fii_trend ?? null, dii_trend: signalRow?.dii_trend ?? null,
        mf_delta: mfDelta, adding: up, reducing: down,
        updated_at: signalRow?.updated_at ?? null,
      },
      disclaimer: "Conviction signal vs filed shareholding. Research signal, not a buy call.",
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
