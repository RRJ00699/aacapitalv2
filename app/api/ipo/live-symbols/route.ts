import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

// Which IPOs are streaming live right now? = distinct symbols with rows in the last 20 min.
export async function GET() {
  try {
    const rows = await sql`
      SELECT symbol, MAX(recorded_at) AS last_at, COUNT(*) AS pts
      FROM ipo_tick_feed
      WHERE recorded_at >= NOW() - INTERVAL '20 minutes'
      GROUP BY symbol
      ORDER BY MAX(recorded_at) DESC
    `.catch(() => [] as any[])
    return NextResponse.json({ symbols: rows, count: (rows as any[]).length })
  } catch (e: any) {
    return NextResponse.json({ symbols: [], count: 0, error: String(e?.message || e) }, { status: 500 })
  }
}
