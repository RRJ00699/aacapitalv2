// app/api/stocks/discovery/route.ts
// Unified stocks discovery — technical_signals + stock_fundamentals
// Strategy: try full query (with Session-9 columns); if columns missing, fallback to base.
// No dynamic SQL — that breaks the Neon client.

import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

const SUPPRESS = /^(ANTELOP|ACUTAAS|BMWVENTURE|UNKNOWN)/i
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0

function buildResponse(rows: any[], hasSession9: boolean) {
  const data = (rows as any[])
    .filter(s => !SUPPRESS.test(s.symbol ?? ""))
    .map(s => {
      const mom  = n(s.momentum_6m ?? 0)
      // REAL business-quality composite (ROCE/ROE/debt/business-DNA) + smart-money context.
      // NOT the old mb_score/buy_zone technical composite — backtests showed that has no edge.
      const roce = n(s.roce), roe = n(s.roe)
      const debt = n(s.debt_to_equity), bdna = n(s.business_dna_score)
      const sm   = n(s.smart_money_score)
      const hasFund = roce > 0 || roe > 0   // do we actually have fundamentals to judge?

      let q = 0
      if      (roce >= 20) q += 30
      else if (roce >= 15) q += 20
      else if (roce >= 10) q += 10
      if      (roe  >= 18) q += 20
      else if (roe  >= 12) q += 10
      if      (debt > 0 && debt < 0.5) q += 20
      else if (debt > 0 && debt < 1.0) q += 10
      if      (bdna >= 75) q += 15
      else if (bdna >= 60) q += 8
      if      (sm   >= 70) q += 15   // institutional ownership as context, lighter weight
      else if (sm   >= 50) q += 8
      const quality = Math.min(q, 100)

      const tier =
        !hasFund                                   ? "unrated" :
        (quality >= 80 && roce >= 20)               ? "elite"  :
        (quality >= 60 && roce >= 15)               ? "strong" : "decent"

      return {
        ...s,
        dna_score:      hasFund ? quality : 0,   // unrated (no data) sink to the bottom
        quality_score:  quality,
        predicted_tier: tier,
        is_nr7:  !!(s.is_nr7 ?? s.nr7),
        mf_conviction:       n(s.mf_conviction_funds) > 0,
        mf_conviction_funds: n(s.mf_conviction_funds) || 0,
        mf_conviction_names: s.mf_conviction_fund_names ?? null,
        mf_conviction_seen:  s.mf_conviction_seen ?? null,
        signals: [
          (s.is_nr7 || s.nr7)   ? "NR7"          : null,
          s.above_ema200         ? "Above EMA200" : null,
          mom > 15               ? `+${mom.toFixed(0)}% 6M` : null,
          s.volume_expansion     ? "Vol↑"         : null,
          s.breakout_watch_tier === "COILED"   ? "🔥 Coiled"   : null,
          s.breakout_watch_tier === "BUILDING" ? "⚡ Building" : null,
          (s.smart_money_signal ?? "").toLowerCase().includes("accum") ? "SM Accum" : null,
          n(s.mf_conviction_funds) >= 2 ? `💎 New conviction ×${n(s.mf_conviction_funds)}` :
          n(s.mf_conviction_funds) === 1 ? "💎 New conviction" : null,
        ].filter(Boolean),
      }
    })

  return NextResponse.json({ ok: true, data, count: data.length, has_session9_cols: hasSession9 })
}

export async function GET() {
  try {
    // ── Attempt 1: Full query with Session-9 columns ──────────────────────
    // These columns were written by generate_signals.py.
    // If they don't exist yet this query throws → caught below.
    const rows = await sql`
      SELECT
        ts.symbol,
        COALESCE(cm.company_name, ts.symbol)  AS company_name,
        cm.sector,
        ts.close,
        ts.change_pct,
        ts.buy_zone_score,
        ts.nr7,
        ts.vr7,
        ts.volume_expansion,
        ts.ema_crossover,
        ts.rsi,
        ts.mb_score,
        ts.breakout_watch_score,
        ts.breakout_watch_tier,
        ts.momentum_6m,
        ts.pct_below_high,
        ts.stage,
        ts.stage_label,
        ts.above_ema200,
        ts.vol_compression,
        ts.volume_ratio_20,
        COALESCE(ts.is_nr7, ts.nr7, false)    AS is_nr7,
        COALESCE(sf.business_dna_score,  0)   AS business_dna_score,
        sf.business_dna_grade,
        COALESCE(sf.smart_money_score,   0)   AS smart_money_score,
        sf.smart_money_signal,
        mc.n_funds        AS mf_conviction_funds,
        mc.funds          AS mf_conviction_fund_names,
        mc.first_seen     AS mf_conviction_seen,
        COALESCE(sf.earnings_score,      0)   AS earnings_score,
        COALESCE(sf.roce,                0)   AS roce,
        COALESCE(sf.roe,                 0)   AS roe,
        COALESCE(sf.debt_to_equity,      0)   AS debt_to_equity,
        sf.pe_ratio,
        sf.market_cap
      FROM technical_signals ts
      LEFT JOIN company_master     cm ON cm.symbol     = ts.symbol
      LEFT JOIN stock_fundamentals sf ON sf.nse_symbol = ts.symbol
      LEFT JOIN mf_conviction_flags mc ON mc.nse_symbol = ts.symbol AND mc.expires_on >= CURRENT_DATE
      WHERE ts.timeframe   = 'daily'
        AND ts.signal_date = (
          SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
        )
      ORDER BY COALESCE(sf.roce, 0) DESC NULLS LAST
      LIMIT 200
    `

    return buildResponse(rows as any[], true)

  } catch {
    // ── Fallback: base columns only (generate_signals.py hasn't run yet) ──
    try {
      const rows = await sql`
        SELECT
          ts.symbol,
          COALESCE(cm.company_name, ts.symbol)  AS company_name,
          cm.sector,
          ts.close,
          ts.change_pct,
          ts.buy_zone_score,
          ts.nr7,
          ts.vr7,
          ts.volume_expansion,
          ts.ema_crossover,
          ts.rsi,
          COALESCE(sf.business_dna_score,  0)   AS business_dna_score,
          sf.business_dna_grade,
          COALESCE(sf.smart_money_score,   0)   AS smart_money_score,
          sf.smart_money_signal,
          mc.n_funds        AS mf_conviction_funds,
          mc.funds          AS mf_conviction_fund_names,
          mc.first_seen     AS mf_conviction_seen,
          COALESCE(sf.earnings_score,      0)   AS earnings_score,
          COALESCE(sf.roce,                0)   AS roce,
          COALESCE(sf.roe,                 0)   AS roe,
          COALESCE(sf.debt_to_equity,      0)   AS debt_to_equity,
            sf.pe_ratio,
          sf.market_cap
        FROM technical_signals ts
        LEFT JOIN company_master     cm ON cm.symbol     = ts.symbol
        LEFT JOIN stock_fundamentals sf ON sf.nse_symbol = ts.symbol
        LEFT JOIN mf_conviction_flags mc ON mc.nse_symbol = ts.symbol AND mc.expires_on >= CURRENT_DATE
        WHERE ts.timeframe   = 'daily'
          AND ts.signal_date = (
            SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
          )
        ORDER BY COALESCE(sf.roce, 0) DESC NULLS LAST
        LIMIT 200
      `

      return buildResponse(rows as any[], false)

    } catch (err: any) {
      return NextResponse.json({ ok: false, error: err.message, data: [] }, { status: 500 })
    }
  }
}
