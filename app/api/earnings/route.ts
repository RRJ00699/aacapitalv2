// app/api/earnings/route.ts
// Earnings Calendar — upcoming results + surprise history
// GET /api/earnings?view=upcoming&days=30
// GET /api/earnings?view=surprises&symbol=DIXON
// GET /api/earnings?view=watchlist  (symbols with convergence >= 60)

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const view   = req.nextUrl.searchParams.get("view") ?? "upcoming"
  const symbol = req.nextUrl.searchParams.get("symbol")?.toUpperCase()
  const days   = parseInt(req.nextUrl.searchParams.get("days") ?? "30")
  const sql    = db()

  try {

    // ── Upcoming results ───────────────────────────────────────────────────
    if (view === "upcoming") {
      const rows = await sql`
        SELECT
          ee.nse_symbol,
          ee.company_name,
          ee.result_date,
          ee.quarter,
          ee.est_eps,
          ee.status,
          f.business_dna_score,
          f.business_dna_grade,
          f.earnings_score,
          f.smart_money_score,
          -- Convergence proxy
          LEAST(100, GREATEST(0, ROUND((
            COALESCE(f.business_dna_score, 50) * 0.30 +
            COALESCE(f.earnings_score, 50) * 0.35 +
            COALESCE(f.smart_money_score, 50) * 0.20 +
            COALESCE(f.sector_rotation_score, 50) * 0.15
          )::numeric, 0))) AS convergence_proxy,
          -- Days until results
          (ee.result_date - CURRENT_DATE) AS days_away,
          -- Last surprise
          (SELECT es2.surprise_type FROM earnings_signals es2
           WHERE es2.nse_symbol = ee.nse_symbol
           ORDER BY es2.created_at DESC LIMIT 1) AS last_surprise,
          (SELECT es2.consecutive_beats FROM earnings_signals es2
           WHERE es2.nse_symbol = ee.nse_symbol
           ORDER BY es2.created_at DESC LIMIT 1) AS consecutive_beats
        FROM earnings_events ee
        LEFT JOIN stock_fundamentals f ON f.nse_symbol = ee.nse_symbol
        WHERE ee.result_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '${days} days'
          AND ee.status = 'UPCOMING'
        ORDER BY ee.result_date ASC, convergence_proxy DESC NULLS LAST
        LIMIT 50
      `
      return NextResponse.json({ ok: true, view: "upcoming", count: rows.length, data: rows })
    }

    // ── Surprise history for a symbol ─────────────────────────────────────
    if (view === "surprises" && symbol) {
      const rows = await sql`
        SELECT
          ee.quarter,
          ee.result_date,
          ee.est_eps,
          ee.actual_eps,
          ee.eps_surprise_pct,
          ee.surprise_type,
          ee.guidance_change,
          es.consecutive_beats,
          es.acceleration,
          es.margin_trend,
          es.signal_summary
        FROM earnings_events ee
        LEFT JOIN earnings_signals es ON es.nse_symbol = ee.nse_symbol
          AND es.quarter = ee.quarter
        WHERE ee.nse_symbol = ${symbol}
          AND ee.status IN ('DECLARED', 'VERIFIED')
        ORDER BY ee.result_date DESC
        LIMIT 8
      `
      return NextResponse.json({ ok: true, view: "surprises", symbol, data: rows })
    }

    // ── High-conviction watchlist earnings ────────────────────────────────
    if (view === "watchlist") {
      const rows = await sql`
        SELECT
          ee.nse_symbol,
          ee.company_name,
          ee.result_date,
          ee.quarter,
          f.business_dna_grade,
          f.business_dna_score,
          f.earnings_score,
          (ee.result_date - CURRENT_DATE) AS days_away
        FROM earnings_events ee
        JOIN stock_fundamentals f ON f.nse_symbol = ee.nse_symbol
        WHERE ee.result_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '45 days'
          AND ee.status = 'UPCOMING'
          AND f.business_dna_score >= 65
          AND f.earnings_score >= 50
        ORDER BY f.business_dna_score DESC, ee.result_date ASC
        LIMIT 20
      `
      return NextResponse.json({ ok: true, view: "watchlist", count: rows.length, data: rows })
    }

    return NextResponse.json({ error: `Unknown view: ${view}` }, { status: 400 })

  } catch (err: any) {
    console.error("earnings:", err.message)
    if (err.message?.includes("does not exist")) {
      return NextResponse.json({
        ok: false,
        error: "Run earnings-calendar.sql migration first",
        data: []
      }, { status: 503 })
    }
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}

// POST: upsert earnings event (called by scraper script)
export async function POST(req: NextRequest) {
  const body = await req.json()
  const { symbol, company_name, result_date, quarter,
          est_eps, actual_eps, eps_surprise_pct, surprise_type,
          guidance_change, status, source } = body

  if (!symbol || !quarter) {
    return NextResponse.json({ error: "symbol and quarter required" }, { status: 400 })
  }

  const sql = db()

  await sql`
    INSERT INTO earnings_events (
      nse_symbol, company_name, result_date, quarter,
      est_eps, actual_eps, eps_surprise_pct, surprise_type,
      guidance_change, status, source, updated_at
    ) VALUES (
      ${symbol}, ${company_name ?? null}, ${result_date ?? null}, ${quarter},
      ${est_eps ?? null}, ${actual_eps ?? null},
      ${eps_surprise_pct ?? null}, ${surprise_type ?? null},
      ${guidance_change ?? null}, ${status ?? "UPCOMING"},
      ${source ?? "MANUAL"}, NOW()
    )
    ON CONFLICT (nse_symbol, quarter) DO UPDATE SET
      result_date = COALESCE(EXCLUDED.result_date, earnings_events.result_date),
      actual_eps = COALESCE(EXCLUDED.actual_eps, earnings_events.actual_eps),
      eps_surprise_pct = COALESCE(EXCLUDED.eps_surprise_pct, earnings_events.eps_surprise_pct),
      surprise_type = COALESCE(EXCLUDED.surprise_type, earnings_events.surprise_type),
      guidance_change = COALESCE(EXCLUDED.guidance_change, earnings_events.guidance_change),
      status = COALESCE(EXCLUDED.status, earnings_events.status),
      updated_at = NOW()
  `

  return NextResponse.json({ ok: true, symbol, quarter })
}
