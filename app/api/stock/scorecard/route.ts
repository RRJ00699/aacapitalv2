import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

// ── /api/stock/scorecard?sym=ABCAPITAL ───────────────────────────────────────
// Decomposes the convergence score into 4 named, explainable sub-scores, each
// computed from REAL columns in stock_fundamentals (+ mf_conviction_flags).
// Honest-by-design: every sub-score returns its own inputs so the UI can show
// "tap to explain". Research signal, not a buy call.

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

// clamp a value to 0..100
const clamp = (n: number) => Math.max(0, Math.min(100, Math.round(n)))

// map a metric into a 0..100 contribution given a good/bad band
// higherIsBetter: value at or above `good` => 100, at or below `bad` => 0, linear between
function band(value: number | null, bad: number, good: number, higherIsBetter = true): number | null {
  if (value === null) return null
  const lo = higherIsBetter ? bad : good
  const hi = higherIsBetter ? good : bad
  const pct = ((value - lo) / (hi - lo)) * 100
  return clamp(higherIsBetter ? pct : 100 - clamp(pct))
}

// average only the non-null contributions (so a missing metric doesn't tank the score)
function avg(parts: (number | null)[]): number | null {
  const live = parts.filter((p): p is number => p !== null)
  if (!live.length) return null
  return clamp(live.reduce((a, b) => a + b, 0) / live.length)
}

