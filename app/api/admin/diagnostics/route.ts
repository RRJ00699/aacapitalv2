// app/api/admin/diagnostics/route.ts — whitelisted, read-only D1 diagnostics.
import { NextResponse } from "next/server";
import { requireUser } from "@/lib/api-guard";
import { runDiagnostic } from "@/lib/v2/diagnostics";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const gate = await requireUser(); if (gate) return gate;
  const check = new URL(req.url).searchParams.get("check") ?? "";
  try {
    const rows = await runDiagnostic(check);
    if (rows === null) return NextResponse.json({ ok: false, error: "unknown check" }, { status: 400 });
    return NextResponse.json({ ok: true, check, rows,
      ranAt: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST" });
  } catch (e: unknown) {
    return NextResponse.json({ ok: true, check,
      rows: [{ note: e instanceof Error ? e.message.slice(0, 180) : "query failed" }] });
  }
}
