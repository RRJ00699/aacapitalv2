// app/api/admin/job-flag/route.ts — the Neon-free job flag.
// VM's job_runner polls THIS (KV, zero DB) every minute; Neon is only touched
// when a job actually exists. Auth: X-AAC-Key must equal ADMIN_JOB_KEY.
import { NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";
export const dynamic = "force-dynamic";

const KEYNAME = "admin:jobs-pending";

function authed(req: Request) {
  const want = process.env.ADMIN_JOB_KEY;
  return Boolean(want) && req.headers.get("x-aac-key") === want;
}
function kv() {
  const { env } = getCloudflareContext();
  return (env as Record<string, { get(k: string): Promise<string | null>; delete(k: string): Promise<void> }>).JOB_FLAG;
}

export async function GET(req: Request) {
  if (!authed(req)) return NextResponse.json({ ok: false }, { status: 401 });
  try {
    const v = await kv().get(KEYNAME);
    return NextResponse.json({ ok: true, pending: v != null });
  } catch {
    // KV unavailable -> tell the runner to fall back to its DB poll
    return NextResponse.json({ ok: false, pending: true });
  }
}

export async function DELETE(req: Request) {
  if (!authed(req)) return NextResponse.json({ ok: false }, { status: 401 });
  try { await kv().delete(KEYNAME); } catch { /* TTL self-heals */ }
  return NextResponse.json({ ok: true });
}
