// app/api/alert-history/route.ts
// Returns past convergence alerts stored in audit_log

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const limit = parseInt(req.nextUrl.searchParams.get("limit") ?? "20")
  try {
    const sql = db()
    const alerts = await sql`
      SELECT
        details->>'tradingsymbol' as symbol,
        details->>'alert_tier' as alert_tier,
        details->>'convergence_score' as convergence_score,
        details->>'engines_triggered' as engines_triggered,
        created_at
      FROM audit_log
      WHERE action = 'convergence_alert'
        OR (action = 'premarket_brief' AND details->>'six_sigma' IS NOT NULL)
      ORDER BY created_at DESC
      LIMIT ${limit}
    `.catch(() => [])
    return NextResponse.json({ ok: true, alerts })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : "error" })
  }
}
