import { NextResponse } from "next/server";
import { readStrict } from "@/lib/kv-cache";

export const dynamic = "force-dynamic";
export async function GET(req: Request) {
  const params = new URL(req.url).searchParams;
  const symbol = (params.get("symbol") || "").toUpperCase().trim();
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 });
  const day = params.get("date") ?? new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
  const hit = await readStrict(`cumvol:v1:${symbol}:${day}`);
  if (!hit) return NextResponse.json({ ok: false, unavailable: true, reason: "volume_snapshot_unavailable", symbol, window: "10:29–11:00 IST" }, { status: 503, headers: { "retry-after": "60", "x-cache": "MISS" } });
  return new NextResponse(hit.payload, { headers: { "content-type": "application/json", "x-cache": hit.source === "primary" ? "HIT" : "STALE" } });
}
