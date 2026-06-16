// app/api/ipo/intelligence/route.ts
// Serves IPO probability engine output from ipo_intelligence table
// Used by IPO Command Center UI

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const sql = db()
  const { searchParams } = new URL(req.url)
  const name   = searchParams.get("name") || ""
  const limit  = Math.min(50, parseInt(searchParams.get("limit") || "20"))
  const action = searchParams.get("action") || ""   // MOMENTUM CHASE, VALUE DIP BUY, AVOID

  try {
    const rows = await sql`
      SELECT
        id,
        company_name,
        symbol,
        sector,
        issue_price,
        listing_date,
        listing_gap_pct,
        archetype,

        -- LQI & probability
        lqi_final,
        prob_10pct_profit,
        prob_loss_gt10,
        expected_return,
        confidence_level,
        suggested_action,

        -- Subscription
        qib_subscription_x,
        nii_subscription_x,
        rii_subscription_x,
        total_subscription_x,

        -- GMP
        gmp_percentage,
        gmp_momentum,

        -- Deal structure
        ofs_pct,
        issue_size_cr,
        brlm_names,
        anchor_quality,

        -- Valuation
        ipo_pe,
        peer_median_pe,

        -- Post-listing returns
        return_day7,
        return_day30,
        return_day90,
        return_cmp,
        max_upside_pct,
        max_drawdown_day30,

        -- Similar IPOs (stored as JSONB)
        similar_ipos,

        updated_at
      FROM ipo_intelligence
      WHERE
        (${name} = '' OR company_name ILIKE ${'%' + name + '%'})
        AND (${action} = '' OR suggested_action = ${action})
        AND lqi_final IS NOT NULL
      ORDER BY lqi_final DESC NULLS LAST
      LIMIT ${limit}
    `

    const ipos = rows.map((r: any) => ({
      id:            r.id,
      company_name:  r.company_name,
      symbol:        r.symbol,
      sector:        r.sector,
      issue_price:   Number(r.issue_price   || 0),
      listing_date:  r.listing_date,
      listing_gain:  Number(r.listing_gap_pct || 0),
      archetype:     r.archetype,

      lqi:           Number(r.lqi_final          || 0),
      p_above_10:    Number(r.prob_10pct_profit   || 0),
      p_loss:        Number(r.prob_loss_gt10      || 0),
      exp_return:    Number(r.expected_return     || 0),
      confidence:    r.confidence_level,
      action:        r.suggested_action,

      qib_x:         r.qib_subscription_x  ? Number(r.qib_subscription_x)  : null,
      nii_x:         r.nii_subscription_x  ? Number(r.nii_subscription_x)  : null,
      retail_x:      r.rii_subscription_x  ? Number(r.rii_subscription_x)  : null,
      total_x:       r.total_subscription_x? Number(r.total_subscription_x): null,

      gmp_pct:       r.gmp_percentage ? Number(r.gmp_percentage) : null,
      gmp_momentum:  r.gmp_momentum,

      ofs_pct:       r.ofs_pct     ? Number(r.ofs_pct)     : null,
      issue_size:    r.issue_size_cr? Number(r.issue_size_cr): null,
      brlm:          r.brlm_names,
      anchor:        r.anchor_quality,

      ipo_pe:        r.ipo_pe         ? Number(r.ipo_pe)         : null,
      peer_pe:       r.peer_median_pe ? Number(r.peer_median_pe) : null,

      return_d7:     r.return_day7   ? Number(r.return_day7)   : null,
      return_d30:    r.return_day30  ? Number(r.return_day30)  : null,
      return_d90:    r.return_day90  ? Number(r.return_day90)  : null,
      return_cmp:    r.return_cmp    ? Number(r.return_cmp)    : null,
      max_up:        r.max_upside_pct     ? Number(r.max_upside_pct)     : null,
      max_down:      r.max_drawdown_day30 ? Number(r.max_drawdown_day30) : null,

      similar_ipos:  (() => {
        try { return typeof r.similar_ipos === "string" ? JSON.parse(r.similar_ipos) : (r.similar_ipos || []) }
        catch { return [] }
      })(),

      updated_at: r.updated_at,
    }))

    // Summary stats
    const total    = ipos.length
    const momentum = ipos.filter(i => i.action === "MOMENTUM CHASE").length
    const value    = ipos.filter(i => i.action === "VALUE DIP BUY").length
    const avoid    = ipos.filter(i => i.action === "AVOID").length
    const avgLqi   = total > 0 ? Math.round(ipos.reduce((s, i) => s + i.lqi, 0) / total) : 0

    return NextResponse.json({
      ok:       true,
      count:    total,
      summary:  { momentum, value, avoid, avg_lqi: avgLqi },
      ipos,
      fetched_at: new Date().toISOString(),
    })

  } catch (err: any) {
    console.error("[ipo/intelligence]", err)
    return NextResponse.json({ ok: false, error: err.message, ipos: [] }, { status: 500 })
  }
}

// POST — trigger a re-score for a specific IPO
export async function POST(req: NextRequest) {
  try {
    const { company_name } = await req.json()
    if (!company_name) {
      return NextResponse.json({ ok: false, error: "company_name required" }, { status: 400 })
    }
    // Note: actual re-scoring happens via Python engine
    // This endpoint just returns current data for the named IPO
    const sql  = db()
    const rows = await sql`
      SELECT company_name, lqi_final, prob_10pct_profit, suggested_action, updated_at
      FROM ipo_intelligence
      WHERE company_name ILIKE ${'%' + company_name + '%'}
      LIMIT 1
    `
    if (!rows.length) {
      return NextResponse.json({ ok: false, error: "IPO not found" }, { status: 404 })
    }
    return NextResponse.json({ ok: true, ipo: rows[0] })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