export async function GET(req: NextRequest) {
  const sym = (req.nextUrl.searchParams.get("sym") || "").trim().toUpperCase()
  if (!sym) return NextResponse.json({ ok: false, error: "sym required" }, { status: 400 })

  try {
    const sql = neon(process.env.DATABASE_URL!)

    const [rows, peerRows, flagRows] = await Promise.all([
      sql`SELECT nse_symbol, name, industry, industry_group, current_price, market_cap,
                 pe_ratio, roce, roce_3yr_avg, roe, roe_3yr_avg, opm_pct,
                 debt_to_equity, interest_coverage,
                 sales_growth_3y, pat_growth_1y, eps_growth_3y,
                 business_dna_score, business_dna_grade,
                 earnings_score, earnings_category,
                 smart_money_score, smart_money_signal,
                 bulk_net_flow, bulk_deal_count,
                 return_3m, return_6m, sector_rotation_score
          FROM stock_fundamentals WHERE UPPER(nse_symbol) = ${sym} LIMIT 1`,
      // sector PE median for valuation-vs-peers (uses industry_group when present)
      sql`SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY pe_ratio) AS sector_pe
          FROM stock_fundamentals
          WHERE pe_ratio > 0 AND pe_ratio < 200
            AND industry_group = (SELECT industry_group FROM stock_fundamentals WHERE UPPER(nse_symbol) = ${sym} LIMIT 1)`,
      sql`SELECT n_funds, funds, first_seen, total_weight
          FROM mf_conviction_flags
          WHERE UPPER(nse_symbol) = ${sym} AND expires_on >= CURRENT_DATE
          ORDER BY first_seen DESC LIMIT 1`,
    ])

    const f = (rows[0] || {}) as any
    if (!rows.length) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 })

    const sectorPe = num((peerRows[0] as any)?.sector_pe)
    const flag = (flagRows[0] || null) as any

    // Detect lenders — banks/NBFCs/finance carry high D/E by design (they borrow to lend),
    // so the normal debt band would wrongly tank every financial. For them, skip the debt
    // and interest-coverage bands and lean on ROE + DNA instead.
    const sectorText = `${f.industry || ""} ${f.industry_group || ""}`.toLowerCase()
    const isFinance = /financ|bank|nbfc|lend|insur|capital market|housing finance/.test(sectorText)

    // ── QUALITY ── ROCE, ROE, debt, interest coverage, margins, DNA score
    const qParts = {
      roce:       band(num(f.roce), 8, 25),
      roe:        band(num(f.roe), 8, 22),
      opm:        band(num(f.opm_pct), 5, 25),
      debt:       isFinance ? null : band(num(f.debt_to_equity), 1.5, 0.2, false),   // lower better; N/A for lenders
      intCover:   isFinance ? null : band(num(f.interest_coverage), 1.5, 8),         // N/A for lenders
      dna:        num(f.business_dna_score),                       // already 0..100-ish
    }
    const quality = avg(Object.values(qParts))

    // ── SMART MONEY ── your precomputed smart_money_score + bulk flow + MF conviction
    const smParts = {
      smartScore: num(f.smart_money_score),
      bulkFlow:   num(f.bulk_net_flow) !== null ? (Number(f.bulk_net_flow) > 0 ? 70 : 35) : null,
      conviction: flag ? clamp(60 + Number(flag.n_funds || 0) * 12) : null,  // funds initiating => boost
    }
    const smartMoney = avg(Object.values(smParts))

    // ── VALUATION ── PE vs sector median (cheaper than peers => higher score)
    const pe = num(f.pe_ratio)
    let valuation: number | null = null
    if (pe !== null && pe > 0 && sectorPe && sectorPe > 0) {
      // pe at 50% of sector => ~85, at sector median => 50, at 2x sector => ~15
      const ratio = pe / sectorPe
      valuation = clamp(100 - (ratio - 0.5) * 70)
    } else if (pe !== null && pe > 0) {
      valuation = band(pe, 60, 12, false)  // fallback absolute band, lower PE better
    }

    // ── MOMENTUM ── returns, earnings acceleration, growth, sector rotation
    const mParts = {
      ret3m:      band(num(f.return_3m), -10, 30),
      ret6m:      band(num(f.return_6m), -15, 45),
      earnings:   num(f.earnings_score),
      patGrowth:  band(num(f.pat_growth_1y), 0, 40),
      sectorRot:  num(f.sector_rotation_score),
    }
    const momentum = avg(Object.values(mParts))

    // ── COMPOSITE ── weighted blend (quality + smart money lead; honest, not a buy call)
    const blend = avg([
      quality, quality,          // weight quality 2x
      smartMoney, smartMoney,    // weight smart money 2x
      valuation,
      momentum,
    ])

    // one-line plain-language read, generated from the sub-scores
    const read = buildRead({ quality, smartMoney, valuation, momentum })

    return NextResponse.json({
      ok: true,
      symbol: sym,
      name: f.name,
      industry: f.industry_group || f.industry,
      price: num(f.current_price),
      market_cap: num(f.market_cap),
      convergence: blend,
      read,
      subscores: {
        quality:    { score: quality,    inputs: { ...cleanInputs(qParts, f, ["roce", "roe", "opm_pct", "debt_to_equity", "interest_coverage", "business_dna_grade"]), is_lender: isFinance } },
        smartMoney: { score: smartMoney, inputs: { smart_money_signal: f.smart_money_signal, bulk_net_flow: num(f.bulk_net_flow), bulk_deal_count: num(f.bulk_deal_count), conviction_funds: flag ? Number(flag.n_funds) : 0, funds: flag?.funds ?? null } },
        valuation:  { score: valuation,  inputs: { pe_ratio: pe, sector_pe: sectorPe } },
        momentum:   { score: momentum,   inputs: { return_3m: num(f.return_3m), return_6m: num(f.return_6m), earnings_category: f.earnings_category, pat_growth_1y: num(f.pat_growth_1y), sector_rotation_score: num(f.sector_rotation_score) } },
      },
      disclaimer: "Research signal, not a buy call. Each sub-score is computed from real fundamentals; tap to see inputs.",
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}

function cleanInputs(parts: Record<string, number | null>, f: any, keys: string[]) {
  const out: Record<string, any> = {}
  for (const k of keys) out[k] = num(f[k]) ?? f[k] ?? null
  return out
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
  // join with em-dash separators, capitalize first
  const txt = bits.join(" · ")
  return txt.charAt(0).toUpperCase() + txt.slice(1)
}
