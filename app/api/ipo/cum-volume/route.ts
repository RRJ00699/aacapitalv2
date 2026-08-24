// app/api/ipo/cum-volume/route.ts
// Serves listing-day traded volume in the 10:29–11:00 IST confirmation window.
// Source after D1 cutover: persisted 5m Kite bars. No Neon tick-feed dependency.

import { NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { d1First } from "@/lib/d1";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbol = (searchParams.get("symbol") || "").toUpperCase().trim();
  const date = searchParams.get("date");
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 });

  if (process.env.UAT_FIXTURE_JSON) {
    return NextResponse.json({ ok: true, symbol, window: "10:29–11:00 IST", cum_volume: null, status: "awaiting", note: "UAT fixture has no live market stream" });
  }

  const dayKey = date ?? new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
  const ckey = `cumvol:v2:${symbol}:${dayKey}`;
  const store = kvStore();
  if (store) {
    try {
      const hit = await store.get(ckey);
      if (hit) return new NextResponse(hit, { headers: { "content-type": "application/json", "x-cache": "HIT" } });
    } catch {}
  }

  try {
    // Stored timestamps are UTC. 10:29–11:00 IST corresponds to 04:59–05:30 UTC.
    // 5m candles give traded volume per bar, so summing the bars in the window is
    // the same quantity the old cumulative-tick subtraction was trying to measure.
    const r = await d1First<{ cum_volume: number | null; bar_count: number }>(
      `SELECT SUM(m.volume_shares) AS cum_volume, COUNT(*) AS bar_count
       FROM market_bars m
       JOIN ipo i ON i.id=m.ipo_id
       WHERE UPPER(i.nse_symbol)=?
         AND m.interval='5m'
         AND substr(m.ts,1,10)=?
         AND substr(m.ts,12,5) >= '04:59'
         AND substr(m.ts,12,5) <= '05:30'`,
      [symbol, dayKey],
    );

    const istNow = new Date(Date.now() + 5.5 * 3600_000);
    const istToday = istNow.toISOString().slice(0, 10);
    const windowClosed = dayKey < istToday ||
      (dayKey === istToday && istNow.getUTCHours() * 60 + istNow.getUTCMinutes() >= 660);
    const bars = Number(r?.bar_count ?? 0);
    const cum = r?.cum_volume == null ? null : Number(r.cum_volume);
    const confirmed = windowClosed && bars > 0 && cum != null;

    const body = JSON.stringify({
      ok: true,
      symbol,
      window: "10:29–11:00 IST",
      cum_volume: confirmed ? cum : null,
      bar_count: bars,
      status: confirmed ? "confirmed" : "awaiting",
      source: "d1_kite_5m",
      ...(confirmed ? {} : { note: bars ? "window still open" : "no 5m bars captured in window yet" }),
    });
    if (store) { try { await store.put(ckey, body, { expirationTtl: confirmed ? 86400 : 60 }); } catch {} }
    return new NextResponse(body, { headers: { "content-type": "application/json", "x-cache": "MISS" } });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : "query failed" }, { status: 500 });
  }
}
