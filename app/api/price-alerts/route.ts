// app/api/price-alerts/route.ts
// Price alerts — "alert me when ARVIND hits ₹350"
// Checked daily by GitHub Actions cron

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"
const db = () => neon(process.env.DATABASE_URL!)

async function ensureTable(sql: ReturnType<typeof neon>) {
  await sql`
    CREATE TABLE IF NOT EXISTS price_alerts (
      id          SERIAL PRIMARY KEY,
      symbol      TEXT NOT NULL,
      target_price NUMERIC(12,2) NOT NULL,
      direction   TEXT NOT NULL DEFAULT 'above',  -- 'above' or 'below'
      note        TEXT,
      triggered   BOOLEAN DEFAULT FALSE,
      triggered_at TIMESTAMPTZ,
      created_at  TIMESTAMPTZ DEFAULT NOW()
    )
  `
}

export async function GET() {
  const sql = db()
  await ensureTable(sql)
  const alerts = await sql`
    SELECT * FROM price_alerts ORDER BY triggered ASC, created_at DESC
  `
  return NextResponse.json({ ok: true, alerts })
}

export async function POST(req: NextRequest) {
  const { symbol, target_price, direction = "above", note } = await req.json()
  if (!symbol || !target_price) {
    return NextResponse.json({ ok: false, error: "symbol and target_price required" }, { status: 400 })
  }
  const sql = db()
  await ensureTable(sql)
  const [alert] = await sql`
    INSERT INTO price_alerts (symbol, target_price, direction, note)
    VALUES (${symbol.toUpperCase()}, ${target_price}, ${direction}, ${note ?? null})
    RETURNING *
  `
  return NextResponse.json({ ok: true, alert })
}

export async function DELETE(req: NextRequest) {
  const { id } = await req.json()
  if (!id) return NextResponse.json({ ok: false, error: "id required" }, { status: 400 })
  const sql = db()
  await sql`DELETE FROM price_alerts WHERE id = ${id}`
  return NextResponse.json({ ok: true })
}
