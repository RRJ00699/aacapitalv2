// app/api/admin/pipeline-steps/route.ts — latest run's step board (green/red).
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = neon(process.env.DATABASE_URL!);
    const rows = await sql`
      WITH latest AS (SELECT MAX(ran_at) AS t FROM pipeline_steps)
      SELECT step, ok, LEFT(error, 200) AS error, ran_at
      FROM pipeline_steps, latest
      WHERE ran_at > latest.t - interval '90 minutes'
      ORDER BY ran_at ASC`;
    return NextResponse.json({ ok: true, steps: rows });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "";
    if (msg.includes("does not exist")) return NextResponse.json({ ok: true, steps: [] });
    return NextResponse.json({ ok: false, steps: [], error: msg }, { status: 500 });
  }
}
