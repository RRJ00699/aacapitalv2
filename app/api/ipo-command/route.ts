// app/api/ipo-command/route.ts
// Single feed for the redesigned IPO page (/dashboard/ipo2). Read-only.
// Sections: command (upcoming/open/in-window w/ score), live (ticks + levels +
// derived block events), post (audit: band vs outcome), brlm (empirical table),
// all from tables the nightly already populates. Null-safe everywhere.
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

export async function GET() {
  const gate = await requireUser();
  if (gate) return gate;
  try {
    const cards = await sql`
      SELECT company_name, listing_date, ipo_open_date AS open_date, ipo_close_date AS close_date, issue_size_cr,
             issue_price, ipo_score, score_band, score_evidence, gap_bucket,
             listing_gap_pct, final_qib, final_nii, final_retail, final_total,
             brlm_names,
             UPPER(REGEXP_REPLACE(COALESCE(symbol_final, nse_symbol, symbol, ''), '\\.NS$','')) AS sym,
             (SELECT rating FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(symbol_final,nse_symbol,symbol))
                     OR n.company ILIKE '%'||split_part(company_name,' ',1)||'%') LIMIT 1) AS sbi_rating,
             (SELECT peer_name FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(symbol_final,nse_symbol,symbol))
                     OR n.company ILIKE '%'||split_part(company_name,' ',1)||'%') LIMIT 1) AS sbi_peer,
             (SELECT peer_ps FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(symbol_final,nse_symbol,symbol))
                     OR n.company ILIKE '%'||split_part(company_name,' ',1)||'%') LIMIT 1) AS sbi_peer_ps,
             (SELECT note_ps FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(symbol_final,nse_symbol,symbol))
                     OR n.company ILIKE '%'||split_part(company_name,' ',1)||'%') LIMIT 1) AS sbi_highlight,
             CASE
               WHEN ipo_open_date <= CURRENT_DATE AND ipo_close_date >= CURRENT_DATE THEN 'OPEN'
               WHEN listing_date = CURRENT_DATE THEN 'LISTING'
               WHEN listing_date > CURRENT_DATE THEN 'UPCOMING'
               WHEN listing_date >= CURRENT_DATE - 30 THEN 'INWINDOW'
             END AS state,
             (SELECT verdict FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS verdict,
             (SELECT why_trade FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS why_trade,
             (SELECT why_caution FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS why_caution,
             (SELECT why_avoid FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS why_avoid,
             (SELECT regime FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS regime,
             (SELECT quality_promoter FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS quality_promoter
      FROM ipo_consolidated c
      WHERE listing_date >= CURRENT_DATE - 30 OR ipo_close_date >= CURRENT_DATE
         OR ipo_open_date >= CURRENT_DATE
      ORDER BY COALESCE(listing_date, ipo_open_date)`;

    // floor/ceiling derived from candles (first-5-session low/high - the canonical
    // definition, same as the legacy page). No dependency on side tables.
    const dlRaw = await sql`
      WITH w AS (
        SELECT UPPER(REGEXP_REPLACE(c.symbol_final,'\\.NS$','')) AS sym,
               p.date, p.low, p.high, p.close,
               ROW_NUMBER() OVER (PARTITION BY c.symbol_final ORDER BY p.date) AS rn
        FROM ipo_consolidated c
        JOIN price_candles p
          ON UPPER(p.symbol) = UPPER(REGEXP_REPLACE(c.symbol_final,'\\.NS$',''))
         AND p.date >= c.listing_date
        WHERE c.listing_date >= CURRENT_DATE - 45 AND c.symbol_final IS NOT NULL)
      SELECT sym,
             MIN(low)  FILTER (WHERE rn <= 5) AS floor,
             MAX(high) FILTER (WHERE rn <= 5) AS ceiling,
             (ARRAY_AGG(close ORDER BY date DESC))[1] AS last_close,
             MAX(rn) AS t
      FROM w GROUP BY sym`;
    const dl = dlRaw.map((r) => {
      const f = r.floor == null ? null : Number(r.floor);
      const cg = r.ceiling == null ? null : Number(r.ceiling);
      const lc = r.last_close == null ? null : Number(r.last_close);
      return { sym: r.sym, floor: f, ceiling: cg, t: r.t,
        cushion: f && lc ? +(((lc - f) / f) * 100).toFixed(1) : null,
        broke_floor: f != null && lc != null && lc < f,
        broke_ceiling: cg != null && lc != null && lc > cg };
    });

    // live symbols = listing today OR ticks in the last 3h
    const liveSyms = await sql`
      SELECT DISTINCT symbol FROM ipo_tick_feed
      WHERE recorded_at > NOW() - INTERVAL '3 hours'`;
    let live: Record<string, unknown>[] = [];
    let levels: Record<string, unknown>[] = [];
    let blocks: Record<string, unknown>[] = [];
    if (liveSyms.length) {
      const syms = liveSyms.map(r => r.symbol as string);
      live = await sql`
        SELECT symbol, ltp, vwap, vwap_dist, obir, day_volume, momentum, signal,
               recorded_at
        FROM ipo_tick_feed
        WHERE symbol = ANY(${syms}) AND recorded_at > NOW() - INTERVAL '7 hours'
        ORDER BY recorded_at`;
      levels = await sql`
        SELECT DISTINCT ON (symbol) symbol, trade_date, issue_price, listing_open,
               gap_pct, gap_bucket, floor_price, ceiling_price, floor_defenses,
               poc_price, verdict, risk_note, circuit_locked, session_vwap
        FROM ipo_level_analysis
        WHERE symbol = ANY(${syms})
        ORDER BY symbol, trade_date DESC`;
      // block events: volume delta >= 3x median delta for that symbol
      const bySym: Record<string, typeof live> = {};
      for (const t of live) (bySym[t.symbol as string] ||= []).push(t);
      for (const [s, ts] of Object.entries(bySym)) {
        const deltas: { t: unknown; p: unknown; d: number }[] = [];
        for (let i = 1; i < ts.length; i++) {
          const d = Number(ts[i].day_volume || 0) - Number(ts[i - 1].day_volume || 0);
          if (d > 0) deltas.push({ t: ts[i].recorded_at, p: ts[i].ltp, d });
        }
        const sorted = deltas.map(x => x.d).sort((a, b) => a - b);
        const med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
        if (med > 0)
          for (const x of deltas)
            if (x.d >= 3 * med)
              blocks.push({ symbol: s, at: x.t, price: x.p, qty: x.d,
                            mult: +(x.d / med).toFixed(1) });
      }
      blocks = blocks.sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 12);
    }

    // post-listing audit: band vs what happened (d10_best_pct if precomputed)
    const hasD10 = await sql`
      SELECT 1 FROM information_schema.columns
      WHERE table_name='ipo_consolidated' AND column_name='d10_best_pct'`;
    const post = hasD10.length
      ? await sql`SELECT company_name, listing_date, score_band, gap_bucket,
                         listing_gap_pct, d10_best_pct,
                         (SELECT verdict FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS verdict
                  FROM ipo_consolidated c
                  WHERE listing_date < CURRENT_DATE AND score_band IS NOT NULL
                  ORDER BY listing_date DESC LIMIT 30`
      : await sql`SELECT company_name, listing_date, score_band, gap_bucket,
                         listing_gap_pct, NULL AS d10_best_pct,
                         (SELECT verdict FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS verdict
                  FROM ipo_consolidated c
                  WHERE listing_date < CURRENT_DATE AND score_band IS NOT NULL
                  ORDER BY listing_date DESC LIMIT 30`;

    // BRLM empirical (lead manager = first name), listing-day + d10 stats
    const brlm = hasD10.length
      ? await sql`
        SELECT TRIM(SPLIT_PART(brlm_names, ',', 1)) AS lead, COUNT(*) AS n,
               ROUND(AVG(CASE WHEN listing_gap_pct > 0 THEN 100 ELSE 0 END), 0) AS pop_rate,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY listing_gap_pct)::numeric, 1) AS med_gap,
               ROUND(AVG(CASE WHEN d10_best_pct > 0 THEN 100 ELSE 0 END), 0) AS d10_win,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d10_best_pct)::numeric, 1) AS d10_med
        FROM ipo_consolidated c
        WHERE brlm_names IS NOT NULL AND listing_gap_pct IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= 8 ORDER BY n DESC LIMIT 15`
      : await sql`
        SELECT TRIM(SPLIT_PART(brlm_names, ',', 1)) AS lead, COUNT(*) AS n,
               ROUND(AVG(CASE WHEN listing_gap_pct > 0 THEN 100 ELSE 0 END), 0) AS pop_rate,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY listing_gap_pct)::numeric, 1) AS med_gap,
               NULL AS d10_win, NULL AS d10_med
        FROM ipo_consolidated c
        WHERE brlm_names IS NOT NULL AND listing_gap_pct IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= 8 ORDER BY n DESC LIMIT 15`;

    return NextResponse.json({ cards, live, levels, blocks, post, brlm, dl,
      generated_at: new Date().toISOString() });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
