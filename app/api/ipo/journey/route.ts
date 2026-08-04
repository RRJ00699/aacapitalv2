import { NextRequest, NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot } from "@/lib/versioned-snapshot";
import { computeJourney } from "@/lib/v2/journey";

export async function GET(req: NextRequest) {
  const sym = req.nextUrl.searchParams.get("sym")?.toUpperCase();
  if (!sym) return NextResponse.json({ ok: false, error: "sym required" }, { status: 400 });
  const store = kvStore();
  const hit = store ? await readVersionedSnapshot(store, "journey:candles:v2") : null;
  if (!hit) return NextResponse.json(computeJourney([], sym), { headers: { "x-cache": "MISS" } });
  const bundle = JSON.parse(hit.payload) as { rows?: Record<string, Record<string, unknown>[]> };
  const rows = bundle.rows?.[sym] ?? [];
  let live: { price: number; source: string } | null = null;
  try {
    const q = await fetch(`${req.nextUrl.origin}/api/broker/quote?sym=${encodeURIComponent(sym)}&exchange=NSE`, { signal: AbortSignal.timeout(5000) });
    if (q.ok) { const j = await q.json(); const price = Number(j.last_price ?? j.lastPrice ?? j.ltp); if (price > 0) live = { price, source: j.source || "live" }; }
  } catch { /* the unchanged close fallback is inside computeJourney */ }
  return NextResponse.json(computeJourney(rows, sym, live), { headers: { "x-cache": "HIT", "x-snapshot-version": hit.version, ...(hit.source === "previous" ? { "x-snapshot-rollback": "previous" } : {}) } });
}
