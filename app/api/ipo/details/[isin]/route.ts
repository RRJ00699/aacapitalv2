import { NextRequest, NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot } from "@/lib/versioned-snapshot";

export const dynamic = "force-dynamic";
const ISIN = /^[A-Z0-9]{12}$/;

/** KV-only consumer: deliberately no database, SQL-client, or domain-builder import. */
export async function GET(_req: NextRequest, context: { params: Promise<{ isin: string }> }) {
  const isin = String((await context.params).isin ?? "").toUpperCase();
  if (!ISIN.test(isin)) return NextResponse.json({ state: "invalid", error: "ISIN must contain exactly 12 letters or digits" }, { status: 400 });
  const store = kvStore();
  if (!store) return NextResponse.json({ state: "kv_unavailable", error: "Details snapshot store is unavailable" }, { status: 503 });
  const hit = await readVersionedSnapshot(store, `ipo-details:isin:${isin}:v1`);
  if (!hit) return NextResponse.json({ state: "not_found", isin, error: "Details snapshot not found or both active and previous snapshots are malformed" }, { status: 404, headers: { "x-cache": "MISS" } });
  return new Response(hit.payload, { status: 200, headers: { "content-type": "application/json", "x-cache": "HIT", "x-snapshot-version": hit.version, ...(hit.source === "previous" ? { "x-snapshot-rollback": "previous" } : {}) } });
}
