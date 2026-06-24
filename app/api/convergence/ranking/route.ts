// app/api/convergence/ranking/route.ts
// Serves the precomputed 5-factor convergence ranking (compute_convergence_ranking.py)
// for the Today screen's "Top Convergence" panel.
import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const sql = neon(process.env.DATABASE_URL!)
  const limit = Math.min(50, parseInt(new URL(req.url).searchParams.get("limit") || "15"))
  try {
    const rows = await sql`
      SELECT symbol, name, convergence, business, earnings, technical, smart_money, sector, action
      FROM convergence_ranking
      ORDER BY convergence DESC NULLS LAST
      LIMIT ${limit}
    `
    return NextResponse.json({ ok: true, data: rows, count: rows.length })
  } catch (err: any) {
    // Table not built yet → empty (panel shows its empty state rather than erroring)
    return NextResponse.json({ ok: false, error: err.message, data: [] }, { status: 200 })
  }
}
