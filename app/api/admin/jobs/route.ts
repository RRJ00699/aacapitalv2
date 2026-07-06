// app/api/admin/jobs/route.ts
// Admin job console API. web -> Neon only; the VM's job_runner.py polls job_runs.
//   GET  -> the 25 most recent runs
//   POST -> enqueue a whitelisted job (inserts a job_runs row; the VM claims + runs it)
// Already behind the login wall (proxy.ts); this adds an admin-email gate on top.
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";

export const dynamic = "force-dynamic";

const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

// MUST mirror the JOBS whitelist keys in _scripts/job_runner.py.
const ALLOWED_JOBS = new Set([
  "pipeline", "pipeline_weekly", "token", "gmp",
  "sbi_download", "sbi_parse", "levels", "theses", "sync", "exit_backtest",
]);

// Same DDL job_runner.py uses, so the first enqueue works even before the VM
// has run once. IF NOT EXISTS => idempotent, safe to call every POST.
async function ensureTable() {
  await sql`
    CREATE TABLE IF NOT EXISTS job_runs (
      id           BIGSERIAL PRIMARY KEY,
      job          TEXT NOT NULL,
      status       TEXT NOT NULL DEFAULT 'queued',
      requested_by TEXT,
      requested_at TIMESTAMPTZ DEFAULT now(),
      started_at   TIMESTAMPTZ,
      finished_at  TIMESTAMPTZ,
      exit_code    INT,
      error        TEXT,
      log_tail     TEXT
    )`;
}

export async function GET() {
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  try {
    const runs = await sql`
      SELECT id, job, status, requested_by, requested_at, started_at,
             finished_at, exit_code, error, log_tail
      FROM job_runs
      ORDER BY requested_at DESC
      LIMIT 25`;
    return NextResponse.json({ ok: true, runs });
  } catch (e: unknown) {
    // table may not exist yet (job_runner.py never ran) — treat as empty, not an error
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: true, runs: [], warning: msg });
  }
}

export async function POST(req: NextRequest) {
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });

  const body = await req.json().catch(() => ({}));
  const job = String(body.job ?? "");
  if (!ALLOWED_JOBS.has(job)) {
    return NextResponse.json({ ok: false, error: `unknown job '${job}'` }, { status: 400 });
  }

  try {
    await ensureTable();
    // don't double-queue: block if this job is already queued or running
    const pending = await sql`
      SELECT id FROM job_runs
      WHERE job = ${job} AND status IN ('queued', 'running')
      LIMIT 1`;
    if (pending.length) {
      return NextResponse.json(
        { ok: false, error: `'${job}' is already queued or running` },
        { status: 409 },
      );
    }
    const row = await sql`
      INSERT INTO job_runs (job, status, requested_by)
      VALUES (${job}, 'queued', ${admin})
      RETURNING id`;
    return NextResponse.json({ ok: true, id: row[0].id });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
