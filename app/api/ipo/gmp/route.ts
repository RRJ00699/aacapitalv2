import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

// Store GMP update for an IPO
export async function POST(req: NextRequest) {
  try {
    const { name, gmpPrice, gmpPct } = await req.json()
    if (!name || gmpPrice === undefined) {
      return NextResponse.json({ error: "name and gmpPrice required" }, { status: 400 })
    }

    const sql = getDb()
    await sql`
      CREATE TABLE IF NOT EXISTS ipo_gmp (
        id SERIAL PRIMARY KEY,
        ipo_name TEXT NOT NULL,
        gmp_price NUMERIC NOT NULL,
        gmp_pct NUMERIC,
        recorded_at TIMESTAMPTZ DEFAULT NOW()
      )
    `
    await sql`
      INSERT INTO ipo_gmp (ipo_name, gmp_price, gmp_pct)
      VALUES (${name}, ${gmpPrice}, ${gmpPct ?? 0})
    `
    return NextResponse.json({ ok: true })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

// Get GMP history for an IPO
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const name = searchParams.get("name")
    if (!name) return NextResponse.json({ error: "name required" }, { status: 400 })

    const sql = getDb()
    await sql`
      CREATE TABLE IF NOT EXISTS ipo_gmp (
        id SERIAL PRIMARY KEY,
        ipo_name TEXT NOT NULL,
        gmp_price NUMERIC NOT NULL,
        gmp_pct NUMERIC,
        recorded_at TIMESTAMPTZ DEFAULT NOW()
      )
    `
    const rows = await sql`
      SELECT gmp_price, gmp_pct, recorded_at
      FROM ipo_gmp
      WHERE ipo_name ILIKE ${`%${name}%`}
      ORDER BY recorded_at DESC
      LIMIT 30
    `
    return NextResponse.json({ ok: true, history: rows })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
