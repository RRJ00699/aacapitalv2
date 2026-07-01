import { NextRequest, NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

// Floor/ceiling series for a symbol.
//  • Live-tick path (ipo_level_analysis): rich intraday volume profile, ~live IPOs only.
//  • Fallback (ipo_daily_levels): researched first-5-session floor/ceiling band, covers
//    EVERY listed IPO, updated daily to lock-in. Mapped to the same shape so the panel
//    renders unchanged.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim()
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  try {
    const live = await sql`
      SELECT trade_date, issue_price, listing_open, gap_pct, gap_bucket,
             day_open, day_high, day_low, day_close, session_vwap, close_vs_vwap,
             floor_price, floor_volume, floor_defenses, ceiling_price, ceiling_volume,
             poc_price, obir_open, obir_close, circuit_locked, verdict, risk_note,
             profile_json, tick_count, computed_at
      FROM ipo_level_analysis
      WHERE symbol = ${symbol}
      ORDER BY trade_date ASC
    `.catch(() => [] as any[])

    if ((live as any[]).length) {
      const series = live as any[]
      return NextResponse.json({ symbol, latest: series[series.length - 1], series, count: series.length, source: "live_ticks" })
    }

    // Fallback: researched daily-candle band
    const daily = await sql`
      SELECT d.date AS trade_date, d.t, d.close AS day_close, d.floor AS floor_price,
             d.ceiling AS ceiling_price, d.poc AS poc_price, d.broke_floor, d.broke_ceiling, d.cushion,
             c.gap_bucket, c.gap_pct
      FROM ipo_daily_levels d
      LEFT JOIN ipo_consolidated c ON c.symbol_final = d.symbol
      WHERE d.symbol = ${symbol}
      ORDER BY d.date ASC
    `.catch(() => [] as any[])

    const map = (r: any) => {
      const cush = r.cushion != null ? Number(r.cushion) : null
      const verdict = r.broke_floor ? "FLOOR BROKEN"
        : (cush != null && cush < 0.03) ? "AT FLOOR"
        : r.broke_ceiling ? "ABOVE CEILING" : "FLOOR INTACT"
      return {
        ...r,
        floor_defenses: null, day_open: null, day_high: null, day_low: null,
        session_vwap: null, close_vs_vwap: null, profile_json: null,
        verdict,
        risk_note: cush != null
          ? `Cushion ${(cush * 100).toFixed(1)}% above the first-5-session floor. Daily-candle band (researched, 78% respected) — a risk gauge, not a bounce signal.`
          : null,
      }
    }
    const series = (daily as any[]).map(map)
    const latest = series.length ? series[series.length - 1] : null
    return NextResponse.json({ symbol, latest, series, count: series.length, source: series.length ? "daily_candles" : "none" })
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e), symbol, series: [], latest: null }, { status: 500 })
  }
}
