import { NextResponse } from "next/server";
import { requireUser } from "@/lib/api-guard";
import { readStrict, readVersionedSnapshot } from "@/lib/kv-cache";

export const dynamic = "force-dynamic";
export const SNAPSHOT_KEY = "ipo-command:v6";

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const hit = await readVersionedSnapshot(SNAPSHOT_KEY) ?? await readStrict("ipo-command:v5");
  if (!hit) return NextResponse.json({ ok: false, unavailable: true, reason: "snapshot_unavailable" }, { status: 503, headers: { "retry-after": "300", "x-cache": "MISS" } });
  return new NextResponse(hit.payload, { headers: { "content-type": "application/json", "x-cache": hit.source === "primary" ? "HIT" : "STALE" } });
}
