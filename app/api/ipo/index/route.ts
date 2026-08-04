import { NextResponse } from "next/server";
import { readStrict, readVersionedSnapshot } from "@/lib/kv-cache";

export const runtime = "edge";
export const SNAPSHOT_KEY = "ipo:index:v3";

export async function GET() {
  const hit = await readVersionedSnapshot(SNAPSHOT_KEY) ?? await readStrict("ipo:index:v2");
  if (!hit) return NextResponse.json({ rows: [], unavailable: true, reason: "snapshot_unavailable" }, { status: 503, headers: { "retry-after": "300", "x-cache": "MISS" } });
  return new NextResponse(hit.payload, { headers: { "content-type": "application/json", "x-cache": hit.source === "primary" ? "HIT" : "STALE" } });
}
