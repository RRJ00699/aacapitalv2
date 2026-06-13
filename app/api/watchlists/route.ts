import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

export async function GET() {
  try {
    const sql = getDb()
    // Ensure tables exist
    await sql`
      CREATE TABLE IF NOT EXISTS watchlist_stocks (
        id SERIAL PRIMARY KEY,
        symbol TEXT NOT NULL,
        exchange TEXT DEFAULT 'NSE',
        added_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(symbol)
      )
    `
    const stocks = await sql`SELECT * FROM watchlist_stocks ORDER BY added_at DESC`
    return NextResponse.json({ ok: true, stocks })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const { symbol, exchange = "NSE" } = await req.json()
    if (!symbol) return NextResponse.json({ error: "Symbol required" }, { status: 400 })

    const sql = getDb()
    await sql`
      CREATE TABLE IF NOT EXISTS watchlist_stocks (
        id SERIAL PRIMARY KEY,
        symbol TEXT NOT NULL,
        exchange TEXT DEFAULT 'NSE',
        added_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(symbol)
      )
    `
    await sql`
      INSERT INTO watchlist_stocks (symbol, exchange)
      VALUES (${symbol.toUpperCase()}, ${exchange})
      ON CONFLICT (symbol) DO NOTHING
    `
    return NextResponse.json({ ok: true, symbol })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { symbol } = await req.json()
    if (!symbol) return NextResponse.json({ error: "Symbol required" }, { status: 400 })
    const sql = getDb()
    await sql`DELETE FROM watchlist_stocks WHERE symbol = ${symbol.toUpperCase()}`
    return NextResponse.json({ ok: true })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
