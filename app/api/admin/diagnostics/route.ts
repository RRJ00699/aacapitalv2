// app/api/admin/diagnostics/route.ts — phone-first, WHITELISTED, READ-ONLY
// diagnostics (Settings panel). V2: checks read canonical tables; `sbi_notes` was
// removed with the SBI parser. No user SQL ever reaches this route.
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";
import { runDiagnostic } from "@/lib/v2/diagnostics";
import type { SqlClient } from "@/lib/v2/sql";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const gate = await requireUser(); if (gate) return gate;   // ledger #15: queries kite_session
  const check = new URL(req.url).searchParams.get("check") ?? "";
  const sql = neon(process.env.DATABASE_URL!) as unknown as SqlClient;
  try {
    const rows = await runDiagnostic(sql, check);
    if (rows === null) return NextResponse.json({ ok: false, error: "unknown check" }, { status: 400 });
    return NextResponse.json({ ok: true, check, rows,
      ranAt: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST" });
  } catch (e: unknown) {
    // a missing table/column reports itself as a note instead of failing the panel
    return NextResponse.json({ ok: true, check,
      rows: [{ note: e instanceof Error ? e.message.slice(0, 180) : "query failed" }] });
  }
}
