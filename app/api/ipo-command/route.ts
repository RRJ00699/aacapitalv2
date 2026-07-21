import { fixtureAwareNeon } from "@/lib/db";
// deploy: retrigger 2026-07-11b
// app/api/ipo-command/route.ts
// Single feed for the redesigned IPO page (/dashboard/ipo2). Read-only.
// Sections: command (upcoming/open/in-window w/ score), live (ticks + levels +
// derived block events), post (audit: band vs outcome), brlm (empirical table),
// all from tables the nightly already populates. Null-safe everywhere.
import { NextResponse } from "next/server";
import { fairValue } from "@/lib/fair-value";
import { neon, type NeonQueryFunction } from "@neondatabase/serverless";
import { requireUser } from "@/lib/api-guard";
import { getCloudflareContext } from "@opennextjs/cloudflare";

// KV cache helper — serves the IPO feed from Cloudflare KV so Neon isn't hit on
// every page load. Data only changes nightly (cron), so a short TTL is safe.
const CACHE_KEY = "ipo-command:v4"; // v4 2026-07-22: street-news join (details/review release)
const CACHE_TTL_S = 43200; // 12h — pipeline warms it 2x/day; page loads never hit Neon between runs
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null; }
  catch { return null; } // not on CF (local/Vercel) → no cache, query direct
}

export const dynamic = "force-dynamic";
// lazy neon client — do NOT init at module scope: `next build` (deploy.yml) has no
// DATABASE_URL, and a module-scope neon() throws during page-data collection. Same
// runtime behavior; resolves on first query. (see lib/db.ts for the shared helper)
let _neonSql: NeonQueryFunction<false, false> | null = null;
const sql = ((strings: TemplateStringsArray, ...values: unknown[]) => {
  if (!_neonSql) _neonSql = fixtureAwareNeon();
  return _neonSql(strings, ...values);
}) as NeonQueryFunction<false, false>;

