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
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return null; // authorized -> continue
}
