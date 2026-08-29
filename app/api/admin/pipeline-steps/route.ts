// app/api/admin/pipeline-steps/route.ts — latest run's step board (green/red), D1-backed.
import { NextResponse } from "next/server";
import { requireUser } from "@/lib/api-guard";
import { EXPECTED_LEAN_STEPS } from "@/lib/pipeline-steps";
import { d1All } from "@/lib/d1";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  try {
    const rows = await d1All(
      `WITH latest AS (SELECT MAX(ran_at) AS t FROM pipeline_steps)
       SELECT step, ok, substr(error,1,200) AS error, ran_at
       FROM pipeline_steps, latest
       WHERE ran_at > datetime(latest.t,'-90 minutes')
       ORDER BY ran_at ASC`
    );
    return NextResponse.json({ ok: true, steps: rows, expected: EXPECTED_LEAN_STEPS });
  } catch (e: unknown) {
    return NextResponse.json({ ok: true, steps: [], expected: EXPECTED_LEAN_STEPS,
      warning: e instanceof Error ? e.message : "D1 query failed" });
  }
}
