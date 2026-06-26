import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

//  /api/financial-dna
// Serves the Financial DNA engine output (financial_dna table, computed by
// _scripts/compute_financial_dna.py from 10yr annual_financials) to the workboard.
//   ?symbol=RELIANCE   ->  grade, 0-100 DNA score, 7 sub-scores + risk, green/red flags.
// IMPORTANT FRAMING: DNA is a QUALITY / RISK lens, validated as such (higher grades =
// lower volatility, shallower drawdowns, fewer blow-ups). It is NOT a return predictor
// (raw returns inverted over 2021-26). The UI must present it as durability/risk, not alpha.

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const symbol = (req.nextUrl.searchParams.get("symbol") || "").trim().toUpperCase()
    if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

    const rows = await sql`
      SELECT symbol, company_name, dna_score, grade,
             growth, profitability, cashflow, balancesheet, capalloc,
             efficiency, earnings_quality, risk,
             green_flags, red_flags, years, computed_at
      FROM financial_dna
      WHERE symbol = ${symbol}
      LIMIT 1`

    if (!rows.length) {
      // not graded yet (e.g. missing/shallow annual_financials) — explicit, honest empty state
      return NextResponse.json({ symbol, graded: false }, { headers: { "Cache-Control": "public, max-age=3600" } })
    }

    const r: any = rows[0]
    const parseJson = (v: any) => {
      if (v == null) return []
      if (Array.isArray(v)) return v
      try { return JSON.parse(v) } catch { return [] }
    }
    // green_flags: string[]   red_flags: [text, severity][]
    const red = parseJson(r.red_flags).map((x: any) =>
      Array.isArray(x) ? { text: String(x[0]), severity: String(x[1] || "med") } : { text: String(x), severity: "med" })

    return NextResponse.json({
      symbol: r.symbol,
      graded: true,
      company_name: r.company_name || null,
      dna_score: num(r.dna_score),
      grade: r.grade || null,
      years: num(r.years),
      computed_at: r.computed_at || null,
      subs: {
        growth: num(r.growth),
        profitability: num(r.profitability),
        cashflow: num(r.cashflow),
        balancesheet: num(r.balancesheet),
        capalloc: num(r.capalloc),
        efficiency: num(r.efficiency),
        earnings_quality: num(r.earnings_quality),
        risk: num(r.risk),
      },
      green_flags: parseJson(r.green_flags).map((x: any) => String(x)),
      red_flags: red,
    }, { headers: { "Cache-Control": "public, max-age=3600" } })
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "failed" }, { status: 500 })
  }
}
