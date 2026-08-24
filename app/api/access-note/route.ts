// app/api/access-note/route.ts — public, rate-safe D1 update.
import { NextRequest, NextResponse } from "next/server";
import { d1First, d1Run } from "@/lib/d1";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const { note } = await req.json();
    const n = String(note || "").slice(0, 200).trim();
    if (!n) return NextResponse.json({ error: "empty" }, { status: 400 });
    const pending = await d1First<{ email: string }>(
      `SELECT email FROM access_requests
       WHERE status='pending'
         AND datetime(requested_at) > datetime('now','-15 minutes')
         AND note IS NULL
       ORDER BY requested_at DESC LIMIT 1`,
    );
    if (pending?.email) {
      await d1Run("UPDATE access_requests SET note=? WHERE email=?", [n, pending.email]);
      if (process.env.NTFY_TOPIC) {
        await fetch(`https://ntfy.sh/${process.env.NTFY_TOPIC}`, {
          method: "POST",
          headers: { Title: "Access request note" },
          body: `${pending.email}: "${n}"`,
        }).catch(() => {});
      }
    }
    return NextResponse.json({ ok: true });
  } catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}
