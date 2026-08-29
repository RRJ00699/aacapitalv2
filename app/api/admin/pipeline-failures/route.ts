// app/api/admin/pipeline-failures/route.ts — recent cron step failures, D1-backed.
import { NextResponse } from "next/server";
import { requireUser } from "@/lib/api-guard";
import { d1All } from "@/lib/d1";
export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  try {
    const rows = await d1All(
      `SELECT step, script, stderr_tail, failed_at
       FROM pipeline_failures
       WHERE failed_at > datetime('now','-7 days')
       ORDER BY failed_at DESC LIMIT 30`
    );
    return NextResponse.json({ ok: true, failures: rows });
  } catch (e: unknown) {
    return NextResponse.json({ ok: true, failures: [], warning: e instanceof Error ? e.message : "D1 query failed" });
  }
}
