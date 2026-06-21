// app/api/stocks/discovery/route.ts
// Unified stocks discovery endpoint for the Stocks tab.
// Combines technical_signals + stock_fundamentals.
// Resilient: if optional Session-9 columns (mb_score, momentum_6m etc.) don't
// exist yet, falls back to base columns that always exist.

import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

export async function GET() {
  try {
    // ── Check which optional columns exist ─────────────────────────────────
    const colRows = await sql`
      SELECT column_name FROM information_schema.columns
      WHERE table_name = 'technical_signals'
        AND column_name = ANY(ARRAY[
          'mb_score','breakout_watch_score','breakout_watch_tier',
          'momentum_6m','pct_below_high','stage','stage_label',
          'above_ema200','vol_compression','volume_ratio_20','is_nr7'
        ])
    `.catch(() => [] as any[])

    const has = new Set((colRows as any[]).map((r: any) => r.column_name))

    // ── Build SELECT dynamically ───────────────────────────────────────────
    // Core columns always exist
    const rows = await sql`
      SELECT
        ts.symbol,
        COALESCE(cm.company_name, ts.symbol)          AS company_name,
        cm.sector,
        ts.close,
        ts.change_pct,
        ts.buy_zone_score,
        ts.nr7,
        ts.vr7,
        ts.volume_expansion,
        ts.ema_crossover,
        ts.rsi,
        -- Optional Session-9 columns — NULL when not present (handled by COALESCE)
        ${has.has('mb_score')            ? sql`ts.mb_score`            : sql`NULL::numeric`} AS mb_score,
        ${has.has('breakout_watch_score')? sql`ts.breakout_watch_score`: sql`NULL::numeric`} AS breakout_watch_score,
        ${has.has('breakout_watch_tier') ? sql`ts.breakout_watch_tier` : sql`NULL::text`}    AS breakout_watch_tier,
        ${has.has('momentum_6m')         ? sql`ts.momentum_6m`         : sql`NULL::numeric`} AS momentum_6m,
        ${has.has('pct_below_high')      ? sql`ts.pct_below_high`      : sql`NULL::numeric`} AS pct_below_high,
        ${has.has('stage')               ? sql`ts.stage`               : sql`NULL::text`}    AS stage,
        ${has.has('stage_label')         ? sql`ts.stage_label`         : sql`NULL::text`}    AS stage_label,
        ${has.has('above_ema200')        ? sql`ts.above_ema200`        : sql`NULL::boolean`} AS above_ema200,
        ${has.has('vol_compression')     ? sql`ts.vol_compression`     : sql`NULL::numeric`} AS vol_compression,
        ${has.has('volume_ratio_20')     ? sql`ts.volume_ratio_20`     : sql`NULL::numeric`} AS volume_ratio_20,
        ${has.has('is_nr7')              ? sql`ts.is_nr7`              : sql`ts.nr7`}        AS is_nr7,
        -- Stock fundamentals (all COALESCE'd — table always exists, values may be 0)
        COALESCE(sf.business_dna_score,  0)  AS business_dna_score,
        sf.business_dna_grade,
        COALESCE(sf.smart_money_score,   0)  AS smart_money_score,
        sf.smart_money_signal,
        COALESCE(sf.earnings_score,      0)  AS earnings_score,
        COALESCE(sf.roce,                0)  AS roce,
        sf.market_cap
      FROM technical_signals ts
      LEFT JOIN company_master     cm ON cm.symbol      = ts.symbol
      LEFT JOIN stock_fundamentals sf ON sf.nse_symbol  = ts.symbol
      WHERE ts.timeframe   = 'daily'
        AND ts.signal_date = (
          SELECT MAX(signal_date) FROM technical_signals WHERE timeframe = 'daily'
        )
        AND ts.symbol NOT SIMILAR TO '(ANTELOP|ACUTAAS|BMWVENTURE|UNKNOWN)%'
      ORDER BY
        COALESCE(
          ${has.has('mb_score') ? sql`ts.mb_score` : sql`ts.buy_zone_score`},
          ts.buy_zone_score, 0
        ) DESC NULLS LAST
      LIMIT 150
    `

    const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0

    // ── Derive tier from mb_score (if available) or buy_zone_score ─────────
    const data = (rows as any[]).map(s => {
      const mbScore  = n(s.mb_score ?? 0)
      const bzsScore = n(s.buy_zone_score ?? 0)
      const mom6m    = n(s.momentum_6m ?? 0)
      const dna      = mbScore > 0 ? mbScore : bzsScore

      const tier =
        mbScore >= 70 && mom6m > 10 ? "5x_candidate" :
        mbScore >= 45               ? "2x_candidate" :
        bzsScore >= 75              ? "2x_candidate" : "watch"

      return {
        ...s,
        dna_score:      Math.round(dna),
        predicted_tier: tier,
        is_nr7:         s.is_nr7 ?? s.nr7 ?? false,
        signals: [
          (s.is_nr7 || s.nr7)          ? "NR7"               : null,
          s.above_ema200                ? "Above EMA200"      : null,
          mom6m > 15                    ? `+${mom6m.toFixed(0)}% 6M` : null,
          s.volume_expansion            ? "Vol expansion"     : null,
          s.breakout_watch_tier === "COILED"   ? "🔥 Coiled"   : null,
          s.breakout_watch_tier === "BUILDING" ? "⚡ Building" : null,
          (s.smart_money_signal ?? "").toLowerCase().includes("accum") ? "SM Accum" : null,
        ].filter(Boolean),
      }
    })

    return NextResponse.json({
      ok:     true,
      data,
      count:  data.length,
      has_session9_cols: has.size > 0,
      cols:   Array.from(has),
    })

  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message, data: [] }, { status: 500 })
  }
}
