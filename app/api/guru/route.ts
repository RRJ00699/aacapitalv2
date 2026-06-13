// app/api/guru/route.ts
// Saves guru screener results to Neon for persistence across sessions.
// Self-healing: creates table on first call.

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() {
  return neon(process.env.DATABASE_URL!)
}

async function ensureTable() {
  const sql = db()
  await sql`
    CREATE TABLE IF NOT EXISTS guru_scan_results (
      id         SERIAL      PRIMARY KEY,
      guru_key   TEXT        NOT NULL,
      results    JSONB       NOT NULL,
      stock_count INTEGER    NOT NULL DEFAULT 0,
      scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `
  // Keep only last 7 scans per guru to stay lean
  await sql`
    DELETE FROM guru_scan_results
    WHERE id NOT IN (
      SELECT id FROM guru_scan_results
      ORDER BY scanned_at DESC
      LIMIT 50
    )
  `
}

// GET: returns latest scan result for each guru key
export async function GET() {
  try {
    await ensureTable()
    const sql = db()
    const rows = await sql`
      SELECT DISTINCT ON (guru_key)
        guru_key, results, stock_count, scanned_at
      FROM guru_scan_results
      ORDER BY guru_key, scanned_at DESC
    `
    const byGuru: Record<string, any> = {}
    for (const row of rows) {
      byGuru[row.guru_key] = {
        results:    row.results,
        stockCount: row.stock_count,
        scannedAt:  row.scanned_at,
      }
    }
    return NextResponse.json({ ok: true, scans: byGuru })
  } catch (err: any) {
    console.error("Guru GET error:", err)
    return NextResponse.json({ error: "Failed to load guru scans" }, { status: 500 })
  }
}

// POST: saves a new scan result
export async function POST(req: Request) {
  try {
    await ensureTable()
    const { guruKey, results } = await req.json()
    if (!guruKey || !Array.isArray(results)) {
      return NextResponse.json({ error: "guruKey and results[] required" }, { status: 400 })
    }
    const sql = db()
    await sql`
      INSERT INTO guru_scan_results (guru_key, results, stock_count)
      VALUES (${guruKey}, ${JSON.stringify(results)}::jsonb, ${results.length})
    `
    return NextResponse.json({ ok: true, saved: results.length })
  } catch (err: any) {
    console.error("Guru POST error:", err)
    return NextResponse.json({ error: "Failed to save scan" }, { status: 500 })
  }
}
