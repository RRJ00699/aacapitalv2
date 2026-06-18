// app/api/management-commentary/scrape/route.ts
// Triggers Screener.in scraper for a symbol and saves to Neon
// Called by management-commentary-panel Extract button
// No Claude API needed — uses local NLP scoring

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"
export const maxDuration = 30

const db = () => neon(process.env.DATABASE_URL!)

export async function POST(req: NextRequest) {
  try {
    const { symbol, force } = await req.json()
    if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })

    const sql = db()
    const sym = symbol.toUpperCase().trim()

    // Check if we already have data this quarter (unless force=true)
    if (!force) {
      const existing = await sql`
        SELECT nse_symbol, quarter, management_tone, sentiment_score
        FROM management_commentary
        WHERE nse_symbol = ${sym}
        ORDER BY updated_at DESC LIMIT 1
      `
      if (existing.length > 0) {
        return NextResponse.json({ ok: true, cached: true, data: existing[0] })
      }
    }

    // This endpoint can't run Python directly on Vercel
    // Return instruction to run locally + show what we have in DB
    const latest = await sql`
      SELECT * FROM management_commentary
      WHERE nse_symbol = ${sym}
      ORDER BY updated_at DESC LIMIT 1
    `

    if (latest.length > 0) {
      return NextResponse.json({ ok: true, data: latest[0] })
    }

    return NextResponse.json({
      ok: false,
      error: `No commentary found for ${sym}. Run locally: python _scripts/score_management_commentary.py --symbols ${sym}`,
      instruction: `python _scripts/score_management_commentary.py --symbols ${sym}`,
    }, { status: 404 })

  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
