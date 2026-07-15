// app/api/cron/premarket-brief/route.ts
// RETIRED. This route was part of the abandoned early-vision engine
// (ipo_master / predictions / feature_store / similarity + the
// multibagger-discovery and convergence-score endpoints). Per the
// canonical data architecture (DATA_ARCHITECTURE.md), those tables are
// FROZEN — no backend route may read them. This route is not wired into
// the pipeline or job_runner and is not called by the UI, so it is
// neutralized rather than repointed. The frozen tables stay in the DB
// untouched; this endpoint no longer reads any of them.

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(
    { ok: false, disabled: true, reason: "premarket-brief retired — see DATA_ARCHITECTURE.md" },
    { status: 410 }
  );
}
