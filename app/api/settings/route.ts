// app/api/settings/route.ts
// Stores user preferences in Neon as key-value pairs.
// The table is provisioned by explicit migration tooling.

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() {
  return neon(process.env.DATABASE_URL!)
}

export async function GET() {
  try {
    const sql  = db()
    const rows = await sql`SELECT key, value FROM user_settings`
    const settings: Record<string, any> = {}
    for (const row of rows) {
      settings[row.key] = row.value
    }
    return NextResponse.json({ ok: true, settings })
  } catch (err: any) {
    console.error("Settings GET error:", err)
    return NextResponse.json({ error: "Failed to load settings" }, { status: 500 })
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const sql  = db()
    for (const [key, value] of Object.entries(body)) {
      await sql`
        INSERT INTO user_settings (key, value, updated_at)
        VALUES (${key}, ${JSON.stringify(value)}::jsonb, NOW())
        ON CONFLICT (key) DO UPDATE
          SET value      = EXCLUDED.value,
              updated_at = NOW()
      `
    }
    return NextResponse.json({ ok: true })
  } catch (err: any) {
    console.error("Settings POST error:", err)
    return NextResponse.json({ error: "Failed to save settings" }, { status: 500 })
  }
}
