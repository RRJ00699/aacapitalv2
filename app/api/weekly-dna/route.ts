// app/api/weekly-dna/route.ts
// Returns weekly DNA features for a single stock

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol")
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 })

  try {
    const sql = db()
    const rows = await sql`
      SELECT * FROM weekly_dna WHERE tradingsymbol = ${symbol.toUpperCase()} LIMIT 1
    `.catch(() => [])

    if (!rows.length) return NextResponse.json({ ok: false, error: "No weekly data yet" })
    return NextResponse.json({ ok: true, data: rows[0] })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : "error" })
  }
}
