import { NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

export async function GET() {
  try {
    const sql = getDb()
    const rows = await sql`
      SELECT user_id, created_at, expires_at
      FROM kite_session
      WHERE expires_at > NOW()
      ORDER BY created_at DESC LIMIT 1
    `
    if (!rows.length) {
      return NextResponse.json({
        connected: false,
        loginUrl: "/api/auth/zerodha",
        message: "Zerodha not connected. Click to login.",
      })
    }
    return NextResponse.json({
      connected: true,
      userId: rows[0].user_id,
      expiresAt: rows[0].expires_at,
      loginUrl: "/api/auth/zerodha",
    })
  } catch (err: any) {
    return NextResponse.json({ connected: false, message: err.message })
  }
}
