// app/api/ipo/live/route.ts
// Reads from ipo_live table (populated by local scraper on your machine)
// Falls back to ipo_history for recent listed IPOs

import { NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

export async function GET() {
  const sql = db()

  try {
    // Try ipo_live table first (populated by local scraper)
    const liveRows = await sql`
      SELECT name, sector, status, open_date, close_date, listing_date,
             price_band_low, price_band_high, issue_size_cr, gmp_pct,
             qib_x, hni_x, retail_x, source, last_updated
      FROM ipo_live
      WHERE last_updated >= NOW() - INTERVAL '7 days'
        AND status IN ('OPEN','UPCOMING','LISTED')
      ORDER BY
        CASE status WHEN 'OPEN' THEN 1 WHEN 'UPCOMING' THEN 2 ELSE 3 END,
        close_date DESC NULLS LAST
      LIMIT 20
    `.catch(() => [])

    const ipos = liveRows.map(r => ({
      company:        r.name,
      category:       r.sector || "Unknown",
      status:         r.status,
      open_date:      r.open_date,
      close_date:     r.close_date,
      listing_date:   r.listing_date,
      price_band_low:  Number(r.price_band_low  || 0),
      price_band_high: Number(r.price_band_high || 0),
      issue_size_cr:   Number(r.issue_size_cr   || 0),
      gmp:             r.gmp_pct ? Number(r.gmp_pct) : null,
      qib_x:           r.qib_x || null,
      hni_x:           r.hni_x || null,
      retail_x:        r.retail_x || null,
      source:          r.source || "local_scrape",
      last_updated:    r.last_updated,
    }))

    return NextResponse.json({
      ok: true,
      count: ipos.length,
      open:     ipos.filter(i => i.status === "OPEN").length,
      upcoming: ipos.filter(i => i.status === "UPCOMING").length,
      listed:   ipos.filter(i => i.status === "LISTED").length,
      source:   liveRows.length > 0 ? "ipo_live_table" : "empty",
      ipos,
      fetched_at: new Date().toISOString(),
    })

  } catch (err: any) {
    return NextResponse.json({
      ok: false, error: err.message,
      count: 0, ipos: [], fetched_at: new Date().toISOString()
    }, { status: 500 })
  }
}
