// app/api/access-note/route.ts — public, rate-safe: attaches a short note to the
// newest pending access request (created seconds earlier by the auth callback).
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

export async function POST(req: NextRequest) {
  try {
    const { note } = await req.json();
    const n = String(note || "").slice(0, 200).trim();
    if (!n) return NextResponse.json({ error: "empty" }, { status: 400 });
    await sql`ALTER TABLE access_requests ADD COLUMN IF NOT EXISTS note TEXT`;
    const upd = await sql`
      UPDATE access_requests SET note = ${n}
      WHERE email = (SELECT email FROM access_requests
                     WHERE status = 'pending' AND requested_at > now() - interval '15 minutes'
                       AND note IS NULL
                     ORDER BY requested_at DESC LIMIT 1)
      RETURNING email`;
    if (upd.length && process.env.NTFY_TOPIC) {
      await fetch(`https://ntfy.sh/${process.env.NTFY_TOPIC}`, { method: "POST",
        headers: { Title: "Access request note" },
        body: `${upd[0].email}: "${n}"` }).catch(() => {});
    }
    return NextResponse.json({ ok: true });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}
