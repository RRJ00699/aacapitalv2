// app/api/ipo/[id]/details/route.ts — Complete Details feed.
//
// KV-ONLY by design. It serves the payload warm_kv builds (ipo:<id>:details), reading the
// live key then the 7-day :stale twin. Per the HARD CONSTRAINT it NEVER queries Neon: a
// total miss returns an honest "not yet warmed" state so a brand-new IPO (before its first
// warm cycle) does not wake the database on user traffic. If the screen needs a field KV
// doesn't hold, add it to pipeline/warm_kv.py — never a DB read here.
import { NextRequest, NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ipoId = Number(id);
  if (!Number.isInteger(ipoId) || ipoId <= 0) {
    return NextResponse.json({ ok: false, error: "invalid id" }, { status: 400 });
  }

  const key = `ipo:${ipoId}:details`;
  const store = kvStore();
  if (store) {
    try {
      const hit = await store.get(key);
      if (hit) {
        return new NextResponse(hit, {
          headers: { "content-type": "application/json", "x-cache": "HIT" },
        });
      }
      const stale = await store.get(`${key}:stale`);
      if (stale) {
        // primary expired but the twin survives — serve it, Neon stays asleep
        return new NextResponse(stale, {
          headers: { "content-type": "application/json", "x-cache": "STALE",
                     "x-warning": "served from the 7-day stale twin" },
        });
      }
    } catch { /* fall through to the degraded state; never touch Neon */ }
  }

  // Total miss = not yet warmed (new IPO before its first cycle, or no KV binding locally).
  // Honest degraded state, 200 so the screen can render "details are being prepared".
  return NextResponse.json(
    { id: ipoId, available: false,
      reason: `IPO ${ipoId} is not yet in the cache — the pipeline warms every in-scope IPO twice daily; this resolves on the next run` },
    { status: 200, headers: { "x-cache": "MISS" } },
  );
}
