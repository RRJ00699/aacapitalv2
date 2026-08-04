// app/api/ipo/journey/route.ts — HOLD engine. V2: candles from canonical
// `market_candles` (keyed ipo_id, floored at ipo.listing_date), compared against a
// LIVE price (broker quote) so exits fire intraday. Exit math unchanged.
import { NextRequest, NextResponse } from "next/server";
import { readStrict } from "@/lib/kv-cache";
import { computeJourney } from "@/lib/v2/journey";

// IST calendar day — candles change only on EOD sync, so one KV key per day.
function istDate(): string { return new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10); }

export async function GET(req: NextRequest) {
  const sym = req.nextUrl.searchParams.get("sym")?.toUpperCase();
  if (!sym) return NextResponse.json({ ok: false, error: "sym required" }, { status: 400 });
  try {
    // Cache the Neon candle read in KV per sym per IST day (key bumped v1->v2 for the
    // market_candles source). EMPTY results are NOT cached (a listing-day first candle
    // would otherwise be hidden for the TTL). The live price is always fresh.
    const ckey = `journey:candles:v2:${sym}:${istDate()}`;
    const hit = await readStrict(ckey);
    if (!hit) return NextResponse.json({ ok: false, unavailable: true, reason: "historical_snapshot_unavailable", symbol: sym }, { status: 503, headers: { "retry-after": "300", "x-cache": "MISS" } });
    const rows = JSON.parse(hit.payload) as Record<string, unknown>[];
    if (!rows.length) return NextResponse.json(computeJourney(rows, sym));

    // LIVE price from the broker quote (unchanged path).
    let live: { price: number; source: string } | null = null;
    try {
      const q = await fetch(`${req.nextUrl.origin}/api/broker/quote?sym=${sym}&exchange=NSE`, { signal: AbortSignal.timeout(5000) });
      if (q.ok) {
        const j = await q.json();
        const lp = Number(j.last_price ?? j.lastPrice ?? j.ltp);
        if (lp > 0) live = { price: lp, source: j.source || "live" };
      }
    } catch { /* fall back to last close inside computeJourney */ }

    return NextResponse.json(computeJourney(rows, sym, live));
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}
