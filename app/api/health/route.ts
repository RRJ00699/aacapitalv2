// app/api/health/route.ts — build stamp + DB-free liveness (Guardrail B + E).
import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({
    ok: true,
    build: process.env.NEXT_PUBLIC_BUILD_ID || "dev",
    build_time: process.env.NEXT_PUBLIC_BUILD_TIME || null,
    now: new Date().toISOString(),
  });
}
