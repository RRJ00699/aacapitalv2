// app/api/management-commentary/scrape/route.ts
// Triggers GitHub Actions on-demand commentary scraper
// Falls back to showing cached data if available

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

const db = () => neon(process.env.DATABASE_URL!)

export async function POST(req: NextRequest) {
  try {
    const { symbol, force } = await req.json()
    if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })
    const sym = symbol.toUpperCase().trim()
    const sql = db()

    // Check cache first (unless force=true)
    if (!force) {
      const cached = await sql`
        SELECT nse_symbol, quarter, management_tone, sentiment_score,
               mgmt_quality_score, confidence, updated_at
        FROM management_commentary
        WHERE nse_symbol = ${sym}
        ORDER BY updated_at DESC LIMIT 1
      `
      if (cached.length > 0) {
        return NextResponse.json({ ok: true, cached: true, data: cached[0] })
      }
    }

    // Trigger GitHub Actions workflow_dispatch
    const GITHUB_TOKEN = process.env.GITHUB_TOKEN
    const REPO         = process.env.GITHUB_REPO || "RRJ00699/aacapitalv2"

    if (GITHUB_TOKEN) {
      const ghRes = await fetch(
        `https://api.github.com/repos/${REPO}/actions/workflows/on-demand-commentary.yml/dispatches`,
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${GITHUB_TOKEN}`,
            "Accept":        "application/vnd.github+json",
            "Content-Type":  "application/json",
          },
          body: JSON.stringify({
            ref:    "main",
            inputs: { symbols: sym, force: force ? "true" : "false" },
          }),
        }
      )

      if (ghRes.ok || ghRes.status === 204) {
        return NextResponse.json({
          ok:      true,
          queued:  true,
          message: `Commentary scraper triggered for ${sym}. Results in ~60 seconds. Refresh this page after.`,
        })
      }
    }

    // No GitHub token — show instruction
    const latest = await sql`
      SELECT * FROM management_commentary WHERE nse_symbol = ${sym}
      ORDER BY updated_at DESC LIMIT 1
    `
    if (latest.length > 0) {
      return NextResponse.json({ ok: true, data: latest[0] })
    }

    return NextResponse.json({
      ok:          false,
      instruction: true,
      message:     `python _scripts/score_management_commentary.py --symbols ${sym}`,
      error:       `No commentary for ${sym}. Add GITHUB_TOKEN to Vercel env vars for on-demand scraping, or run locally.`,
    }, { status: 404 })

  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
