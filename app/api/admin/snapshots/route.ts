import { NextRequest, NextResponse } from "next/server";
import { fixtureAwareNeon } from "@/lib/db";
import { kvStore } from "@/lib/kv-cache";
import { publishVersionedSnapshot } from "@/lib/versioned-snapshot";
import { buildCommand } from "@/lib/v2/ipo-command";
import { buildIpoIndex } from "@/lib/v2/ipo-index";
import { fetchJourneyCandles } from "@/lib/v2/journey";
import { fetchPreopenRows, scoreListing } from "@/lib/v2/live-preopen";
import type { SqlClient } from "@/lib/v2/sql";

export const dynamic = "force-dynamic";
const NAMES = { command: "ipo-command:v6", index: "ipo:index:v3", journey: "journey:candles:v2", live: "ipo-live-preopen:v2" } as const;

export async function POST(req: NextRequest) {
  if (!process.env.SNAPSHOT_PUBLISH_KEY || req.headers.get("x-aac-key") !== process.env.SNAPSHOT_PUBLISH_KEY)
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const store = kvStore();
  if (!store) return NextResponse.json({ error: "CACHE binding unavailable" }, { status: 503 });
  const sql = fixtureAwareNeon() as unknown as SqlClient;
  const index = await buildIpoIndex(sql);
  const symbols = (index.rows as Array<Record<string, unknown>>).map(r => String(r.sym || "").toUpperCase()).filter(Boolean);
  const candlePairs = await Promise.all(symbols.map(async sym => [sym, await fetchJourneyCandles(sql, sym)] as const));
  const preopenRows = await fetchPreopenRows(sql);
  const observations = await sql`
    SELECT DISTINCT ON (o.ipo_id) o.ipo_id, o.ltp, o.buy_qty, o.sell_qty, o.payload, o.observed_at
    FROM listing_observations o
    WHERE o.obs_type = 'preopen'
    ORDER BY o.ipo_id, o.observed_at DESC`;
  const latestObservation = new Map(observations.map(o => [String(o.ipo_id), o]));
  // The Worker must never wake Neon for a live quote.  Token refresh remains a
  // pipeline responsibility; publication copies the short-lived credential into
  // protected KV (it is never included in a route snapshot or response).
  const tokenRows = await sql`SELECT value FROM platform_config WHERE key = 'kite_access_token' LIMIT 1`;
  if (tokenRows[0]?.value) await store.put("broker:kite:access-token", String(tokenRows[0].value), { expirationTtl: 86400 });
  const now = new Date().toISOString();
  const payloads = {
    command: await buildCommand(sql), index,
    journey: { rows: Object.fromEntries(candlePairs), generated_at: now },
    live: { ok: true, window: "listing_date = IST-today", book_live: false, count: preopenRows.length,
      listings: preopenRows.map(row => ({ ...scoreListing(row), latest_observation: latestObservation.get(String(row.ipo_id)) ?? null })), fetchedAt: now },
  };
  const published: Record<string, string> = {};
  for (const key of Object.keys(NAMES) as Array<keyof typeof NAMES>)
    published[NAMES[key]] = await publishVersionedSnapshot(store, NAMES[key], payloads[key]);
  return NextResponse.json({ ok: true, published });
}
