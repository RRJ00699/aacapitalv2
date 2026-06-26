import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

// ── /api/stocks ──────────────────────────────────────────────────────────────
// The funnel's front door: the SAME 4 decomposed sub-scores as /api/stock/scorecard,
// computed for the entire universe in one shot so the Stocks grid can sort/filter on
// them. The scoring logic here is a verbatim port of the single-symbol scorecard —
// identical bands, identical lender handling, identical weights — so the grid and the
// workboard verdict header can never disagree. Research signal, not a buy call.

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}
const clamp = (n: number) => Math.max(0, Math.min(100, Math.round(n)))

function band(value: number | null, bad: number, good: number, higherIsBetter = true): number | null {
  if (value === null) return null
  const lo = higherIsBetter ? bad : good
  const hi = higherIsBetter ? good : bad
  const pct = ((value - lo) / (hi - lo)) * 100
  return clamp(higherIsBetter ? pct : 100 - clamp(pct))
}
function avg(parts: (number | null)[]): number | null {
  const live = parts.filter((p): p is number => p !== null)
  if (!live.length) return null
  return clamp(live.reduce((a, b) => a + b, 0) / live.length)
}

function buildRead(s: { quality: number | null; smartMoney: number | null; valuation: number | null; momentum: number | null }): string {
  const hi = (n: number | null) => n !== null && n >= 65
  const lo = (n: number | null) => n !== null && n < 45
  const bits: string[] = []
  if (hi(s.quality)) bits.push("quality business")
  else if (lo(s.quality)) bits.push("weaker fundamentals")
  if (hi(s.smartMoney)) bits.push("funds are buying")
  if (lo(s.valuation)) bits.push("looks pricey")
  else if (hi(s.valuation)) bits.push("reasonably valued")
  if (lo(s.momentum)) bits.push("not yet trending")
  else if (hi(s.momentum)) bits.push("momentum building")
  if (!bits.length) return "Mixed signals — no strong tilt either way."
  const txt = bits.join(" · ")
  return txt.charAt(0).toUpperCase() + txt.slice(1)
}

// Score one fundamentals row. Verbatim port of the single-symbol scorecard math.
function scoreOne(f: any, sectorPe: number | null, flag: any) {
  const sectorText = `${f.industry || ""} ${f.industry_group || ""}`.toLowerCase()
  const isFinance = /financ|bank|nbfc|lend|insur|capital market|housing finance/.test(sectorText)

  const qParts = {
    roce:     band(num(f.roce), 8, 25),
    roe:      band(num(f.roe), 8, 22),
    opm:      band(num(f.opm_pct), 5, 25),
    debt:     isFinance ? null : band(num(f.debt_to_equity), 1.5, 0.2, false),
    intCover: isFinance ? null : band(num(f.interest_coverage), 1.5, 8),
    dna:      num(f.business_dna_score),
  }
  const quality = avg(Object.values(qParts))

  const sig = String(f.smart_money_signal || "").toLowerCase()
  const signalBase =
    sig.includes("strong accum") ? 88 :
    sig.includes("accum")        ? 72 :
    sig.includes("heavy distrib")? 12 :
    sig.includes("distrib")      ? 28 :
    sig.includes("neutral")      ? 50 : null
  const smParts = {
    signal:     signalBase,
    bulkFlow:   num(f.bulk_net_flow) !== null ? (Number(f.bulk_net_flow) > 0 ? 68 : 30) : null,
    conviction: flag ? clamp(60 + Number(flag.n_funds || 0) * 12) : null,
  }
  const smartMoney = avg(Object.values(smParts))

  const pe = num(f.pe_ratio)
  let valuation: number | null = null
  if (pe !== null && pe > 0 && sectorPe && sectorPe > 0) {
    const ratio = pe / sectorPe
    valuation = clamp(85 - (ratio - 0.5) * 36)
  } else if (pe !== null && pe > 0) {
    valuation = band(pe, 60, 12, false)
  }

  const mParts = {
    ret3m:     band(num(f.return_3m), -10, 30),
    ret6m:     band(num(f.return_6m), -15, 45),
    earnings:  num(f.earnings_score),
    patGrowth: band(num(f.pat_growth_1y), 0, 40),
    sectorRot: num(f.sector_rotation_score),
  }
  const momentum = avg(Object.values(mParts))

  const convergence = avg([quality, quality, smartMoney, smartMoney, valuation, momentum])

  return {
    symbol: f.nse_symbol,
    name: f.name,
    industry: f.industry_group || f.industry,
    price: num(f.current_price),
    market_cap: num(f.market_cap),
    convergence,
    quality, smartMoney, valuation, momentum,
    read: buildRead({ quality, smartMoney, valuation, momentum }),
    conviction_funds: flag ? Number(flag.n_funds || 0) : 0,
    has_conviction: !!flag,                              // 💎 badge
    smart_money_signal: f.smart_money_signal ?? null,
  }
}

export async function GET(_req: NextRequest) {
  try {
    const sql = neon(process.env.DATABASE_URL!)

    const [rows, sectorRows, flagRows] = await Promise.all([
      sql`SELECT nse_symbol, name, industry, industry_group, current_price, market_cap,
                 pe_ratio, roce, roe, opm_pct, debt_to_equity, interest_coverage,
                 pat_growth_1y, business_dna_score, earnings_score,
                 smart_money_signal, bulk_net_flow, bulk_deal_count,
                 return_3m, return_6m, sector_rotation_score
          FROM stock_fundamentals
          WHERE nse_symbol IS NOT NULL`,
      sql`SELECT industry_group,
                 percentile_cont(0.5) WITHIN GROUP (ORDER BY pe_ratio) AS sector_pe
          FROM stock_fundamentals
          WHERE pe_ratio > 0 AND pe_ratio < 200 AND industry_group IS NOT NULL
          GROUP BY industry_group`,
      sql`SELECT nse_symbol, n_funds, funds
          FROM mf_conviction_flags
          WHERE expires_on >= CURRENT_DATE`,
    ])

    const sectorPe = new Map<string, number>()
    for (const r of sectorRows as any[]) {
      const p = num(r.sector_pe)
      if (p !== null) sectorPe.set(String(r.industry_group), p)
    }
    const flags = new Map<string, any>()
    for (const r of flagRows as any[]) flags.set(String(r.nse_symbol).toUpperCase(), r)

    const stocks = (rows as any[]).map(f =>
      scoreOne(f, sectorPe.get(String(f.industry_group)) ?? null, flags.get(String(f.nse_symbol).toUpperCase()) ?? null)
    )
    // default sort: highest convergence first (nulls last)
    stocks.sort((a, b) => (b.convergence ?? -1) - (a.convergence ?? -1))

    return NextResponse.json({
      ok: true,
      count: stocks.length,
      stocks,
      disclaimer: "Research signal, not a buy call. Same 4 sub-scores as the workboard verdict.",
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
