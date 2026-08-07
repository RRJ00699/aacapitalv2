// app/api/admin/access/route.ts — pending access requests + approve/deny
import { NextRequest, NextResponse } from "next/server";
import { neon, type NeonQueryFunction } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";
// lazy neon client — do NOT init at module scope: `next build` (deploy.yml) has no
// DATABASE_URL, and a module-scope neon() throws during page-data collection. Same
// runtime behavior; resolves on first query. (see lib/db.ts for the shared helper)
let _neonSql: NeonQueryFunction<false, false> | null = null;
const sql = ((strings: TemplateStringsArray, ...values: unknown[]) => {
  if (!_neonSql) _neonSql = neon(process.env.DATABASE_URL!);
  return _neonSql(strings, ...values);
}) as NeonQueryFunction<false, false>;

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
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
