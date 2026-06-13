// app/api/sector-rotation/route.ts
// Sector Rotation Engine — weekly rankings with FII flow proxy
// GET /api/sector-rotation?view=rankings   — full ranked list
// GET /api/sector-rotation?view=hot        — top 5 sectors to rotate in
// GET /api/sector-rotation?view=cold       — sectors to avoid/exit
// GET /api/sector-rotation?sector=Defense  — stocks in a sector

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const sql = db()
  const view   = req.nextUrl.searchParams.get("view") ?? "rankings"
  const sector = req.nextUrl.searchParams.get("sector")

  try {
    // ── Sector stocks drill-down ─────────────────────────────────────────────
    if (sector) {
      const stocks = await sql`
        SELECT
          f.nse_symbol, f.name, f.current_price, f.market_cap,
          f.business_dna_score, f.business_dna_grade,
          f.earnings_score, f.earnings_category,
          f.return_3m, f.return_6m,
          f.roce, f.sales_growth_3y, f.debt_to_equity,
          s.smart_money_score, s.smart_money_signal,
          s.net_flow_3m, s.tier1_deal_count
        FROM stock_fundamentals f
        LEFT JOIN smart_money_summary s ON s.nse_symbol = f.nse_symbol
        WHERE f.industry_group ILIKE ${'%' + sector + '%'}
          AND f.market_cap > 100
        ORDER BY f.business_dna_score DESC NULLS LAST, f.market_cap DESC
        LIMIT 30
      `
      return NextResponse.json({ ok: true, sector, stocks })
    }

    // ── Full rankings ─────────────────────────────────────────────────────────
    if (view === "rankings") {
      const sectors = await sql`
        SELECT
          industry_group, stock_count,
          return_3m, return_6m,
          avg_roce, avg_sales_growth_3y, avg_pat_growth,
          avg_pe, avg_pbv, total_mcap_cr,
          rotation_score, rotation_signal, rotation_trend,
          top_stocks
        FROM sector_rotation
        ORDER BY rotation_score DESC
      `
      return NextResponse.json({ ok: true, sectors })
    }

    // ── Hot sectors (rotate in) ───────────────────────────────────────────────
    if (view === "hot") {
      const hot = await sql`
        SELECT industry_group, rotation_score, rotation_signal,
               return_3m, return_6m, avg_roce, avg_sales_growth_3y,
               stock_count, top_stocks
        FROM sector_rotation
        WHERE rotation_score >= 60
        ORDER BY rotation_score DESC
        LIMIT 8
      `

      // For each hot sector, get the best stock
      const enriched = await Promise.all(hot.map(async (s) => {
        const best = await sql`
          SELECT nse_symbol, name, business_dna_score, business_dna_grade,
                 earnings_category, return_6m, roce
          FROM stock_fundamentals
          WHERE industry_group = ${s.industry_group}
            AND business_dna_score >= 60
          ORDER BY business_dna_score DESC NULLS LAST
          LIMIT 3
        `.catch(() => [])
        return { ...s, best_stocks: best }
      }))

      return NextResponse.json({ ok: true, hot_sectors: enriched })
    }

    // ── Cold sectors (rotate out) ─────────────────────────────────────────────
    if (view === "cold") {
      const cold = await sql`
        SELECT industry_group, rotation_score, rotation_signal,
               return_3m, return_6m, avg_roce, stock_count
        FROM sector_rotation
        WHERE rotation_score < 40
        ORDER BY rotation_score ASC
        LIMIT 8
      `
      return NextResponse.json({ ok: true, cold_sectors: cold })
    }

    // ── Capital flow map — where is money going? ──────────────────────────────
    if (view === "flow_map") {
      const flowMap = await sql`
        SELECT
          sr.industry_group,
          sr.rotation_score,
          sr.rotation_signal,
          sr.return_3m,
          sr.return_6m,
          sr.avg_roce,
          sr.total_mcap_cr,
          -- Smart money flow into this sector (from bulk/block deals)
          COALESCE(SUM(sms.net_flow_3m), 0) as sector_net_flow_3m,
          COALESCE(SUM(sms.tier1_deal_count), 0) as sector_tier1_deals,
          COUNT(f.nse_symbol) as stocks_with_sm_data
        FROM sector_rotation sr
        LEFT JOIN stock_fundamentals f ON f.industry_group = sr.industry_group
        LEFT JOIN smart_money_summary sms ON sms.nse_symbol = f.nse_symbol
        GROUP BY sr.industry_group, sr.rotation_score, sr.rotation_signal,
                 sr.return_3m, sr.return_6m, sr.avg_roce, sr.total_mcap_cr
        ORDER BY sr.rotation_score DESC
      `
      return NextResponse.json({ ok: true, flow_map: flowMap })
    }

    // ── Summary ───────────────────────────────────────────────────────────────
    const summary = await sql`
      SELECT
        COUNT(*) as total_sectors,
        COUNT(CASE WHEN rotation_score >= 60 THEN 1 END) as hot,
        COUNT(CASE WHEN rotation_score BETWEEN 40 AND 59 THEN 1 END) as neutral,
        COUNT(CASE WHEN rotation_score < 40 THEN 1 END) as cold,
        MAX(rotation_score) as top_score,
        MIN(rotation_score) as bottom_score
      FROM sector_rotation
    `
    return NextResponse.json({ ok: true, summary: summary[0] })

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    if (msg.includes("does not exist")) {
      return NextResponse.json({
        ok: false,
        error: "Sector data not imported. Run: node scripts/sector-rotation-import.mjs"
      }, { status: 503 })
    }
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}
