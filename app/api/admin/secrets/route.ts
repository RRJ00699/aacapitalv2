// app/api/admin/secrets/route.ts — phone-settable secrets into platform_config.
// Whitelisted keys only. Values never returned (masked). Admin-gated.
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);
const KEYS = ["screener_username", "screener_password", "screener_cookie", "ntfy_topic", "ipomatrix_cookie",
  "zerodha_totp_secret", "kite_api_key", "kite_api_secret", "kite_user_id", "kite_password"];

// Decode a JWT's exp claim (IPOMatrix cookie is/contains a JWT) — display only.
function jwtExpiry(v: string): string | null {
  try {
    const m = v.match(/eyJ[\w-]+\.([\w-]+)\./);
    if (!m) return null;
    const payload = JSON.parse(Buffer.from(m[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString());
    if (!payload.exp) return null;
    const d = new Date(payload.exp * 1000);
    const days = Math.floor((d.getTime() - Date.now()) / 86400000);
    return `expires ${d.toISOString().slice(0, 10)} (${days}d)${days <= 5 ? " ⚠️ RENEW SOON" : ""}`;
  } catch { return null; }
}

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const rows = await sql`SELECT key, value, updated_at FROM platform_config WHERE key = ANY(${KEYS})`;
  const state = Object.fromEntries(KEYS.map(k => {
    const r = rows.find(r => r.key === k);
    const v = r?.value as string | undefined;
    if (!v) return [k, "not set"];
    const upd = r?.updated_at ? ` · updated ${String(r.updated_at).slice(0, 10)}` : "";
    const exp = k === "ipomatrix_cookie" ? jwtExpiry(v) : null;
    return [k, `set (${String(v).length} chars)${upd}${exp ? ` · ${exp}` : ""}`];
  }));
  // Kite worker-store health (the June-13-stale-token class, surfaced)
  let kite = "no session row";
  try {
    const ks = await sql`SELECT expires_at FROM kite_session ORDER BY created_at DESC LIMIT 1`;
    if (ks[0]?.expires_at) {
      const live = new Date(ks[0].expires_at as string).getTime() > Date.now();
      kite = `${live ? "LIVE" : "EXPIRED"} · until ${String(ks[0].expires_at).slice(0, 16)}`;
    }
  } catch { /* table absent = leave default */ }
  return NextResponse.json({ state, kite });
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
