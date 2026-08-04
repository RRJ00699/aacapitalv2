import { NextResponse } from "next/server";
import { readStrict } from "@/lib/kv-cache";

export const dynamic = "force-dynamic";
export async function GET() {
  const hit = await readStrict("ipo-live-preopen:v2");
  if (!hit) return NextResponse.json({ ok: false, rows: [], unavailable: true, reason: "live_snapshot_unavailable" }, { status: 503, headers: { "retry-after": "30", "x-cache": "MISS" } });
  return new NextResponse(hit.payload, { headers: { "content-type": "application/json", "x-cache": hit.source === "primary" ? "HIT" : "STALE" } });
}
