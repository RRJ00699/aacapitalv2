// app/api/ipo/cum-volume/route.ts
// Serves the 10:29–11:00 IST cumulative-volume confirmation for a listing-day IPO.
// The live-preopen volume tile was "pending" because this endpoint didn't exist.
//
// Source: ipo_tick_feed.day_volume (Kite's running cumulative day volume, captured
// every tick by kite_ticker_ipo.py). Cumulative volume traded in the window =
// day_volume at the last tick ≤ 11:00 minus day_volume at the first tick ≥ 10:29.
// All times IST; tick recorded_at is stored UTC, so we shift by +5:30.
//
// Query: /api/ipo/cum-volume?symbol=LASERPOWER   (optional &date=YYYY-MM-DD)

import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { kvStore } from "@/lib/kv-cache";

export const dynamic = "force-dynamic";
function db() { return neon(process.env.DATABASE_URL!); }

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim();
  const date = searchParams.get("date"); // optional YYYY-MM-DD (IST listing day)
  if (!symbol) {
    return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 });
  }

  // Phase-2 zero-idle: VolumeConfirm polls every 60s per symbol. The window
  // total is FINAL after 11:00 IST — cache confirmed 24h, in-window 60s, so
  // repeat polls (and multiple devices) collapse to at most 1 Neon read/min,
  // and post-window reads never wake Neon again that day.
  const dayKey = date ?? new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
  const ckey = `cumvol:v1:${symbol}:${dayKey}`;
  const store = kvStore();
  if (store) {
    try {
      const hit = await store.get(ckey);
      if (hit) return new NextResponse(hit, { headers: { "content-type": "application/json", "x-cache": "HIT" } });
    } catch { /* miss */ }
  }

  try {
    const sql = db();
    // Window bounds in IST → compare against recorded_at (UTC) shifted +5:30.
    // 10:29 IST = 04:59 UTC · 11:00 IST = 05:30 UTC. We filter on the IST-local
    // clock via (recorded_at AT TIME ZONE 'Asia/Kolkata').
    // Phase-1 bug fix ("in window — accumulating ticks" stuck forever): the old
    // code built an IST-today fallback in a `day` variable but never used it —
    // the filter compared against ${date ?? null}::date, i.e. `= NULL` on every
    // normal UI call (no ?date=), which matches zero rows. COALESCE to IST today.
    const rows = await sql`
      WITH win AS (
        SELECT day_volume, recorded_at,
               (recorded_at AT TIME ZONE 'Asia/Kolkata') AS ist
        FROM ipo_tick_feed
        WHERE UPPER(symbol) = ${symbol}
          AND (recorded_at AT TIME ZONE 'Asia/Kolkata')::date
              = COALESCE(${date ?? null}::date, (now() AT TIME ZONE 'Asia/Kolkata')::date)
      )
      SELECT
        (SELECT day_volume FROM win WHERE ist::time <= '11:00' ORDER BY ist DESC LIMIT 1) AS vol_end,
        (SELECT day_volume FROM win WHERE ist::time >= '10:29' ORDER BY ist ASC  LIMIT 1) AS vol_start,
        (SELECT count(*) FROM win) AS tick_count
    `;

    const r = rows[0] as { vol_end: number | null; vol_start: number | null; tick_count: number };
    if (!r || !r.tick_count) {
      const body = JSON.stringify({
        ok: true, symbol, window: "10:29–11:00 IST",
        cum_volume: null, status: "awaiting", note: "no ticks captured in window yet",
      });
      if (store) { try { await store.put(ckey, body, { expirationTtl: 60 }); } catch { /* best-effort */ } }
      return new NextResponse(body, { headers: { "content-type": "application/json", "x-cache": "MISS" } });
    }

    // Window total needs BOTH bounds. The old fallback returned vol_end alone
    // (i.e. the whole-day cumulative volume) and labeled it "confirmed" — wrong
    // number before 10:29. And "confirmed" additionally requires the 11:00 IST
    // window close (always true for historical ?date= queries).
    const cum = (r.vol_end != null && r.vol_start != null)
      ? Math.max(0, Number(r.vol_end) - Number(r.vol_start))
      : null;
    const istNow = new Date(Date.now() + 5.5 * 3600_000);
    const istToday = istNow.toISOString().slice(0, 10);
    const windowClosed = dayKey < istToday ||
      (dayKey === istToday && istNow.getUTCHours() * 60 + istNow.getUTCMinutes() >= 660); // 11:00 IST
    const confirmed = cum != null && windowClosed;

    const body = JSON.stringify({
      ok: true, symbol, window: "10:29–11:00 IST",
      cum_volume: confirmed ? cum : null,
      vol_start: r.vol_start, vol_end: r.vol_end,
      tick_count: r.tick_count,
      status: confirmed ? "confirmed" : "awaiting",
      ...(confirmed ? {} : { note: "in window — accumulating ticks" }),
    });
    // confirmed totals are final for the day — 24h; in-window partials — 60s
    if (store) { try { await store.put(ckey, body, { expirationTtl: confirmed ? 86400 : 60 }); } catch { /* best-effort */ } }
    return new NextResponse(body, { headers: { "content-type": "application/json", "x-cache": "MISS" } });
  } catch (e: unknown) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "query failed" },
      { status: 500 });
  }
}
