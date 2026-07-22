// app/api/ipo/index/route.ts — the FULL-UNIVERSE identity index (D5,
// 2026-07-25): every IPO ever, for the Details/Review search. Identity only;
// the command payload serves data for windowed IPOs, ipo_gold for the rest
// (next slice). Cached 6h; pipeline-refreshed data changes 2x/day anyway.
import { NextResponse } from "next/server";
import { fixtureAwareNeon } from "@/lib/db";
import { cached } from "@/lib/kv-cache";

export const runtime = "edge";

export async function GET() {
  try {
    const body = await cached("ipo:index:v1", async () => {
      const sql = fixtureAwareNeon();
      const rows = await sql`
        SELECT c.company_name,
               COALESCE(NULLIF(btrim(c.symbol_final), ''), NULLIF(btrim(c.nse_symbol), ''), btrim(c.symbol)) AS sym,
               c.listing_date
        FROM ipo_consolidated c
        WHERE c.company_name IS NOT NULL
        ORDER BY c.listing_date DESC NULLS LAST`;
      return JSON.stringify({ rows, generated_at: new Date().toISOString() });
    }, 21600);
    return new NextResponse(body, { headers: { "content-type": "application/json" } });
  } catch (e) {
    return NextResponse.json({ rows: [], degraded: String(e).slice(0, 200) }, { status: 200 });
  }
}
