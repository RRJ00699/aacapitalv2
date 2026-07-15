// deploy: retrigger 2026-07-11b
// app/api/ipo-command/route.ts
// Single feed for the redesigned IPO page (/dashboard/ipo2). Read-only.
// Sections: command (upcoming/open/in-window w/ score), live (ticks + levels +
// derived block events), post (audit: band vs outcome), brlm (empirical table),
// all from tables the nightly already populates. Null-safe everywhere.
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";
import { getCloudflareContext } from "@opennextjs/cloudflare";

// KV cache helper — serves the IPO feed from Cloudflare KV so Neon isn't hit on
// every page load. Data only changes nightly (cron), so a short TTL is safe.
const CACHE_KEY = "ipo-command:v1";
const CACHE_TTL_S = 600; // 10 min — Neon queried at most ~6x/hr instead of every load
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null; }
  catch { return null; } // not on CF (local/Vercel) → no cache, query direct
}

export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

export async function GET() {
  const gate = await requireUser();
  if (gate) return gate;

  const kv = await getKV();
  if (kv) {
    try {
      const cached = await kv.get(CACHE_KEY);
      if (cached) return new NextResponse(cached, { headers: { "content-type": "application/json", "x-cache": "HIT" } });
    } catch { /* cache read failed — fall through to DB */ }
  }

  try {
    const cards = await sql`
      SELECT c.company_name, c.listing_date, c.ipo_open_date AS open_date, c.ipo_close_date AS close_date, c.issue_size_cr,
             c.issue_price, c.ipo_score, c.score_band, c.score_evidence, c.gap_bucket,
             c.listing_gap_pct, c.final_qib, c.final_nii, c.final_retail, c.final_total,
             c.brlm_names,
             UPPER(REGEXP_REPLACE(COALESCE(c.symbol_final, c.nse_symbol, c.symbol, ''), '\\.NS$','')) AS sym,
             (SELECT rating FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR n.company ILIKE '%'||split_part(c.company_name,' ',1)||'%') LIMIT 1) AS sbi_rating,
             (SELECT peer_name FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR n.company ILIKE '%'||split_part(c.company_name,' ',1)||'%') LIMIT 1) AS sbi_peer,
             (SELECT peer_ps FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR n.company ILIKE '%'||split_part(c.company_name,' ',1)||'%') LIMIT 1) AS sbi_peer_ps,
             (SELECT note_ps FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR n.company ILIKE '%'||split_part(c.company_name,' ',1)||'%') LIMIT 1) AS sbi_highlight,
             CASE
               WHEN c.ipo_open_date <= CURRENT_DATE AND c.ipo_close_date >= CURRENT_DATE THEN 'OPEN'
               WHEN c.listing_date = CURRENT_DATE THEN 'LISTING'
               WHEN c.listing_date > CURRENT_DATE THEN 'UPCOMING'
               WHEN c.listing_date >= CURRENT_DATE - 30 THEN 'INWINDOW'
             END AS state,
             v.verdict, v.why_trade, v.why_caution, v.why_avoid, v.regime,
             v.quality_promoter, v.ai_summary, v.score AS vscore, v.confidence AS vconf,
             v.sub_scores, v.why_passes,
             ri.verdict AS rhp_verdict, ri.one_line AS rhp_one_line, ri.quality_gate AS rhp_gate,
             ri.margin_of_safety AS rhp_mos, ri.full_json AS rhp_full, ri.confidence AS rhp_confidence,
             f.red_flags, f.green_checks, f.red_count, f.green_count,
             bc.consensus AS street_consensus, bc.n_brokers AS street_brokers, bc.consensus_score AS street_score,
             ii.anchor_count, ii.ofs_cr, ii.fresh_issue_cr, ii.price_band_high AS band_high,
             c.ipo_pe, c.eps_post, c.peer_median_pe, c.roe, c.revenue_cagr_3y,
             c.profit_cagr_3y, c.debt_equity, c.ofs_pct, c.structure_type, c.return_listing_open,
             c.gmp_day_before_pct, c.gmp_max_pct, c.gmp_min_pct, c.gmp_percentage
      FROM ipo_consolidated c
      LEFT JOIN ipo_verdicts v ON v.company_name = c.company_name
      LEFT JOIN ipo_flags f ON f.company_name = c.company_name
      LEFT JOIN ipo_broker_consensus bc ON bc.company = c.company_name
      LEFT JOIN ipo_rhp_intel ri ON
        regexp_replace(lower(regexp_replace(ri.company_name, '\s*&\s*', ' and ', 'g')), '[^a-z0-9]', '', 'g')
        = regexp_replace(lower(regexp_replace(c.company_name, '\s*&\s*', ' and ', 'g')), '[^a-z0-9]', '', 'g')
        OR regexp_replace(lower(ri.company_name), '(ltd|limited|and|&)|[^a-z0-9]', '', 'g')
        = regexp_replace(lower(c.company_name), '(ltd|limited|and|&)|[^a-z0-9]', '', 'g')
      LEFT JOIN ipo_intelligence ii ON regexp_replace(lower(ii.company_name),'[^a-z0-9]','','g')=regexp_replace(lower(c.company_name),'[^a-z0-9]','','g')
      WHERE c.listing_date >= CURRENT_DATE - 30 OR c.ipo_close_date >= CURRENT_DATE
         OR c.ipo_open_date >= CURRENT_DATE
      ORDER BY
        CASE WHEN c.listing_date >= CURRENT_DATE OR c.ipo_close_date >= CURRENT_DATE THEN 0 ELSE 1 END,
        COALESCE(c.listing_date, c.ipo_open_date) DESC`;

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
                         UPPER(REGEXP_REPLACE(COALESCE(c.symbol_final,c.nse_symbol,c.symbol,''),'\\.NS$','')) AS sym,
                         (SELECT verdict FROM ipo_verdicts v WHERE v.company_name = c.company_name LIMIT 1) AS verdict
                  FROM ipo_consolidated c
                  WHERE listing_date < CURRENT_DATE AND score_band IS NOT NULL
                  ORDER BY listing_date DESC LIMIT 30`
      : await sql`SELECT company_name, listing_date, score_band, gap_bucket,
                         listing_gap_pct, NULL AS d10_best_pct,
                         UPPER(REGEXP_REPLACE(COALESCE(c.symbol_final,c.nse_symbol,c.symbol,''),'\\.NS$','')) AS sym,
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

    // TRACK RECORD — computed in its own endpoint to keep this fast
    const track: Record<string, unknown>[] = [];

    // ACCURACY LEADERBOARD — street (listing gain) vs ours (buy-open), separate games
    let leaderboard: Record<string, unknown>[] = [];
    try {
      leaderboard = await sql`SELECT source, call_type, n, avg_outcome, hit_rate, outcome_measure
        FROM ipo_accuracy_leaderboard ORDER BY
        CASE WHEN source LIKE 'Street%' THEN 0 ELSE 1 END, avg_outcome DESC NULLS LAST`;
    } catch (e) { console.error("leaderboard:", e); leaderboard = []; }

    // ── Fair Value (Rakesh's 3-step model): base PE × quality ±15% × structure ±10% ──
    function gmpSignal(c: Record<string, unknown>) {
  // GMP day-before is the predictive reading (r=+0.74): >20% strong, 10-20% good, 0-10% weak.
  // gmp_percentage (broad) is noise (r=-0.05) — shown for context only, not the signal.
  const db = c.gmp_day_before_pct == null ? null : Number(c.gmp_day_before_pct);
  const hi = c.gmp_max_pct == null ? null : Number(c.gmp_max_pct);
  const lo = c.gmp_min_pct == null ? null : Number(c.gmp_min_pct);
  let band: string | null = null, hint: string | null = null;
  if (db != null) {
    if (db > 20)      { band = "STRONG"; hint = ">20% GMP: +50.9% avg, 100% win (n=14)"; }
    else if (db >= 10){ band = "GOOD";   hint = "10-20% GMP: +28.2% avg, 89% win"; }
    else if (db >= 0) { band = "WEAK";   hint = "0-10% GMP: +4.2% avg, 57% win"; }
    else              { band = "NEGATIVE"; hint = "negative GMP: discount signal"; }
  }
  return { gmp_day_before: db, gmp_high: hi, gmp_low: lo, gmp_band: band, gmp_hint: hint };
}

function fairValue(c: Record<string, unknown>) {
      const price = Number(c.issue_price) || 0;
      // Prefer post-issue EPS; fall back to deriving it from ipo_pe (eps = price / P/E)
      // so fair value lights up on the ~392 IPOs that have ipo_pe even when eps_post is null.
      let eps = Number(c.eps_post) || 0;
      let epsSource = "post-issue EPS";
      if (eps <= 0) {
        const ipoPe = Number(c.ipo_pe) || 0;
        if (ipoPe > 0 && price > 0) {
          eps = price / ipoPe;
          epsSource = "EPS derived from issue P/E";
        }
      }
      const peerPE = Number(c.peer_median_pe) || 0;
      if (eps <= 0 || peerPE <= 0 || price <= 0) {
        const missing: string[] = [];
        if (eps <= 0) missing.push("EPS (no eps_post or issue P/E)");
        if (peerPE <= 0) missing.push("peer P/E");
        if (price <= 0) missing.push("issue price");
        return { fair_value: null, fair_mos: null, fair_verdict: null, fair_note: `needs ${missing.join(" + ")}` };
      }
      // Step 1: base
      const base = eps * peerPE;
      // Step 2: quality factor ±15% (ROE, revenue CAGR, low debt)
      const roe = Number(c.roe) || 0;
      const revCagr = Number(c.revenue_cagr_3y) || 0;
      const de = Number(c.debt_equity);
      let q = 1.0;
      if (roe >= 18) q += 0.06; else if (roe > 0 && roe < 10) q -= 0.06;
      if (revCagr >= 20) q += 0.05; else if (revCagr > 0 && revCagr < 8) q -= 0.05;
      if (!isNaN(de) && de <= 0.3) q += 0.04; else if (!isNaN(de) && de > 1.5) q -= 0.04;
      q = Math.max(0.85, Math.min(1.15, q));
      // Step 3: structure factor ±10% (fresh vs OFS)
      const ofsPct = Number(c.ofs_pct);
      let sfac = 1.0;
      if (!isNaN(ofsPct)) {
        if (ofsPct < 20) sfac += 0.06;        // mostly fresh — capex/expansion, good
        else if (ofsPct > 60) sfac -= 0.08;   // mostly OFS — promoter cash-out, weak
      }
      sfac = Math.max(0.90, Math.min(1.10, sfac));
      const fv = base * q * sfac;
      const mos = ((fv / price) - 1) * 100;   // margin of safety vs issue price
      const verdict = mos >= 10 ? "undervalued" : mos <= -10 ? "rich" : "fair";
      return {
        fair_value: Math.round(fv),
        fair_mos: Math.round(mos * 10) / 10,
        fair_verdict: verdict,
        fair_note: `EPS ₹${eps.toFixed(1)}${epsSource.includes("derived") ? "*" : ""} × peer P/E ${peerPE.toFixed(0)} × quality ${q.toFixed(2)} × structure ${sfac.toFixed(2)}${epsSource.includes("derived") ? " · *EPS est. from issue P/E" : ""}`,
      };
    }

    // ── AACapital Playbook rules — applied to every IPO (tested 2026-07-13) ──
    const enrichedCards = (cards as Record<string, unknown>[]).map((c) => {
      const size  = Number(c.issue_size_cr) || 0;
      const gap   = c.listing_gap_pct == null ? null : Number(c.listing_gap_pct);
      const anc   = c.anchor_count == null ? null : Number(c.anchor_count);
      const ofs   = Number(c.ofs_cr) || 0;
      const fresh = Number(c.fresh_issue_cr) || 0;
      const band  = c.band_high == null ? null : Number(c.band_high);
      const gate  = String(c.rhp_gate || "");
      const ofsPct = (ofs + fresh) > 0 ? (100 * ofs / (ofs + fresh)) : null;

      const rules = [
        { key: "mega",    label: "Mega issue (>₹2000cr)",        pass: size >= 2000 },
        { key: "openpos", label: "Opens positive",               pass: gap != null && gap >= 0 },
        { key: "gap15",   label: "Opens +15% or more",           pass: gap != null && gap >= 15 },
        { key: "anchors", label: "30+ anchor investors",         pass: anc != null && anc > 30 },
        { key: "fresh",   label: "Fresh-issue (not OFS-heavy)",  pass: ofsPct != null && ofsPct < 30 },
        { key: "band",    label: "Affordable band (<₹300)",      pass: band != null && band < 300 },
      ];
      const avoid = [
        size > 0 && size < 500 ? "Small issue (<₹500cr)" : null,
        gap != null && gap > 50 ? "Euphoric open (>+50%)" : null,
        gate === "reject" ? "RHP reject (junk)" : null,
      ].filter(Boolean);

      const passed = rules.filter(r => r.pass).length;
      const megaOK = size >= 2000 && gap != null && gap >= 0;
      const stack  = megaOK && anc != null && anc > 30;
      let setup = "watch";
      if (avoid.length) setup = "avoid";
      else if (stack) setup = "stack";          // best: mega + positive + 30 anchors
      else if (megaOK && gap != null && gap >= 15) setup = "core";
      else if (megaOK) setup = "core-lite";

      // clear one-line verdict for the card
      const passedLabels = rules.filter(r => r.pass).map(r => r.label);
      let verdict_line = "";
      if (setup === "avoid")      verdict_line = `Skip — ${avoid.join(", ")}.`;
      else if (setup === "stack") verdict_line = `STACK setup — mega, opens positive, 30+ anchors. The cleanest buy-at-open (85% historically).`;
      else if (setup === "core")  verdict_line = `CORE trade — mega issue opening +15%+. Buy at open (92% historically).`;
      else if (setup === "core-lite") verdict_line = `Core-lite — mega opening positive. Solid buy-at-open.`;
      else verdict_line = passedLabels.length ? `Passes: ${passedLabels.join(" · ")}.` : `No buy-at-open rules met — watch only.`;

      return { ...c, playbook_rules: rules, playbook_avoid: avoid, playbook_setup: setup,
               playbook_passed: passed, playbook_verdict: verdict_line, ...fairValue(c), ...gmpSignal(c) };
    });

    const payload = JSON.stringify({ cards: enrichedCards, live, levels, blocks, post, brlm, dl, track, leaderboard,
      generated_at: new Date().toISOString() });
    if (kv) { try { await kv.put(CACHE_KEY, payload, { expirationTtl: CACHE_TTL_S }); } catch { /* cache write best-effort */ } }
    return new NextResponse(payload, { headers: { "content-type": "application/json", "x-cache": "MISS" } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
