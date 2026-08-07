// lib/v2/ipo-command.ts — the /dashboard/ipo2 command-center feed. V2 NARROW FIRST
// CUT (owner-approved): cards + brlm + derived floor/ceiling, all from canonical
// tables. DROPPED (no maintained V2 source, first cut): the live-ticks section,
// rich intraday levels, street news, SBI notes, and GMP. Sections stay in the
// envelope as empty arrays so the UI's destructuring never breaks.
//
// Sources: ipo + ipo_issue + subscription_snapshots + valuation (v2-score-% ONLY)
// + decisions + rhp_findings + insights + source_facts(brlm_names) + listing_outcomes
// + market_candles (first-5-session floor/ceiling).
import { fairValue } from "@/lib/fair-value";
import { calculateProForma } from "@/lib/intelligence/ipo-profile";
import { attachCanonicalInputs, buildCanonicalProFormaInputs } from "@/lib/intelligence/canonical-inputs";
import type { SqlClient } from "./sql";

export async function fetchCards(sql: SqlClient) {
  const rows=await sql`
    SELECT i.id AS ipo_id, i.isin, i.name_display AS company_name, i.listing_date,
           iss.open_date, iss.close_date, iss.issue_size_cr, iss.issue_price,
           iss.ofs_cr, iss.fresh_cr AS fresh_issue_cr, iss.band_hi AS band_high,
           iss.band_lo AS band_low, iss.lot_size, iss.face_value, iss.allotment_date,
           UPPER(COALESCE(i.symbol, '')) AS sym,
           ss.anchor_count, ss.qib_x AS final_qib, ss.nii_x AS final_nii,
           ss.retail_x AS final_retail, ss.total_x AS final_total,
           v.score AS ipo_score, v.score_band, v.pe AS ipo_pe, v.pb, v.peer_median_pe,
           v.roe, v.roce, v.de AS debt_equity, v.rev_cagr_3y AS revenue_cagr_3y, v.ofs_pct,
           v.fair_value_lo, v.fair_value_hi, v.quality_promoter,
           v.inputs_used->>'pe_source' AS pe_source, v.inputs_used->>'pb_source' AS pb_source,
           v.inputs_used->>'rhp_eps' AS eps_post,v.inputs_used->>'rhp_eps' AS rhp_eps,
           v.inputs_used->>'rhp_eps_field' AS rhp_eps_field,
           d.fundamental_verdict AS verdict,
           CASE d.fundamental_verdict WHEN 'JUNK' THEN 'reject' WHEN 'WATCH' THEN 'watch'
                WHEN 'GOOD' THEN 'accept' END AS rhp_gate,
           lo.gap_pct AS listing_gap_pct,
           rf.red_flag_count, rf.junk_signals,
           bf.value AS brlm_names,
           CASE
             WHEN iss.open_date <= (now() AT TIME ZONE 'Asia/Kolkata')::date AND iss.close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'OPEN'
             WHEN i.listing_date = (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'LISTING'
             WHEN i.listing_date > (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'UPCOMING'
             WHEN i.listing_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date - 30 THEN 'INWINDOW'
           END AS state,
           (SELECT json_agg(json_build_object('category', s.category, 'direction', s.direction,
                   'statement', s.statement, 'excerpt', s.excerpt, 'source', s.source_type))
              FROM insights s WHERE s.ipo_id = i.id AND s.is_current) AS insights
    FROM ipo i
    JOIN ipo_issue iss ON iss.ipo_id = i.id
    LEFT JOIN LATERAL (SELECT anchor_count, qib_x, nii_x, retail_x, total_x FROM subscription_snapshots s
                       WHERE s.ipo_id = i.id ORDER BY is_final DESC, captured_at DESC LIMIT 1) ss ON true
    LEFT JOIN LATERAL (SELECT score, score_band, pe, pb, peer_median_pe, roe, roce, de, rev_cagr_3y,
                              ofs_pct, fair_value_lo, fair_value_hi, quality_promoter, inputs_used
                       FROM valuation vv WHERE vv.ipo_id = i.id AND vv.engine_version LIKE 'v2-score-%'
                       ORDER BY computed_at DESC LIMIT 1) v ON true
    LEFT JOIN LATERAL (SELECT fundamental_verdict FROM decisions dd WHERE dd.ipo_id = i.id
                       ORDER BY decided_at DESC LIMIT 1) d ON true
    LEFT JOIN listing_outcomes lo ON lo.ipo_id = i.id
    LEFT JOIN LATERAL (SELECT red_flag_count, junk_signals FROM rhp_findings r WHERE r.ipo_id = i.id
                       ORDER BY analyzed_at DESC LIMIT 1) rf ON true
    LEFT JOIN LATERAL (SELECT value FROM source_facts sf WHERE sf.ipo_id = i.id AND sf.field = 'brlm_names'
                       ORDER BY fetched_at DESC LIMIT 1) bf ON true
    WHERE i.is_mainboard = true
      AND (i.listing_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date - 30
           OR iss.close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date
           OR iss.open_date  >= (now() AT TIME ZONE 'Asia/Kolkata')::date)
      AND (iss.issue_size_cr IS NULL OR iss.issue_size_cr >= 200)
      AND i.name_display !~* '\\y(REIT|InvIT)\\y'
      AND COALESCE(i.symbol, '') !~* '(INVIT|REIT)'
    ORDER BY
      CASE WHEN i.listing_date >= CURRENT_DATE OR iss.close_date >= CURRENT_DATE THEN 0 ELSE 1 END,
      COALESCE(i.listing_date, iss.open_date) DESC`;
  return attachCanonicalInputs(sql,rows);
}

