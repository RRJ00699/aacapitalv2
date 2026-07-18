// app/api/admin/kv-put/route.ts — the VM ticker writes live snapshots here
// (KV, zero Neon) during listing mornings. Auth: X-AAC-Key == ADMIN_JOB_KEY.
import { NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";
export const dynamic = "force-dynamic";

function authed(req: Request): boolean {
  const want = process.env.ADMIN_JOB_KEY;
  return Boolean(want) && req.headers.get("x-aac-key") === want;
}

function kv() {
  const { env } = getCloudflareContext();
  return (env as Record<string, { put(k: string, v: string, o?: { expirationTtl?: number }): Promise<void> } | undefined>).CACHE ?? null;
}

export async function GET(req: Request) {
  // Write-only endpoint, but the auth invariant applies to every method:
  // unauthenticated -> 401 (never leak that the route exists / do any work).
  if (!authed(req)) return NextResponse.json({ ok: false }, { status: 401 });
  return NextResponse.json({ ok: false, reason: "use POST" }, { status: 405 });
}

export async function POST(req: Request) {
  if (!authed(req)) return NextResponse.json({ ok: false }, { status: 401 });
  const store = kv();
  if (!store) return NextResponse.json({ ok: false, reason: "no CACHE binding" }, { status: 503 });
  try {
    const { key, payload, ttl } = await req.json();
    if (!key || typeof payload !== "string")
      return NextResponse.json({ ok: false, reason: "key+payload required" }, { status: 400 });
    await store.put(String(key), payload, { expirationTtl: ttl || 300 }); // live data: 5-min TTL self-heals
    return NextResponse.json({ ok: true, key });
  } catch (e) {
    return NextResponse.json({ ok: false, reason: String(e).slice(0, 120) }, { status: 500 });
  }
}
