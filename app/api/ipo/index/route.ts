// app/api/ipo/index/route.ts — full-universe identity index for the ipo2 search.
// V2: reads canonical `ipo` (was V1 `ipo_consolidated`). Cached 6h.
import { NextResponse } from "next/server";
import { fixtureAwareNeon } from "@/lib/db";
import { cached } from "@/lib/kv-cache";
import { buildIpoIndex } from "@/lib/v2/ipo-index";
import type { SqlClient } from "@/lib/v2/sql";

export const runtime = "edge";

export async function GET() {
  try {
    // key bumped v1->v2: payload now sourced from `ipo`, so the old cache is invalidated.
    const body = await cached("ipo:index:v2", () => buildIpoIndex(fixtureAwareNeon() as unknown as SqlClient), 21600);
    return new NextResponse(body, { headers: { "content-type": "application/json" } });
  } catch (e) {
    return NextResponse.json({ rows: [], degraded: String(e).slice(0, 200) }, { status: 200 });
  }
}