export async function fetchDl(sql: SqlClient) {
  const rows = await sql`
    WITH w AS (
      SELECT i.id, UPPER(COALESCE(i.symbol, '')) AS sym, mc.d, mc.l, mc.h, mc.c,
             ROW_NUMBER() OVER (PARTITION BY i.id ORDER BY mc.d) AS rn
      FROM ipo i
      JOIN market_candles mc ON mc.ipo_id = i.id AND mc.d >= i.listing_date
      WHERE i.listing_date >= CURRENT_DATE - 30 AND i.is_mainboard = true
    )
    SELECT sym, MIN(l) FILTER (WHERE rn <= 5) AS floor, MAX(h) FILTER (WHERE rn <= 5) AS ceiling,
           (ARRAY_AGG(c ORDER BY d DESC))[1] AS last_close, MAX(rn) AS t
    FROM w GROUP BY sym`;
  return rows.map((r) => {
    const f = r.floor == null ? null : Number(r.floor);
    const cg = r.ceiling == null ? null : Number(r.ceiling);
    const lc = r.last_close == null ? null : Number(r.last_close);
    return { sym: r.sym, floor: f, ceiling: cg, t: r.t,
      cushion: f && lc ? +(((lc - f) / f) * 100).toFixed(1) : null,
      broke_floor: f != null && lc != null && lc < f,
      broke_ceiling: cg != null && lc != null && lc > cg };
  });
}

export async function fetchPost(sql: SqlClient) {
  return await sql`
    SELECT i.name_display AS company_name, i.listing_date, v.score_band,
           lo.gap_pct AS listing_gap_pct, UPPER(COALESCE(i.symbol, '')) AS sym,
           d.fundamental_verdict AS verdict
    FROM ipo i
    LEFT JOIN listing_outcomes lo ON lo.ipo_id = i.id
    LEFT JOIN LATERAL (SELECT score_band FROM valuation vv WHERE vv.ipo_id = i.id
                       AND vv.engine_version LIKE 'v2-score-%' ORDER BY computed_at DESC LIMIT 1) v ON true
    LEFT JOIN LATERAL (SELECT fundamental_verdict FROM decisions dd WHERE dd.ipo_id = i.id
                       ORDER BY decided_at DESC LIMIT 1) d ON true
    WHERE i.listing_date < CURRENT_DATE AND i.is_mainboard = true AND v.score_band IS NOT NULL
    ORDER BY i.listing_date DESC LIMIT 30`;
}

