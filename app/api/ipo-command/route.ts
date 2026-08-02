// app/api/ipo-command/route.ts — single feed for /dashboard/ipo2. V2 NARROW CUT:
// cards + brlm + derived floor/ceiling from canonical tables; live-ticks, intraday
// levels, news, SBI and GMP are dropped (no maintained V2 source). Read-only.
//
// KV: new key `ipo-command:v5` (payload differs from warm_kv's `ipo:list:v2`, so it
// gets its own key). cachedWithStale + build-on-miss; warm_kv.py will write this key
// in a follow-up so the two repos stay decoupled.
import { NextResponse } from "next/server";
import { fixtureAwareNeon } from "@/lib/db";
import { requireUser } from "@/lib/api-guard";
import { cachedWithStale, kvPutBoth } from "@/lib/kv-cache";
import { buildCommand } from "@/lib/v2/ipo-command";
import type { SqlClient } from "@/lib/v2/sql";

export const dynamic = "force-dynamic";
const CACHE_KEY = "ipo-command:v5";
const CACHE_TTL_S = 43200; // 12h — pipeline warms it 2x/day

export async function GET(req?: Request) {
  // ?warm=1 + machine key: skip the session gate AND the cache read (this call
  // exists to REBUILD the cache), build fresh and write both twins.
  let isWarm = false;
  if (req) {
    try {
      isWarm = new URL(req.url).searchParams.get("warm") === "1"
        && req.headers.get("x-aac-key") === process.env.ADMIN_JOB_KEY;
    } catch { isWarm = false; }
  }
  if (!isWarm) { const gate = await requireUser(); if (gate) return gate; }

  const sql = () => fixtureAwareNeon() as unknown as SqlClient;
  try {
    if (isWarm) {
      const payload = JSON.stringify(await buildCommand(sql()));
      await kvPutBoth(CACHE_KEY, payload, CACHE_TTL_S);
      return new NextResponse(payload, { headers: { "content-type": "application/json", "x-cache": "REBUILD" } });
    }
    const { payload, source } = await cachedWithStale(CACHE_KEY, () => buildCommand(sql()), CACHE_TTL_S);
    const headers: Record<string, string> = {
      "content-type": "application/json",
      "x-cache": source === "kv" ? "HIT" : source === "stale" ? "STALE" : "MISS",
    };
    if (source === "stale") headers["x-warning"] = "primary cache expired; serving stale copy, DB not woken";
    return new NextResponse(payload, { headers });
  } catch (e) {
    // DEGRADED MODE: one error must never blank the page.
    return NextResponse.json({
      cards: [], filtered: [], filtered_count: 0, live: [], levels: [], blocks: [],
      post: [], brlm: [], dl: [], track: [],
      degraded: String(e).slice(0, 300), generated_at: new Date().toISOString(),
    }, { status: 200 });
  }
}
