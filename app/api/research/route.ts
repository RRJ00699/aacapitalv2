// app/api/research/route.ts — read-only feed for /dashboard/research (Score v0 evidence page)
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);
export async function GET() {
  const gate = await requireUser();
  if (gate) return gate;
  try {
    const upcoming = await sql`
      SELECT company_name, listing_date, issue_size_cr, issue_price,
             ipo_score, score_band, score_evidence, gap_bucket
      FROM ipo_consolidated WHERE listing_date >= CURRENT_DATE
      ORDER BY listing_date LIMIT 20`;
    const recent = await sql`
      SELECT company_name, listing_date, score_band, gap_bucket, listing_gap_pct, d10_best_pct
      FROM ipo_consolidated
      WHERE listing_date < CURRENT_DATE AND score_band IS NOT NULL
      ORDER BY listing_date DESC LIMIT 15`;
    return NextResponse.json({ upcoming, recent });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}
