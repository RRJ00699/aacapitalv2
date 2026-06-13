import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

async function ensureTable(sql: any) {
  await sql`
    CREATE TABLE IF NOT EXISTS thesis_notes (
      id SERIAL PRIMARY KEY,
      symbol TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT,
      framework TEXT,
      conviction INTEGER DEFAULT 5,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    )
  `
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const symbol = searchParams.get("symbol")
    const sql = getDb()
    await ensureTable(sql)

    const notes = symbol
      ? await sql`SELECT * FROM thesis_notes WHERE symbol = ${symbol.toUpperCase()} ORDER BY updated_at DESC`
      : await sql`SELECT * FROM thesis_notes ORDER BY updated_at DESC LIMIT 50`

    return NextResponse.json({ ok: true, notes })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const { symbol, title, content, framework, conviction = 5 } = await req.json()
    if (!symbol || !title) return NextResponse.json({ error: "Symbol and title required" }, { status: 400 })

    const sql = getDb()
    await ensureTable(sql)
    const rows = await sql`
      INSERT INTO thesis_notes (symbol, title, content, framework, conviction)
      VALUES (${symbol.toUpperCase()}, ${title}, ${content || ""}, ${framework || ""}, ${conviction})
      RETURNING *
    `
    return NextResponse.json({ ok: true, note: rows[0] })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function PUT(req: NextRequest) {
  try {
    const { id, title, content, framework, conviction } = await req.json()
    if (!id) return NextResponse.json({ error: "ID required" }, { status: 400 })

    const sql = getDb()
    await ensureTable(sql)
    const rows = await sql`
      UPDATE thesis_notes
      SET title = ${title}, content = ${content}, framework = ${framework},
          conviction = ${conviction}, updated_at = NOW()
      WHERE id = ${id}
      RETURNING *
    `
    return NextResponse.json({ ok: true, note: rows[0] })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { id } = await req.json()
    if (!id) return NextResponse.json({ error: "ID required" }, { status: 400 })
    const sql = getDb()
    await sql`DELETE FROM thesis_notes WHERE id = ${id}`
    return NextResponse.json({ ok: true })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
