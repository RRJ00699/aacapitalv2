// app/api/tracker/route.ts
// Private distraction/frustration tracker. web -> Neon only. Admin-gated (only you).
//   GET    -> all entries, newest first
//   POST   -> add an entry { who, severity, what }
//   DELETE -> remove an entry by id (?id=)
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";

export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

// idempotent DDL — safe to call every request
async function ensureTable() {
  await sql`
    CREATE TABLE IF NOT EXISTS distraction_log (
      id          BIGSERIAL PRIMARY KEY,
      owner_email TEXT NOT NULL,
      who         TEXT NOT NULL,
      severity    TEXT NOT NULL DEFAULT 'mid',
      what        TEXT NOT NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )`;
}

// Real project history (Jul 5–13 2026), grounded in the actual transcripts.
// Seeded once, on the owner's first visit, so the board isn't empty.
const SEED: { who: string; severity: string; what: string; day: number; hhmm: string }[] = [
  { who: "Claude", severity: "mid",  what: "First long session — went in circles on the pipeline setup; needed repeated 'stop' to redirect.", day: 5, hhmm: "20:10" },
  { who: "Claude", severity: "mid",  what: "Score-engine redesign drifted; several 'going in circles' before the PR workflow settled.", day: 6, hhmm: "20:30" },
  { who: "Claude", severity: "high", what: "Anchor/master cleanup — 'what the fuck, you said we uploaded PE comparison from SBI docs, now not a single doc's data is in the DB?' Claimed done, wasn't.", day: 8, hhmm: "01:30" },
  { who: "Claude", severity: "mid",  what: "Edge analysis wandered; 'wasted' + 'doesn't work' before the CIR result landed.", day: 9, hhmm: "21:20" },
  { who: "Claude", severity: "high", what: "'We wasted a whole week to set data.' Data kept changing under you — trust in the dataset broke, forcing a full rebuild.", day: 10, hhmm: "18:20" },
  { who: "Claude", severity: "high", what: "Strategy session — called 'useless' twice; you pushed 'why don't we fix the data / how do we know it's right' because I hadn't nailed it.", day: 10, hhmm: "18:40" },
  { who: "Claude", severity: "mid",  what: "RHP verdict-engine — more circles, another 'wasted', another 'useless' before it worked.", day: 10, hhmm: "20:50" },
  { who: "Claude", severity: "low",  what: "UI/RHP buildout — a few circles, but mostly productive.", day: 11, hhmm: "01:00" },
  { who: "Claude", severity: "mid",  what: "Sonnet RHP moat — 3 hallucinations flagged; claimed things that weren't there.", day: 12, hhmm: "16:20" },
  { who: "Claude", severity: "high", what: "Scaling — hallucinated repeatedly, 'wasted' x3; the UTF-8 write bug kept silently failing on ₹.", day: 12, hhmm: "19:00" },
  { who: "Claude", severity: "low",  what: "Kept saying 'let's close for the day / fresh day' when you had hours and wanted to finish.", day: 13, hhmm: "06:30" },
  { who: "Claude", severity: "mid",  what: "Dragged you into a Screener login/cookie side-quest — nothing to do with your core IPO goal.", day: 13, hhmm: "09:05" },
  { who: "Claude", severity: "high", what: "Green-lit two extraction tabs on one API key without flagging rate-limit risk. They throttled each other — 20 files in 2-3 hrs. Wasted time + spend.", day: 13, hhmm: "07:40" },
  { who: "Claude", severity: "high", what: "Hallucinated the SEBI download script didn't exist — when we'd built it together. Made you re-walk finished work.", day: 13, hhmm: "09:20" },
  { who: "Claude", severity: "high", what: "Built the RHP downloader as a 1035-filing manifest walker instead of your simple 'check newest page, grab the new one' design. Every 'fix' patched my own overcomplication.", day: 13, hhmm: "09:50" },
  { who: "Claude", severity: "mid",  what: "Kept throwing commands without saying WHERE to run them (PC vs VM). You ran VM commands in PowerShell and back, repeatedly.", day: 13, hhmm: "10:15" },
  { who: "Claude", severity: "mid",  what: "Asked clarifying-question prompts when you wanted action — 'your fucking prompt is driving us out of our vision.'", day: 13, hhmm: "10:40" },

  { who: "Claude", severity: "mid",  what: "Kept firing interactive popup prompts that irritate you and break focus — 'those pop up irritate me, make me deviate, why can't you keep it straight.'", day: 13, hhmm: "11:30" },
  { who: "Claude", severity: "low",  what: "Had to be told the tracker's real purpose: it's for a real person with a family and hard time constraints — not a game. Behind every prompt is that person.", day: 13, hhmm: "11:35" },];

async function seedIfEmpty(admin: string) {
  const existing = await sql`SELECT 1 FROM distraction_log WHERE owner_email = ${admin} LIMIT 1`;
  if (existing.length) return;
  for (const s of SEED) {
    const ts = new Date(Date.UTC(2026, 6, s.day, ...s.hhmm.split(":").map(Number) as [number, number], 0)).toISOString();
    await sql`
      INSERT INTO distraction_log (owner_email, who, severity, what, created_at)
      VALUES (${admin}, ${s.who}, ${s.severity}, ${s.what}, ${ts})`;
  }
}

export async function GET() {
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  try {
    await ensureTable();
    await seedIfEmpty(admin);
    const rows = await sql`
      SELECT id, who, severity, what, created_at
      FROM distraction_log
      WHERE owner_email = ${admin}
      ORDER BY created_at DESC`;
    return NextResponse.json({ ok: true, rows });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: true, rows: [], warning: msg });
  }
}

export async function POST(req: NextRequest) {
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  const body = await req.json().catch(() => ({}));
  const who = String(body.who ?? "").trim().slice(0, 120);
  const what = String(body.what ?? "").trim().slice(0, 2000);
  const sev = ["low", "mid", "high"].includes(body.severity) ? body.severity : "mid";
  if (!who || !what) {
    return NextResponse.json({ ok: false, error: "who and what are required" }, { status: 400 });
  }
  try {
    await ensureTable();
    const row = await sql`
      INSERT INTO distraction_log (owner_email, who, severity, what)
      VALUES (${admin}, ${who}, ${sev}, ${what})
      RETURNING id, who, severity, what, created_at`;
    return NextResponse.json({ ok: true, entry: row[0] });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  const id = req.nextUrl.searchParams.get("id");
  if (!id) return NextResponse.json({ ok: false, error: "id required" }, { status: 400 });
  try {
    await ensureTable();
    await sql`DELETE FROM distraction_log WHERE id = ${id} AND owner_email = ${admin}`;
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
