// app/api/admin/secrets/route.ts — phone-settable secrets into platform_config.
// Whitelisted keys only. Values never returned (masked). Admin-gated.
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);
const KEYS = ["screener_username", "screener_password", "screener_cookie", "ntfy_topic"];

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const rows = await sql`SELECT key, value FROM platform_config WHERE key = ANY(${KEYS})`;
  const state = Object.fromEntries(KEYS.map(k => {
    const v = rows.find(r => r.key === k)?.value as string | undefined;
    return [k, v ? `set (${String(v).length} chars)` : "not set"];
  }));
  return NextResponse.json({ state });
}

export async function POST(req: NextRequest) {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const { key, value } = await req.json();
  if (!KEYS.includes(key) || typeof value !== "string" || !value.trim())
    return NextResponse.json({ error: "bad key/value" }, { status: 400 });
  await sql`INSERT INTO platform_config (key, value) VALUES (${key}, ${value.trim()})
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`;
  return NextResponse.json({ ok: true });
}
