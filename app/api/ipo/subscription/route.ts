import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function getSQL() { return neon(process.env.DATABASE_URL!) }

// Ensure table exists on first call
async function ensureTable() {
  await getSQL()`
    CREATE TABLE IF NOT EXISTS subscription_history (
      id          SERIAL PRIMARY KEY,
      ipo_name    TEXT NOT NULL,
      day         INTEGER NOT NULL CHECK (day IN (1, 2, 3)),
      qib_x       NUMERIC,
      nii_x       NUMERIC,
      retail_x    NUMERIC,
      total_x     NUMERIC,
      notes       TEXT,
      recorded_at TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE(ipo_name, day)
    )
  `
}

// GET /api/ipo/subscription?name=CMR+Green+Technologies
export async function GET(req: NextRequest) {
  try {
    const name = req.nextUrl.searchParams.get("name")
    if (!name) return NextResponse.json({ error: "Missing name" }, { status: 400 })

    await ensureTable()

    const rows = await getSQL()`
      SELECT day, qib_x, nii_x, retail_x, total_x, notes, recorded_at
      FROM subscription_history
      WHERE ipo_name = ${name}
      ORDER BY day ASC
    `
    return NextResponse.json({ ok: true, days: rows })
  } catch (err: any) {
    console.error("subscription GET error:", err)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

// POST /api/ipo/subscription
// Body: { name, day, qib_x, nii_x, retail_x, notes }
export async function POST(req: NextRequest) {
  try {
    const { name, day, qib_x, nii_x, retail_x, notes } = await req.json()

    if (!name || !day) {
      return NextResponse.json({ error: "Missing name or day" }, { status: 400 })
    }
    if (![1, 2, 3].includes(day)) {
      return NextResponse.json({ error: "Day must be 1, 2 or 3" }, { status: 400 })
    }

    await ensureTable()

    const total = qib_x && nii_x && retail_x
      ? +((qib_x * 0.5 + nii_x * 0.15 + retail_x * 0.35)).toFixed(2)
      : null

    await getSQL()`
      INSERT INTO subscription_history (ipo_name, day, qib_x, nii_x, retail_x, total_x, notes)
      VALUES (${name}, ${day}, ${qib_x ?? null}, ${nii_x ?? null}, ${retail_x ?? null}, ${total}, ${notes ?? null})
      ON CONFLICT (ipo_name, day)
      DO UPDATE SET
        qib_x      = EXCLUDED.qib_x,
        nii_x      = EXCLUDED.nii_x,
        retail_x   = EXCLUDED.retail_x,
        total_x    = EXCLUDED.total_x,
        notes      = EXCLUDED.notes,
        recorded_at = NOW()
    `

    // Fetch all days back to return complete state
    const rows = await getSQL()`
      SELECT day, qib_x, nii_x, retail_x, total_x, notes, recorded_at
      FROM subscription_history
      WHERE ipo_name = ${name}
      ORDER BY day ASC
    `
    return NextResponse.json({ ok: true, days: rows })
  } catch (err: any) {
    console.error("subscription POST error:", err)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
