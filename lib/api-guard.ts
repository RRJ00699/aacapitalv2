// lib/api-guard.ts — call at the top of every data route handler so the API
// can't be scraped directly (proxy.ts only protects pages).
//   import { requireUser } from "@/lib/api-guard";
//   export async function GET() {
//     const gate = await requireUser(); if (gate) return gate;   // 401 if not logged in
//     ... return your data ...
//   }
import { NextResponse } from "next/server";
import { auth } from "@/auth";

export async function requireUser() {
  // UAT fixture mode (feat/ux-premium): when the server is fixture-served
  // (UAT_FIXTURE_JSON set — never in production; it also replaces the DB),
  // the auth gate opens so browser journeys can run without a login flow.
  // A guard test pins that this bypass is impossible without fixture mode.
  if (process.env.UAT_FIXTURE_JSON) return null;
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return null; // authorized -> continue
}
