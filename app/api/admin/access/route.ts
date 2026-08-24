// app/api/admin/access/route.ts — pending access requests + approve/deny in D1.
import { NextRequest, NextResponse } from "next/server";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
import { d1All, d1Run } from "@/lib/d1";
export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
    const requests = await d1All("SELECT email,name,status,requested_at,note FROM access_requests ORDER BY requested_at DESC LIMIT 50");
    const allowed = await d1All("SELECT email,added_by,added_at FROM allowed_users ORDER BY added_at DESC LIMIT 100");
    return NextResponse.json({ requests, allowed });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}

export async function POST(req: NextRequest) {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
    const { email, action } = await req.json();
    const e = String(email || "").toLowerCase().trim();
    if (!e || !["approve", "deny", "revoke"].includes(action))
      return NextResponse.json({ error: "bad request" }, { status: 400 });
    if (action === "approve") {
      await d1Run(
        "INSERT INTO allowed_users(email,added_by,added_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(email) DO NOTHING",
        [e, admin],
      );
      await d1Run("UPDATE access_requests SET status='approved',decided_at=CURRENT_TIMESTAMP,decided_by=? WHERE email=?", [admin, e]);
    } else if (action === "deny") {
      await d1Run("UPDATE access_requests SET status='denied',decided_at=CURRENT_TIMESTAMP,decided_by=? WHERE email=?", [admin, e]);
    } else {
      await d1Run("DELETE FROM allowed_users WHERE email=?", [e]);
      await d1Run("UPDATE access_requests SET status='revoked',decided_at=CURRENT_TIMESTAMP,decided_by=? WHERE email=?", [admin, e]);
    }
    return NextResponse.json({ ok: true });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}
