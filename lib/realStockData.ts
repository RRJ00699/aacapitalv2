// lib/realStockData.ts
// Pulls REAL fundamentals (stock_fundamentals) and REAL ownership (shareholding_history)
// for a symbol, mapped to the exact keys the UI/SimulatedProvider use. /api/stock merges
// these over the simulated values so the workbook shows real data wherever it exists and
// only falls back to sr() for fields with genuinely no source.
import { neon } from "@neondatabase/serverless"

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

// keep only defined, non-null entries so a merge never overwrites a good value with null
function nn<T extends Record<string, any>>(o: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(o).filter(([, v]) => v !== null && v !== undefined &&
      !(Array.isArray(v) && v.length === 0))
  ) as Partial<T>
}

export async function getRealStockData(symbol: string): Promise<{ realFund: Record<string, any>; realOwn: Record<string, any> | null }> {
  const sym = symbol.toUpperCase()
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const [fundRows, shRows] = await Promise.all([
      sql`SELECT roce, roe, pe_ratio, pb_ratio, debt_equity, operating_margin,
                 sales_growth_3y, pat_growth, market_cap
          FROM stock_fundamentals WHERE UPPER(nse_symbol) = ${sym} LIMIT 1`,
      sql`SELECT quarter, promoter_pct, promoter_pledge, fii_pct, dii_pct, mf_pct
          FROM shareholding_history WHERE UPPER(nse_symbol) = ${sym}
          ORDER BY quarter ASC LIMIT 12`,
    ])

    const f = (fundRows[0] || {}) as any
    const realFund = nn({
      pe:              num(f.pe_ratio),
      pb:              num(f.pb_ratio),
      roe:             num(f.roe),
      roce:            num(f.roce),
      debtToEquity:    num(f.debt_equity),
      operatingMargin: num(f.operating_margin),
      revenueCAGR3Y:   num(f.sales_growth_3y),
      patCAGR3Y:       num(f.pat_growth),
      mcap:            num(f.market_cap),
    })

    let realOwn: Record<string, any> | null = null
    if (shRows.length) {
      const latest = shRows[shRows.length - 1] as any
      const fii = (latest.fii_pct != null) ? num(latest.fii_pct) : null
      const dii = (latest.dii_pct != null) ? num(latest.dii_pct) : null
      realOwn = nn({
        promoterPct:    num(latest.promoter_pct),
        pledgePct:      num(latest.promoter_pledge),
        fiiHistory:     shRows.map((r: any) => num(r.fii_pct)).filter((v: any) => v !== null),
        diiHistory:     shRows.map((r: any) => num(r.dii_pct)).filter((v: any) => v !== null),
        mfHistory:      shRows.map((r: any) => num(r.mf_pct)).filter((v: any) => v !== null),
        institutionPct: (fii !== null || dii !== null) ? (fii ?? 0) + (dii ?? 0) : null,
      })
      if (realOwn && Object.keys(realOwn).length === 0) realOwn = null
    }

    return { realFund, realOwn }
  } catch {
    // any DB error → fall back entirely to simulated (route handles realOwn === null)
    return { realFund: {}, realOwn: null }
  }
}
