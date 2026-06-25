// app/api/stock/mf-holders/route.ts
// Which mutual funds hold (or just initiated) a given stock — the reverse lookup behind
// the 💎 conviction badge. Reads mf_scheme_holdings (latest snapshot per fund) + the
// mf_conviction_flags table (fresh initiations). Honest, data-only — no buy calls.

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const sql = neon(process.env.DATABASE_URL!)
  const sym = (req.nextUrl.searchParams.get("sym") || "").toUpperCase().trim()
  if (!sym) return NextResponse.json({ ok: false, error: "sym required" }, { status: 400 })

  try {
    // Latest holding row per fund for this stock (most recent disclosure each scheme has).
    const holders = await sql`
      WITH latest AS (
        SELECT DISTINCT ON (scheme_name)
          scheme_name, amc_name, month AS as_of, portfolio_weight_pct
        FROM mf_scheme_holdings
        WHERE nse_symbol = ${sym}
        ORDER BY scheme_name, month DESC
      ),
      first_seen AS (
        -- when did each fund FIRST start holding this stock (initiation date)
        SELECT scheme_name, MIN(month) AS since
        FROM mf_scheme_holdings
        WHERE nse_symbol = ${sym}
        GROUP BY scheme_name
      )
      SELECT l.scheme_name, l.amc_name, l.as_of, l.portfolio_weight_pct, f.since
      FROM latest l
      LEFT JOIN first_seen f ON f.scheme_name = l.scheme_name
      ORDER BY l.portfolio_weight_pct DESC NULLS LAST
    `

    // Fresh conviction flag (a fund initiated within the edge window)
    const flag = await sql`
      SELECT n_funds, funds, first_seen, expires_on
      FROM mf_conviction_flags
      WHERE nse_symbol = ${sym} AND expires_on >= CURRENT_DATE
      LIMIT 1
    `

    const convFunds: string[] = flag.length && flag[0].funds
      ? String(flag[0].funds).split("·").map((s: string) => s.trim())
      : []

    return NextResponse.json({
      ok: true,
      symbol: sym,
      held_by: holders.length,
      is_new_conviction: flag.length > 0,
      conviction_first_seen: flag.length ? flag[0].first_seen : null,
      holders: holders.map((h: any) => ({
        fund: h.scheme_name,
        amc: h.amc_name,
        weight_pct: h.portfolio_weight_pct != null ? Number(h.portfolio_weight_pct) : null,
        as_of: h.as_of,
        since: h.since,
        // is THIS fund one that freshly initiated (in the conviction window)?
        new_conviction: convFunds.some(cf => cf && h.scheme_name && h.scheme_name.includes(cf.slice(0, 12))),
      })),
    })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message, holders: [] }, { status: 500 })
  }
}
