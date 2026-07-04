// app/api/journal/base-rate/route.ts
// Read-only base-rate feedback loop. For every journaled IPO trade, join to
// ipo_consolidated to get its listing gap_bucket, then compare the actual result
// to the VALIDATED backtest base rate for that bucket. No writes. Reads only the
// columns the journal page already uses, so it's consistent with that schema.
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

// Validated base rates from the N≈338 backtest (buy at listing open → best close ≤10d).
// win = % positive, median = median return %. Descriptive, not a buy call.
const BASE: Record<string, { win: number; median: number }> = {
  LOW:  { win: 70, median: 4.3 },
  MID:  { win: 81, median: 10.0 },
  HIGH: { win: 61, median: 3.2 },
};

export async function GET() {
  const gate = await requireUser();
  if (gate) return gate;

  try {
    const rows = await sql`
      SELECT j.id, j.symbol, j.company_name, j.pnl_pct, j.outcome, j.entry_date,
             c.gap_bucket
      FROM trade_journal j
      LEFT JOIN ipo_consolidated c
        ON UPPER(REGEXP_REPLACE(COALESCE(c.symbol_final, c.nse_symbol, c.symbol), '\\.NS$', ''))
         = UPPER(j.symbol)
      WHERE j.symbol IS NOT NULL
      ORDER BY j.entry_date DESC NULLS LAST`;

    const trades = rows.map((r: Record<string, unknown>) => {
      const bucket = (r.gap_bucket as string) || null;
      const b = bucket ? BASE[bucket] : undefined;
      const pnl = r.pnl_pct == null ? null : Number(r.pnl_pct);
      const edge = b && pnl != null ? +(pnl - b.median).toFixed(1) : null;
      return {
        id: r.id, symbol: r.symbol, company_name: r.company_name,
        entry_date: r.entry_date, outcome: r.outcome,
        pnl_pct: pnl, gap_bucket: bucket,
        base_win: b?.win ?? null, base_median: b?.median ?? null,
        edge_vs_base: edge,
      };
    });

    // aggregate your realized results per bucket vs base
    const acc: Record<string, { n: number; wins: number; edgeSum: number; edgeN: number }> = {};
    for (const t of trades) {
      if (!t.gap_bucket || t.pnl_pct == null) continue;
      const a = (acc[t.gap_bucket] ??= { n: 0, wins: 0, edgeSum: 0, edgeN: 0 });
      a.n++;
      if (t.pnl_pct > 0) a.wins++;
      if (t.edge_vs_base != null) { a.edgeSum += t.edge_vs_base; a.edgeN++; }
    }
    const buckets = Object.entries(acc).map(([bucket, a]) => ({
      bucket,
      n: a.n,
      your_win: Math.round((a.wins / a.n) * 100),
      base_win: BASE[bucket]?.win ?? null,
      avg_edge: a.edgeN ? +(a.edgeSum / a.edgeN).toFixed(1) : null,
    }));

    const linked = trades.filter((t) => t.gap_bucket).length;
    return NextResponse.json({ ok: true, trades, buckets, linked, total: trades.length });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "db error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
