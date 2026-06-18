import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

const n = (v: any, f = 0) => { const x = Number(v); return Number.isFinite(x) ? x : f }
const clean = (s: any) => String(s ?? "").trim().toUpperCase()
const has = (v: any) => v !== null && v !== undefined && String(v) !== ""

type Row = Record<string, any>

async function safe<T>(p: Promise<T>, fallback: T): Promise<T> {
  try { return await p } catch { return fallback }
}

function mapRow(r: Row) {
  const symbol = clean(r.symbol ?? r.nse_symbol ?? r.tradingsymbol)
  const price = n(r.current_price ?? r.close ?? r.last_price ?? 0)
  const business = n(r.business_dna_score ?? r.business_score ?? 50)
  const earnings = n(r.earnings_score ?? r.earnings_momentum_score ?? 50)
  const smart = n(r.smart_money_score ?? 50)
  const stage = r.stage ?? null
  const isNr7 = !!(r.is_nr7 ?? r.nr7)
  const breakout = !!(r.breakout_ready ?? r.volume_expansion)
  const convergence = Math.max(0, Math.min(100, Math.round(
    n(r.convergence_score, NaN) || n(r.convergence, NaN) ||
    (business * 0.35 + earnings * 0.25 + smart * 0.15 + (isNr7 ? 12 : 0) + (breakout ? 8 : 0) + 15)
  )))

  return {
    symbol,
    name: r.name ?? r.company_name ?? symbol,
    industry: r.industry ?? r.sector ?? "—",
    price,
    market_cap: n(r.market_cap ?? r.market_cap_cr ?? 0),
    convergence,
    business_grade: r.business_dna_grade ?? (business >= 80 ? "A+" : business >= 65 ? "A" : business >= 50 ? "B" : "C"),
    business_score: business,
    earnings_score: earnings,
    sm_score: smart,
    sm_signal: r.smart_money_signal ?? "Neutral",
    ob_score: has(r.ob_score) ? n(r.ob_score) : null,
    ob_coverage: r.ob_coverage ?? r.coverage_tier ?? null,
    current_ob_cr: has(r.current_ob_cr) ? n(r.current_ob_cr) : null,
    earnings_momentum: has(r.earnings_momentum_score) ? n(r.earnings_momentum_score) : null,
    consecutive_beats: has(r.consecutive_beats) ? n(r.consecutive_beats) : null,
    is_nr7: isNr7,
    stage,
    breakout_ready: breakout,
  }
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim() || ""
  if (q.length < 1) return NextResponse.json({ ok: true, results: [] })

  const uq = q.toUpperCase()
  const like = `%${uq}%`
  const results: any[] = []
  const seen = new Set<string>()

  const add = (rows: Row[]) => {
    for (const row of rows) {
      const item = mapRow(row)
      if (!item.symbol || seen.has(item.symbol)) continue
      seen.add(item.symbol)
      results.push(item)
    }
  }

  // 1) Best case: existing rich stock_fundamentals table.
  add(await safe(sql`
    SELECT nse_symbol AS symbol, name, industry, current_price, market_cap,
           business_dna_score, business_dna_grade, earnings_score,
           smart_money_score, smart_money_signal, sector_rotation_score,
           return_3m, return_6m
    FROM stock_fundamentals
    WHERE UPPER(nse_symbol) LIKE ${like} OR UPPER(name) LIKE ${like} OR UPPER(COALESCE(industry,'')) LIKE ${like}
    ORDER BY CASE WHEN UPPER(nse_symbol) = ${uq} THEN 0 WHEN UPPER(nse_symbol) LIKE ${like} THEN 1 ELSE 2 END,
             business_dna_score DESC NULLS LAST
    LIMIT 12
  `, [] as Row[]))

  // 2) Current documented baseline: company_master.
  if (results.length < 10) add(await safe(sql`
    SELECT symbol, company_name AS name, NULL::text AS industry, market_cap_cr AS market_cap
    FROM company_master
    WHERE UPPER(symbol) LIKE ${like} OR UPPER(company_name) LIKE ${like}
    ORDER BY CASE WHEN UPPER(symbol) = ${uq} THEN 0 WHEN UPPER(symbol) LIKE ${like} THEN 1 ELSE 2 END,
             market_cap_cr DESC NULLS LAST
    LIMIT 15
  `, [] as Row[]))

  // 3) If only technical_signals exists, keep search usable.
  if (results.length < 10) add(await safe(sql`
    SELECT symbol, symbol AS name, NULL::text AS smart_money_signal, NULL::numeric AS convergence_score
    FROM technical_signals
    WHERE UPPER(symbol) LIKE ${like}
    ORDER BY symbol ASC
    LIMIT 10
  `, [] as Row[]))

  return NextResponse.json({ ok: true, query: q, count: results.length, results: results.slice(0, 10) })
}
