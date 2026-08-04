import { NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot } from "@/lib/versioned-snapshot";

export const dynamic = "force-dynamic";

/** Cloudflare Worker -> Kite is the smallest Free-plan live architecture:
 * one request per UI poll, a 15-second KV coalescing cache, and no server/Neon. */
export async function GET() {
  const store = kvStore();
  const base = store ? await readVersionedSnapshot(store, "ipo-live-preopen:v2") : null;
  if (!base) return NextResponse.json({ ok: true, window: "listing_date = IST-today", book_live: false, count: 0, listings: [], degraded: "snapshot unavailable" }, { headers: { "x-cache": "MISS" } });
  const payload = JSON.parse(base.payload) as { listings: Array<Record<string, unknown>>; [key: string]: unknown };
  const token = await store?.get("broker:kite:access-token");
  const apiKey = process.env.KITE_API_KEY;
  const liveEnabled = Boolean(token && apiKey);
  const listings = await Promise.all((payload.listings || []).map(async item => {
    const sym = String(item.sym || "").toUpperCase();
    if (!liveEnabled || !sym) return { ...item, book: null, live_price: null };
    const liveKey = `preopen:live:${sym}`;
    try {
      const cached = await store?.get(liveKey);
      if (cached) return { ...item, ...JSON.parse(cached) };
      const instrument = `NSE:${sym}`;
      const response = await fetch(`https://api.kite.trade/quote?i=${encodeURIComponent(instrument)}`, {
        headers: { "X-Kite-Version": "3", "Authorization": `token ${apiKey}:${token}` }, signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error(`Kite ${response.status}`);
      const q = (await response.json())?.data?.[instrument];
      if (!q) return { ...item, book: null, live_price: null };
      const buyQty = Number(q.total_buy_quantity ?? q.buy_quantity ?? 0), sellQty = Number(q.total_sell_quantity ?? q.sell_quantity ?? 0);
      const total = buyQty + sellQty;
      const overlay = { live_price: Number(q.last_price) || null, book: { discoveryPrice: Number(q.ohlc?.open ?? q.last_price) || null,
        buyQty, sellQty,
        leanPct: total ? Math.round(((buyQty - sellQty) / total) * 1000) / 10 : null },
        last_eval_ist: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) };
      await store?.put(liveKey, JSON.stringify(overlay), { expirationTtl: 15 });
      return { ...item, ...overlay };
    } catch { return { ...item, book: null, live_price: null }; }
  }));
  return NextResponse.json({ ...payload, book_live: liveEnabled, count: listings.length, listings, fetchedAt: new Date().toISOString() },
    { headers: { "x-cache": "HIT", "x-snapshot-version": base.version, ...(base.source === "previous" ? { "x-snapshot-rollback": "previous" } : {}) } });
}
