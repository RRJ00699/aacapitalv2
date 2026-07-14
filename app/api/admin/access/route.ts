// app/api/admin/access/route.ts — pending access requests + approve/deny
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

async function ensure() {
  await sql`CREATE TABLE IF NOT EXISTS allowed_users (
    email TEXT PRIMARY KEY, added_by TEXT, added_at TIMESTAMPTZ DEFAULT now())`;
  await sql`CREATE TABLE IF NOT EXISTS access_requests (
    email TEXT PRIMARY KEY, name TEXT, status TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMPTZ DEFAULT now(), decided_at TIMESTAMPTZ, decided_by TEXT)`;
}

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
    await ensure();
    await sql`ALTER TABLE access_requests ADD COLUMN IF NOT EXISTS note TEXT`;
    const requests = await sql`SELECT email, name, status, requested_at, note
      FROM access_requests ORDER BY requested_at DESC LIMIT 50`;
    const allowed = await sql`SELECT email, added_by, added_at
      FROM allowed_users ORDER BY added_at DESC LIMIT 100`;
    return NextResponse.json({ requests, allowed });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}

export async function POST(req: NextRequest) {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
    await ensure();
    const { email, action } = await req.json();
    const e = String(email || "").toLowerCase().trim();
    if (!e || !["approve", "deny", "revoke"].includes(action))
      return NextResponse.json({ error: "bad request" }, { status: 400 });
    if (action === "approve") {
      await sql`INSERT INTO allowed_users (email, added_by) VALUES (${e}, ${admin})
                ON CONFLICT (email) DO NOTHING`;
      await sql`UPDATE access_requests SET status='approved', decided_at=now(),
                decided_by=${admin} WHERE email=${e}`;
    } else if (action === "deny") {
      await sql`UPDATE access_requests SET status='denied', decided_at=now(),
                decided_by=${admin} WHERE email=${e}`;
    } else {
      await sql`DELETE FROM allowed_users WHERE email=${e}`;
      await sql`UPDATE access_requests SET status='revoked', decided_at=now(),
                decided_by=${admin} WHERE email=${e}`;
    }
    return NextResponse.json({ ok: true });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}
