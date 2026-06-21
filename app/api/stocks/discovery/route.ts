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
      const mb  = n(s.mb_score ?? 0)
      const bzs = n(s.buy_zone_score ?? 0)
      const mom = n(s.momentum_6m ?? 0)
      const dna = mb > 0 ? mb : bzs

      return {
        ...s,
        dna_score:      Math.round(dna),
        predicted_tier:
          mb >= 70 && mom > 10 ? "5x_candidate" :
          mb >= 45              ? "2x_candidate" :
          bzs >= 75             ? "2x_candidate" : "watch",
        is_nr7:  !!(s.is_nr7 ?? s.nr7),
        signals: [
          (s.is_nr7 || s.nr7)   ? "NR7"          : null,
          s.above_ema200         ? "Above EMA200" : null,
          mom > 15               ? `+${mom.toFixed(0)}% 6M` : null,
          s.volume_expansion     ? "Vol↑"         : null,
          s.breakout_watch_tier === "COILED"   ? "🔥 Coiled"   : null,
          s.breakout_watch_tier === "BUILDING" ? "⚡ Building" : null,
          (s.smart_money_signal ?? "").toLowerCase().includes("accum") ? "SM Accum" : null,
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
        COALESCE(sf.earnings_score,      0)   AS earnings_score,
        COALESCE(sf.roce,                0)   AS roce,
        sf.market_cap
      FROM technical_signals ts
      LEFT JOIN company_master     cm ON cm.symbol     = ts.symbol
      LEFT JOIN stock_fundamentals sf ON sf.nse_symbol = ts.symbol
      WHERE ts.timeframe   = 'daily'
        AND ts.signal_date = (
          SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
        )
      ORDER BY COALESCE(ts.mb_score, ts.buy_zone_score, 0) DESC NULLS LAST
      LIMIT 150
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
          COALESCE(sf.earnings_score,      0)   AS earnings_score,
          COALESCE(sf.roce,                0)   AS roce,
          sf.market_cap
        FROM technical_signals ts
        LEFT JOIN company_master     cm ON cm.symbol     = ts.symbol
        LEFT JOIN stock_fundamentals sf ON sf.nse_symbol = ts.symbol
        WHERE ts.timeframe   = 'daily'
          AND ts.signal_date = (
            SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
          )
        ORDER BY ts.buy_zone_score DESC NULLS LAST
        LIMIT 150
      `

      return buildResponse(rows as any[], false)

    } catch (err: any) {
      return NextResponse.json({ ok: false, error: err.message, data: [] }, { status: 500 })
    }
  }
}