export async function GET(req?: Request) {
  // Pipeline cache-warm: ?warm=1 + machine key skips the session gate AND the
  // cache read (it exists to REBUILD the cache), falling straight to the query
  // + KV write below. Normal loads (harness calls GET() with no req) are
  // unaffected: isWarm is false, session gate + cache read run as before.
  let isWarm = false;
  if (req) {
    try {
      isWarm = new URL(req.url).searchParams.get("warm") === "1"
        && req.headers.get("x-aac-key") === process.env.ADMIN_JOB_KEY;
    } catch { isWarm = false; }
  }
  if (!isWarm) {
    const gate = await requireUser();
    if (gate) return gate;
  }

  const kv = await getKV();
  if (kv && !isWarm) {
    try {
      const cached = await kv.get(CACHE_KEY);
      if (cached) return new NextResponse(cached, { headers: { "content-type": "application/json", "x-cache": "HIT" } });
      // Phase-2 zero-idle: primary TTL lapsed (pipeline late / cold KV region).
      // Serve the long-lived stale twin rather than waking Neon for a read.
      // Header flags it so the UI / monitoring can surface "data may be old".
      const stale = await kv.get(`${CACHE_KEY}:stale`);
      if (stale) return new NextResponse(stale, { headers: {
        "content-type": "application/json", "x-cache": "STALE",
        "x-warning": "primary cache expired; serving stale copy, DB not woken" } });
    } catch { /* cache read failed — fall through to DB */ }
  }

  try {
    // ── DEPLOY-ORDER GUARD (incident 2026-07-21) ──────────────────────────
    // This route queries ipo_insights, whose DDL ships via schema_sync.py on
    // the VM. A deploy that lands BEFORE the next schema run raced the DDL
    // and degraded the whole screen (NeonDbError: relation "ipo_insights"
    // does not exist — owner screenshot). The rebuild path now self-heals
    // with the EXACT schema_sync DDL (single-owner rule intact: schema_sync
    // remains authoritative; a test asserts these two statements stay
    // byte-equivalent). Runs only on cache MISS (~2×/day) — negligible cost,
    // and a deploy can never again depend on cron timing.
    await sql`CREATE TABLE IF NOT EXISTS ipo_insights (
        insight_id BIGSERIAL PRIMARY KEY,
        ipo_id INT NOT NULL,
        category TEXT NOT NULL,
        statement TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('positive','negative','neutral','incomplete')),
        source_type TEXT NOT NULL,
        source_name TEXT, source_document_id TEXT, source_url TEXT,
        source_locator TEXT, source_excerpt TEXT,
        extraction_model TEXT, analysis_model TEXT, analysis_run_id TEXT,
        confidence TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        source_published_at TIMESTAMPTZ, source_downloaded_at TIMESTAMPTZ,
        is_current BOOLEAN DEFAULT TRUE)`;
    await sql`CREATE TABLE IF NOT EXISTS ipo_news (
        id BIGSERIAL PRIMARY KEY,
        company_name TEXT NOT NULL,
        nse_symbol TEXT,
        publisher TEXT NOT NULL,
        headline TEXT NOT NULL,
        url TEXT NOT NULL,
        published_at TIMESTAMPTZ,
        snippet TEXT,
        selection_score INT,
        source TEXT NOT NULL DEFAULT 'rss',
        fetch_status TEXT NOT NULL DEFAULT 'ok',
        is_current BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW())`;
    const cards = await sql`
      SELECT c.company_name, c.listing_date, c.ipo_open_date AS open_date, c.ipo_close_date AS close_date, c.issue_size_cr,
             c.issue_price, c.ipo_score, c.score_band, c.score_evidence, c.gap_bucket,
             c.listing_gap_pct, c.final_qib, c.final_nii, c.final_retail, c.final_total,
             c.brlm_names,
             UPPER(REGEXP_REPLACE(COALESCE(c.symbol_final, c.nse_symbol, c.symbol, ''), '\\.NS$','')) AS sym,
             -- SBI join FIX (audit #7, 2026-07-20): first-word ILIKE matched any
             -- company sharing word 1 ("Laser" -> any Laser*). Now symbol OR
             -- EXACT normalized name (SCHEMA.md strong-key rule) — same
             -- normalization as the ipo_rhp_intel join below.
             (SELECT rating FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1) AS sbi_rating,
             (SELECT full_json FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1) AS sbi_full,
             (SELECT one_line  FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1) AS sbi_one_line,
             (SELECT peer_name FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1) AS sbi_peer,
             (SELECT peer_ps FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1) AS sbi_peer_ps,
             (SELECT note_ps FROM ipo_research_notes n WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(c.symbol_final,c.nse_symbol,c.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')) LIMIT 1) AS sbi_highlight,
             CASE
               -- IST is the ONLY market clock (UTC CURRENT_DATE put Caliber in
               -- Open Now while a CST device said opens-in-1d; 2026-07-17).
               WHEN c.ipo_open_date <= (now() AT TIME ZONE 'Asia/Kolkata')::date AND c.ipo_close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'OPEN'
               WHEN c.listing_date = (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'LISTING'
               WHEN c.listing_date > (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'UPCOMING'
               WHEN c.listing_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date - 30 THEN 'INWINDOW'
             END AS state,
             v.verdict, v.why_trade, v.why_caution, v.why_avoid, v.regime,
             v.quality_promoter, v.ai_summary, v.score AS vscore, v.confidence AS vconf,
             v.sub_scores, v.why_passes,
             ri.verdict AS rhp_verdict, ri.one_line AS rhp_one_line, ri.quality_gate AS rhp_gate,
             ri.margin_of_safety AS rhp_mos, ri.full_json AS rhp_full, ri.confidence AS rhp_confidence,
             f.red_flags, f.green_checks, f.red_count, f.green_count,
             bc.consensus AS street_consensus, bc.n_brokers AS street_brokers, bc.consensus_score AS street_score,
             ii.anchor_count, ii.ofs_cr, ii.fresh_issue_cr, ii.price_band_high AS band_high,
             -- PR-B (Phase 6): machine-readable evidence for the reason builder.
             -- Only CURRENT rows; every row carries the source's own words
             -- (fan-out enforces no-excerpt-no-row). NULL until PR-A's fan-out
             -- has processed an RHP — the UI falls back to legacy rendering.
             (SELECT json_agg(json_build_object(
                     'category', s.category, 'direction', s.direction,
                     'statement', s.statement, 'excerpt', s.source_excerpt,
                     'source', s.source_type, 'locator', s.source_locator))
                FROM ipo_insights s
               WHERE s.ipo_id = ii.id AND s.is_current) AS insights,
             (SELECT json_build_object('publisher', n.publisher, 'headline', n.headline,
                                       'url', n.url, 'published_at', n.published_at, 'snippet', n.snippet)
                FROM ipo_news n
                WHERE n.is_current AND n.fetch_status = 'ok' AND n.publisher <> '-'
                  AND n.url ~* '^https?://' AND n.headline NOT LIKE '<%'
                  AND (UPPER(n.nse_symbol) = UPPER(COALESCE(c.symbol_final, c.nse_symbol, c.symbol)) OR n.company_name = c.company_name)
                ORDER BY (n.source = 'manual') DESC, n.created_at DESC LIMIT 1) AS news,
             ii.price_band_low AS band_low, ii.chittorgarh_slug, ii.score_band, ii.score_expected_win, ii.quality_score, ii.quality_conf,
             ri.rhp_url,
             c.ipo_pe, c.eps_post, c.peer_median_pe, c.roe, c.revenue_cagr_3y,
             c.profit_cagr_3y, c.debt_equity, c.ofs_pct, c.structure_type, c.return_listing_open,
             c.gmp_day_before_pct, c.gmp_max_pct, c.gmp_min_pct
      FROM ipo_consolidated c
      LEFT JOIN ipo_verdicts v ON v.company_name = c.company_name
      LEFT JOIN ipo_flags f ON f.company_name = c.company_name
      LEFT JOIN ipo_broker_consensus bc ON bc.company = c.company_name
      LEFT JOIN ipo_rhp_intel ri ON
        regexp_replace(lower(regexp_replace(ri.company_name, '\\s*&\\s*', ' and ', 'g')), '[^a-z0-9]', '', 'g')
        = regexp_replace(lower(regexp_replace(c.company_name, '\\s*&\\s*', ' and ', 'g')), '[^a-z0-9]', '', 'g')
        OR regexp_replace(lower(ri.company_name), '(ltd|limited|and|&)|[^a-z0-9]', '', 'g')
        = regexp_replace(lower(c.company_name), '(ltd|limited|and|&)|[^a-z0-9]', '', 'g')
      LEFT JOIN ipo_intelligence ii ON regexp_replace(lower(ii.company_name),'(ltd|limited|pvt|private)|[^a-z0-9]','','g')=regexp_replace(lower(c.company_name),'(ltd|limited|pvt|private)|[^a-z0-9]','','g')
      -- CURRENT IPOs ONLY (Rakesh 2026-07-18: Suryoday/Mamaearth/Ventive — all
      -- 2023-24 — leaked via the old "both dates null shows forever" clause).
      -- Window = anchor FIRST lock-in = 30 DAYS post-listing (second lock-in is
      -- 90d but the trade decision lives inside the 30d window). All IST.
      WHERE (c.listing_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date - 30
         OR c.ipo_close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date
         OR c.ipo_open_date  >= (now() AT TIME ZONE 'Asia/Kolkata')::date)
        -- HARD FILTER (audit #6, LOCKED rule: <Rs.200cr = don't touch; SME out
        -- of scope). Was label-only ('AVOID'); now excluded from the feed.
        -- issue_size NULL (size-pending upcoming) stays visible.
        AND COALESCE(c.is_sme, false) = false
        AND (c.issue_size_cr IS NULL OR c.issue_size_cr >= 200)
        -- U7 (2026-07-22, owner evidence): 'Bagmane Prime Office REIT' leaked
        -- via size NULL + is_sme=false. REIT/InvIT units are not IPO equities.
        AND c.company_name !~* '\\y(REIT|InvIT)\\y'
        AND COALESCE(c.symbol_final, c.nse_symbol, c.symbol, '') !~* '(INVIT|REIT)'
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
        WHERE c.listing_date >= CURRENT_DATE - 30 AND c.symbol_final IS NOT NULL)
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

    // (accuracy leaderboard RETIRED 2026-07-15 — table dropped, pipeline step removed)

    // ── Fair Value (Rakesh's 3-step model): base PE × quality ±15% × structure ±10% ──
    function gmpSignal(c: Record<string, unknown>) {
  // GMP day-before is the predictive reading (r=+0.74): >20% strong, 10-20% good, 0-10% weak.
  // day-before is the only predictive GMP reading (r=+0.74).
  const db = c.gmp_day_before_pct == null ? null : Number(c.gmp_day_before_pct);
  const hi = c.gmp_max_pct == null ? null : Number(c.gmp_max_pct);
  const lo = c.gmp_min_pct == null ? null : Number(c.gmp_min_pct);
  let band: string | null = null, hint: string | null = null;
  if (db != null) {
    // +54.5% recomputed 2026-07-15 by owner on clean data (n=14, 14/14 positive at open)
    if (db > 20)      { band = "STRONG"; hint = ">20% GMP: +54.5% avg, 100% win (n=14)"; }
    else if (db >= 10){ band = "GOOD";   hint = "10-20% GMP: +28.2% avg, 89% win"; }
    else if (db >= 0) { band = "WEAK";   hint = "0-10% GMP: +4.2% avg, 57% win"; }
    else              { band = "NEGATIVE"; hint = "negative GMP: discount signal"; }
  }
  return { gmp_day_before: db, gmp_high: hi, gmp_low: lo, gmp_band: band, gmp_hint: hint };
}



    // ── AACapital Playbook rules — applied to every IPO (tested 2026-07-13) ──
    // JUNK FLOOR (IPO_BUSINESS_REQUIREMENTS.md §2, owner-locked): issue size
    // < Rs.200cr is RULED OUT — "below this floor, don't touch". Until now the
    // engine only LABELLED these AVOID and still rendered them alongside real
    // candidates, which is the opposite of "filter junk, focus on good
    // companies". They are now split out of `cards` into `filtered` with the
    // reason attached: enforced, but nothing is hidden or lost.
    const JUNK_FLOOR_CR = 200;
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
      // ── HOUSE STACK (measured 2026-07-19, n=55, D30 from listing open) ──
      // 30+ anchors AND >=Rs.200cr AND OFS<30%  ->  72.7% win, +17.2% median,
      // only 23.6% chance of a -20% drawdown. Baseline is 62.2%/+12.7%/32.4%.
      // This beat every signal tested this weekend: RHP governance flags, early
      // executed volume, retail price-bid ratio and mutual-fund share. Adding MF
      // to it made it WORSE at D1/D2/D3/D5 and D30, so the stack ships alone.
      const stackAnchors = anc != null && anc >= 30;
      const stackFloor   = size >= 200;
      const stackFresh   = ofsPct != null && ofsPct < 30;
      const houseStack   = stackAnchors && stackFloor && stackFresh;
      const stackParts   = [
        { label: "30+ anchors",   pass: stackAnchors, got: anc == null ? "—" : String(anc) },
        { label: "≥₹200cr",       pass: stackFloor,   got: size ? `₹${Math.round(size)}cr` : "—" },
        { label: "OFS <30%",      pass: stackFresh,   got: ofsPct == null ? "—" : `${Math.round(ofsPct)}%` },
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
               playbook_passed: passed, playbook_verdict: verdict_line,
               house_stack: houseStack,
               house_stack_parts: stackParts,
               house_stack_hit: stackParts.filter(x => x.pass).length,
               house_stack_stat: houseStack
                 ? "72.7% win · +17.2% median · D30 (n=55)"
                 : `${stackParts.filter(x => x.pass).length}/3 — baseline 62.2% win`,
               ...fairValue(c), ...gmpSignal(c) };
    });

    // split: investable vs junk-floor (size below the owner-locked floor)
    const investable: Record<string, unknown>[] = [];
    const filtered: Record<string, unknown>[] = [];
    for (const c of enrichedCards as Record<string, unknown>[]) {
      const sz = Number(c.issue_size_cr) || 0;
      if (sz > 0 && sz < JUNK_FLOOR_CR) {
        filtered.push({ ...c, filtered_reason: `issue size ₹${Math.round(sz)}cr < ₹${JUNK_FLOOR_CR}cr junk floor — ruled out (spec §2)` });
      } else {
        investable.push(c);
      }
    }

    // ── Phase-9 structured research block (API-first: UI formats, never
    // infers). Derivations use ONLY approved existing fields — no invented
    // thresholds: company_quality.verdict maps the existing RHP quality gate
    // (accept→GOOD, watch→WATCH, reject→JUNK) and exists ONLY when RHP is
    // CONFIRMED; otherwise status=INCOMPLETE with no verdict at all.
    const enrich = (c: Record<string, unknown>) => {
      const rhpStatus = c.rhp_full ? "CONFIRMED" : c.rhp_url ? "PARTIAL" : "PENDING";
      const sbiStatus = c.sbi_full ? "CONFIRMED" : c.sbi_rating ? "PARTIAL" : "PENDING";
      const fvReady = c.eps_post != null && c.peer_median_pe != null;
      const gate = String(c.rhp_gate ?? "").toLowerCase();
      const cq = rhpStatus === "CONFIRMED"
        ? { status: "CONFIRMED",
            verdict: gate === "reject" ? "JUNK" : gate === "watch" ? "WATCH" : gate ? "GOOD" : "WATCH" }
        : { status: "INCOMPLETE" as const };   // no verdict field on purpose
      const done = [rhpStatus === "CONFIRMED", sbiStatus === "CONFIRMED",
                    c.ipo_score != null, fvReady].filter(Boolean).length;
      return { ...c, research: {
        pipeline_status: rhpStatus === "PENDING" && sbiStatus === "PENDING" ? "ENRICHED"
          : (rhpStatus === "CONFIRMED" && c.ipo_score != null ? "RESEARCH_COMPLETE" : "RESEARCH_PARTIAL"),
        research_completeness: { done, of: 4,
          label: done === 4 ? "Research Complete" : done === 0 ? "Research Pending" : "Research Partial" },
        rhp_status: rhpStatus, sbi_status: sbiStatus,
        company_quality: cq,
        prelisting_score: { score: c.ipo_score ?? null, band: c.score_band ?? null,
          expected_win: c.score_expected_win ?? null },
        fair_value_status: fvReady ? "READY" : "UNAVAILABLE",
        margin_of_safety_status: fvReady ? "READY" : "UNAVAILABLE",
        fair_value_note: fvReady ? null : "Fair value unavailable — requires valid EPS and comparable peer valuation.",
        evidence: c.insights ?? null,
      } };
    };
    const investableR = investable.map(enrich);
    const payload = JSON.stringify({ cards: investableR, filtered, filtered_count: filtered.length,
      live, levels, blocks, post, brlm, dl, track,
      generated_at: new Date().toISOString() });
    if (kv) {
      try { await kv.put(CACHE_KEY, payload, { expirationTtl: CACHE_TTL_S }); } catch { /* cache write best-effort */ }
      // stale twin (7d): the read path's no-Neon fallback when primary lapses
      try { await kv.put(`${CACHE_KEY}:stale`, payload, { expirationTtl: 604800 }); } catch { /* best-effort */ }
    }
    return new NextResponse(payload, { headers: { "content-type": "application/json", "x-cache": "MISS" } });
  } catch (e) {
    // DEGRADED MODE (Rakesh 2026-07-17: one error must never blank the page).
    // A schema drift / SQL error returns an empty-but-renderable payload with
    // the reason — the UI shows a banner and keeps whatever it can render.
    return NextResponse.json({
      cards: [], live: [], levels: [], blocks: [], post: [], brlm: [], dl: [], track: [],
      degraded: String(e).slice(0, 300), generated_at: new Date().toISOString(),
    }, { status: 200 });
  }
}
