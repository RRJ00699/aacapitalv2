// app/api/pipeline/status/route.ts
// Returns current DB stats for the pipeline control panel

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

export async function GET() {
  try {
    const sql = neon(process.env.DATABASE_URL!)

    const [candles, signals, commentary, latestSignal] = await Promise.all([
      sql`SELECT COUNT(*) FROM price_candles`.catch(() => [{ count: 0 }]),
      sql`SELECT COUNT(DISTINCT symbol) FROM technical_signals`.catch(() => [{ count: 0 }]),
      sql`SELECT COUNT(*) FROM management_commentary`.catch(() => [{ count: 0 }]),
      sql`SELECT MAX(signal_date) as latest, MAX(updated_at) as updated FROM technical_signals`.catch(() => [{}]),
    ])

    return NextResponse.json({
      ok:         true,
      candles:    Number((candles[0] as any).count),
      signals:    Number((signals[0] as any).count),
      commentary: Number((commentary[0] as any).count),
      latest_signal_date: (latestSignal[0] as any)?.latest ?? null,
      last_updated:       (latestSignal[0] as any)?.updated ?? null,
    })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