export async function fetchBrlm(sql: SqlClient) {
  // BRLM lead = first name in source_facts.brlm_names; empirical listing-pop stats
  // joined to listing_outcomes.gap_pct. (V1 also had d10 stats — no canonical source.)
  return await sql`
    WITH b AS (
      SELECT sf.ipo_id, TRIM(SPLIT_PART(sf.value, ',', 1)) AS lead
      FROM source_facts sf WHERE sf.field = 'brlm_names' AND sf.value IS NOT NULL AND sf.value <> ''
    )
    SELECT b.lead, COUNT(*) AS n,
           ROUND(AVG(CASE WHEN lo.gap_pct > 0 THEN 100 ELSE 0 END), 0) AS pop_rate,
           ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lo.gap_pct)::numeric, 1) AS med_gap
    FROM b JOIN listing_outcomes lo ON lo.ipo_id = b.ipo_id AND lo.gap_pct IS NOT NULL
    GROUP BY b.lead HAVING COUNT(*) >= 8 ORDER BY n DESC LIMIT 15`;
}

// Pure: apply the AACapital playbook rules + fair value, split junk-floor, attach
// the structured research block. GMP signal and SBI status are removed for V2.
export function enrichCards(cards: Record<string, unknown>[]) {
  const JUNK_FLOOR_CR = 200;
  const enriched = cards.map((c) => {
    const size = Number(c.issue_size_cr) || 0;
    const gap = c.listing_gap_pct == null ? null : Number(c.listing_gap_pct);
    const anc = c.anchor_count == null ? null : Number(c.anchor_count);
    const ofs = Number(c.ofs_cr) || 0;
    const fresh = Number(c.fresh_issue_cr) || 0;
    const band = c.band_high == null ? null : Number(c.band_high);
    const gate = String(c.rhp_gate || "");
    const ofsPct = (ofs + fresh) > 0 ? (100 * ofs / (ofs + fresh)) : null;

    const rules = [
      { key: "mega", label: "Mega issue (>₹2000cr)", pass: size >= 2000 },
      { key: "openpos", label: "Opens positive", pass: gap != null && gap >= 0 },
      { key: "gap15", label: "Opens +15% or more", pass: gap != null && gap >= 15 },
      { key: "anchors", label: "30+ anchor investors", pass: anc != null && anc > 30 },
      { key: "fresh", label: "Fresh-issue (not OFS-heavy)", pass: ofsPct != null && ofsPct < 30 },
      { key: "band", label: "Affordable band (<₹300)", pass: band != null && band < 300 },
    ];
    const stackAnchors = anc != null && anc >= 30;
    const stackFloor = size >= 200;
    const stackFresh = ofsPct != null && ofsPct < 30;
    const houseStack = stackAnchors && stackFloor && stackFresh;
    const stackParts = [
      { label: "30+ anchors", pass: stackAnchors, got: anc == null ? "—" : String(anc) },
      { label: "≥₹200cr", pass: stackFloor, got: size ? `₹${Math.round(size)}cr` : "—" },
      { label: "OFS <30%", pass: stackFresh, got: ofsPct == null ? "—" : `${Math.round(ofsPct)}%` },
    ];
    const avoid = [
      size > 0 && size < 500 ? "Small issue (<₹500cr)" : null,
      gap != null && gap > 50 ? "Euphoric open (>+50%)" : null,
      gate === "reject" ? "RHP reject (junk)" : null,
    ].filter(Boolean);

    const passed = rules.filter((r) => r.pass).length;
    const megaOK = size >= 2000 && gap != null && gap >= 0;
    const stack = megaOK && anc != null && anc > 30;
    let setup = "watch";
    if (avoid.length) setup = "avoid";
    else if (stack) setup = "stack";
    else if (megaOK && gap != null && gap >= 15) setup = "core";
    else if (megaOK) setup = "core-lite";

    const passedLabels = rules.filter((r) => r.pass).map((r) => r.label);
    let verdict_line = "";
    if (setup === "avoid") verdict_line = `Skip — ${avoid.join(", ")}.`;
    else if (setup === "stack") verdict_line = "STACK setup — mega, opens positive, 30+ anchors. The cleanest buy-at-open (85% historically).";
    else if (setup === "core") verdict_line = "CORE trade — mega issue opening +15%+. Buy at open (92% historically).";
    else if (setup === "core-lite") verdict_line = "Core-lite — mega opening positive. Solid buy-at-open.";
    else verdict_line = passedLabels.length ? `Passes: ${passedLabels.join(" · ")}.` : "No buy-at-open rules met — watch only.";

    const {inputs}=buildCanonicalProFormaInputs(c); const intelligence=calculateProForma(inputs);
    const intelligence_summary=intelligence.status==="AVAILABLE"?{status:"AVAILABLE",reported:{pat_cr:intelligence.reported_pat_cr,eps:intelligence.reported_eps,pe:intelligence.reported_pe},pro_forma:{pat_cr:intelligence.pro_forma_pat_cr,eps:intelligence.pro_forma_eps,pe:intelligence.pro_forma_pe,net_debt_cr:intelligence.net_debt_cr},known_transformations:[],fair_value:intelligence.fair_value,margin_of_safety_pct:intelligence.margin_of_safety_pct,red_flags:c.junk_signals??[],rhp_verdict:c.verdict??null}:{status:"UNAVAILABLE",reason:"Canonical financial evidence is insufficient.",missing_inputs:intelligence.missing_inputs};
    return { ...c, intelligence_summary, playbook_rules: rules, playbook_avoid: avoid, playbook_setup: setup,
      playbook_passed: passed, playbook_verdict: verdict_line,
      house_stack: houseStack, house_stack_parts: stackParts,
      house_stack_hit: stackParts.filter((x) => x.pass).length,
      house_stack_stat: houseStack ? "72.7% win · +17.2% median · D30 (n=55)"
        : `${stackParts.filter((x) => x.pass).length}/3 — baseline 62.2% win`,
      ...fairValue(c) } as Record<string, unknown>;
  });

  const investable: Record<string, unknown>[] = [];
  const filtered: Record<string, unknown>[] = [];
  for (const c of enriched) {
    const sz = Number(c.issue_size_cr) || 0;
    if (sz > 0 && sz < JUNK_FLOOR_CR) {
      filtered.push({ ...c, filtered_reason: `issue size ₹${Math.round(sz)}cr < ₹${JUNK_FLOOR_CR}cr junk floor — ruled out (spec §2)` });
    } else {
      investable.push(c);
    }
  }

  // structured research block — RHP-driven (SBI removed in V2). company_quality
  // verdict exists ONLY when RHP is confirmed; otherwise INCOMPLETE with no verdict.
  const withResearch = investable.map((c) => {
    const rhpStatus = (c.verdict != null || c.red_flag_count != null) ? "CONFIRMED" : "PENDING";
    const fvReady = c.eps_post != null || c.ipo_pe != null;
    const gate = String(c.rhp_gate ?? "").toLowerCase();
    const cq = rhpStatus === "CONFIRMED"
      ? { status: "CONFIRMED", verdict: gate === "reject" ? "JUNK" : gate === "watch" ? "WATCH" : gate ? "GOOD" : "WATCH" }
      : { status: "INCOMPLETE" as const };
    const done = [rhpStatus === "CONFIRMED", c.ipo_score != null, fvReady].filter(Boolean).length;
    return { ...c, research: {
      pipeline_status: rhpStatus === "CONFIRMED" && c.ipo_score != null ? "RESEARCH_COMPLETE"
        : rhpStatus === "PENDING" ? "ENRICHED" : "RESEARCH_PARTIAL",
      research_completeness: { done, of: 3, label: done === 3 ? "Research Complete" : done === 0 ? "Research Pending" : "Research Partial" },
      rhp_status: rhpStatus,
      company_quality: cq,
      prelisting_score: { score: c.ipo_score ?? null, band: c.score_band ?? null },
      fair_value_status: fvReady ? "READY" : "UNAVAILABLE",
      fair_value_note: fvReady ? null : "Fair value unavailable — requires valid EPS/P·E and comparable peer valuation.",
      evidence: c.insights ?? null,
    } };
  });

  return { investable: withResearch, filtered };
}

export async function buildCommand(sql: SqlClient) {
  const cards = await fetchCards(sql);
  const { investable, filtered } = enrichCards(cards);
  const dl = await fetchDl(sql);
  const post = await fetchPost(sql);
  const brlm = await fetchBrlm(sql);
  return {
    cards: investable, filtered, filtered_count: filtered.length,
    live: [], levels: [], blocks: [],   // dropped: no maintained V2 tick/level feed (first cut)
    post, brlm, dl, track: [],
    notes: { dropped: ["live-ticks", "intraday-levels", "news", "sbi", "gmp"],
      reason: "no maintained V2 source (narrow first cut); floor/ceiling derived from market_candles" },
    generated_at: new Date().toISOString(),
  };
}
