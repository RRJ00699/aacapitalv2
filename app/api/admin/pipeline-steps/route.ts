// app/api/admin/pipeline-steps/route.ts — latest run's step board (green/red).
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";

// EXPECTED steps of the production (lean) pipeline — mirrored from
// _scripts/run_ipo_pipeline_lean.py step() calls; a sync test keeps the two
// identical. Lets the board show steps that SHOULD have run but did not —
// exactly how the peer-PE ghost step stayed invisible for weeks.
// weekly:true steps only run with --weekly and are not "missed" on dailies.
export const EXPECTED_LEAN_STEPS: Array<{ step: string; weekly?: boolean }> = [
  { step: "schema sync (single owner of DDL)" },
  { step: "write-constraint guard (A)" },
  { step: "lineage registry (P2)" },
  { step: "NSE discovery (new IPOs)" },
  { step: "scrape IPO calendar + details" },
  { step: "anchor + subscription enrich" },
  { step: "IPOMatrix enrich (new IPOs)" },
  { step: "IPOMatrix refresh (upcoming drip-feed)" },
  { step: "EPS backfill (caution-marked)" },
  { step: "refresh GMP" },
  { step: "delivery pct (NSE bhavcopy)" },
  { step: "market regime + VIX (today)" },
  { step: "candles: in-window daily sync" },
  { step: "listing-day fields (kite)" },
  { step: "derive listing_open" },
  { step: "download SBI notes (new only)" },
  { step: "parse SBI notes -> DB" },
  { step: "SBI Haiku extract ($0.50 cap)" },
  { step: "RHP forensic (Sonnet, $3/day cap)" },
  { step: "ipo score v0 (derived)" },
  { step: "d10 outcome precompute" },
  { step: "reconcile listing dates" },
  { step: "master computables backfill" },
  { step: "peer PE from SBI notes (fill-empty)" },
  { step: "peer PE (fetch, fair-value input)" },
  { step: "sync issue_details -> intelligence (isin)" },
  { step: "rebuild consolidated" },
  { step: "compute IPO verdicts (TRADE/WATCH/CAUTION/AVOID)" },
  { step: "compute red-flag scanner" },
  { step: "Quality score (pre-list)" },
  { step: "sync trade journal (kite orders)" },
  { step: "compute journal outcomes" },
  { step: "backup critical tables" },
  { step: "purge post-lock candles", weekly: true },
  { step: "health-check (gate)" },
  { step: "value-sanity report" },
  { step: "date sanity gate (D)" },
  { step: "freshness monitor (P2)" },
  { step: "smoke probe (live API)" },
];

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;   // ledger #15: was unguarded
  try {
    const sql = neon(process.env.DATABASE_URL!);
    const rows = await sql`
      WITH latest AS (SELECT MAX(ran_at) AS t FROM pipeline_steps)
      SELECT step, ok, LEFT(error, 200) AS error, ran_at
      FROM pipeline_steps, latest
      WHERE ran_at > latest.t - interval '90 minutes'
      ORDER BY ran_at ASC`;
    return NextResponse.json({ ok: true, steps: rows, expected: EXPECTED_LEAN_STEPS });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "";
    if (msg.includes("does not exist")) return NextResponse.json({ ok: true, steps: [], expected: EXPECTED_LEAN_STEPS });
    return NextResponse.json({ ok: false, steps: [], error: msg }, { status: 500 });
  }
}
