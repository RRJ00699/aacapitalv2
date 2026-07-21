// app/api/admin/jobs/route.ts
// Admin job console API. web -> Neon only; the VM's job_runner.py polls job_runs.
//   GET  -> the 25 most recent runs
//   POST -> enqueue a whitelisted job (inserts a job_runs row; the VM claims + runs it)
// Already behind the login wall (proxy.ts); this adds an admin-email gate on top.
import { NextRequest, NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { neon, type NeonQueryFunction } from "@neondatabase/serverless";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// lazy neon client — do NOT init at module scope: `next build` (deploy.yml) has no
// DATABASE_URL, and a module-scope neon() throws during page-data collection. Same
// runtime behavior; resolves on first query. (see lib/db.ts for the shared helper)
let _neonSql: NeonQueryFunction<false, false> | null = null;
const sql = ((strings: TemplateStringsArray, ...values: unknown[]) => {
  if (!_neonSql) _neonSql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);
  return _neonSql(strings, ...values);
}) as NeonQueryFunction<false, false>;

// MUST mirror the JOBS whitelist keys in _scripts/job_runner.py.
const ALLOWED_JOBS = new Set([
  // IPO Power House — IPO-focused jobs only. Non-IPO jobs (screener, old backtests,
  // theses, coverage, backfills) removed to keep the daily pipeline IPO-only.
  "pipeline", "pipeline_weekly",   // main IPO pipeline (lean — 2026-07-21)
  "peer_pe", "peer_pe_notes", "news", "consolidate", "vm_verify",          // fair-value input fetch · reality report
  "token",                         // Kite token (candles need it)
  "gmp",                           // GMP scrape (IPO context)
  "sbi_download", "sbi_parse",     // SBI research notes (street view)
  // IPO daily levels
  // candle sync (post-listing dashboard)
  "rhp_auto",                      // RHP forensic gate
  "sync",                          // git sync (utility)
  // Added 2026-07-18: these existed in job_runner.py AND had console buttons,
  // but this route rejected them with "unknown job '<name>'" — a THIRD
  // definition of the job list that nobody kept in sync.
  "schema", "verdicts", "score", "quality", "smoke", "sbi_haiku",
  "ipomatrix",   // had a button + runner entry but the API rejected it too
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
  const gate = await requireUser(); if (gate) return gate;
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
  const gate = await requireUser(); if (gate) return gate;
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
    try {
      // Neon-free wake flag for the VM runner (1h TTL self-heals stale flags)
      const { env } = getCloudflareContext();
      await (env as Record<string, { put(k: string, v: string, o?: { expirationTtl: number }): Promise<void> }>)
        .JOB_FLAG.put("admin:jobs-pending", "1", { expirationTtl: 3600 });
    } catch { /* flag is an optimization — queueing already succeeded */ }
    return NextResponse.json({ ok: true, id: row[0].id });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
