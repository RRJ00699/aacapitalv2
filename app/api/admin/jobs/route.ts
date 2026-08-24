// app/api/admin/jobs/route.ts
// Admin job console API. Web queues and reads job_runs from D1; the VM runner claims jobs.
import { NextRequest, NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { d1All, d1First } from "@/lib/d1";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

const ALLOWED_JOBS = new Set([
  "pipeline", "pipeline_weekly",
  "ipo_lifecycle",
  "peer_pe", "peer_pe_notes", "news", "vm_verify",
  "token", "gmp", "sync", "schema", "smoke", "ipomatrix", "breadth",
]);

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  try {
    const runs = await d1All(`
      SELECT id, job, status, requested_by, requested_at, started_at,
             finished_at, exit_code, error, log_tail
      FROM job_runs
      ORDER BY requested_at DESC
      LIMIT 25
    `);
    return NextResponse.json({ ok: true, runs });
  } catch (e: unknown) {
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
    const pending = await d1First<{ id: number }>(
      `SELECT id FROM job_runs WHERE job=? AND status IN ('queued','running') LIMIT 1`,
      [job],
    );
    if (pending) {
      return NextResponse.json({ ok: false, error: `'${job}' is already queued or running` }, { status: 409 });
    }

    const rows = await d1All<{ id: number }>(
      `INSERT INTO job_runs(job,status,requested_by) VALUES(?, 'queued', ?) RETURNING id`,
      [job, admin],
    );
    const id = rows[0]?.id;
    if (id == null) throw new Error("job insert returned no id");

    try {
      const { env } = getCloudflareContext();
      await (env as Record<string, { put(k: string, v: string, o?: { expirationTtl: number }): Promise<void> }>)
        .JOB_FLAG.put("admin:jobs-pending", "1", { expirationTtl: 3600 });
    } catch { /* flag is an optimization */ }

    return NextResponse.json({ ok: true, id });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
