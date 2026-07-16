// app/api/admin/pipeline-failures/route.ts — recent cron step failures for the
// Settings "Pipeline health" panel (7-day window). Table is created lazily by
// the lean pipeline's failure sink; absent table = zero failures, not an error.
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = neon(process.env.DATABASE_URL!);
    const rows = await sql`
      SELECT step, script, stderr_tail, failed_at
      FROM pipeline_failures
      WHERE failed_at > NOW() - interval '7 days'
      ORDER BY failed_at DESC LIMIT 30`;
    return NextResponse.json({ ok: true, failures: rows });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "";
    if (msg.includes("does not exist")) return NextResponse.json({ ok: true, failures: [] });
    return NextResponse.json({ ok: false, failures: [], error: msg }, { status: 500 });
  }
}
