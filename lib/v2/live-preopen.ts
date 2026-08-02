// lib/v2/live-preopen.ts — listing-day pre-open scoring, V2 canonical sources.
// Money-critical rules (size / anchors / OFS / P/E / MoS / RHP) come from the
// canonical tables: ipo + ipo_issue + subscription_snapshots + valuation
// (v2-score-% ONLY) + listing_outcomes + decisions.
//
// DROPPED in V2 (no maintained source): SBI notes, street news, and GMP. GMP was
// the market-implied fallback anchor in the margin-of-safety waterfall — a STALE
// GMP anchoring a live listing-day decision is the worst outcome, so the fallback
// is removed and its absence is surfaced explicitly (see marginOfSafety + the
// route's `gmp` block) rather than silently degrading.
import { fairValue } from "@/lib/fair-value";
import type { SqlClient } from "./sql";

const WIN = { mega_positive: 92, anchors_30: 77, stack: 85, low_fresh: 86, mos: 80 };
const MOS_PASS = 5;
const PE_RICH = 70;
const OFS_HEAVY = 50;

export const num = (v: unknown): number | null => {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export type Rule = { name: string; passed: boolean | null; win: number | null; detail: string };

// Row set: every mainboard IPO listing IST-today, >= Rs.200cr (or size-pending),
// REIT/InvIT excluded. valuation is v2-score-% only (v2-rhp-1 carries no score and
// would blank the band). pe_source is exposed so a proxy is never shown as a
// disclosed figure.
export async function fetchPreopenRows(sql: SqlClient) {
  return await sql`
    SELECT i.id AS ipo_id, i.name_display AS company_name, i.symbol AS nse_symbol, i.listing_date,
           iss.issue_size_cr, iss.ofs_cr, iss.fresh_cr, iss.issue_price,
           ss.anchor_count,
           v.pe AS ipo_pe, v.peer_median_pe, v.roe, v.de AS debt_equity,
           v.rev_cagr_3y AS revenue_cagr_3y,
           COALESCE(v.ofs_pct, CASE WHEN COALESCE(iss.ofs_cr,0)+COALESCE(iss.fresh_cr,0) > 0
                THEN 100.0 * iss.ofs_cr / (iss.ofs_cr + iss.fresh_cr) END) AS ofs_pct,
           (v.inputs_used->>'rhp_eps')::numeric AS eps_post,
           v.inputs_used->>'pe_source' AS pe_source,
           lo.listing_open,
           CASE d.fundamental_verdict WHEN 'JUNK' THEN 'reject' WHEN 'WATCH' THEN 'watch'
                WHEN 'GOOD' THEN 'accept' END AS rhp_gate
    FROM ipo i
    JOIN ipo_issue iss ON iss.ipo_id = i.id
    LEFT JOIN LATERAL (SELECT anchor_count FROM subscription_snapshots s
                       WHERE s.ipo_id = i.id ORDER BY is_final DESC, captured_at DESC LIMIT 1) ss ON true
    LEFT JOIN LATERAL (SELECT pe, peer_median_pe, roe, de, rev_cagr_3y, ofs_pct, inputs_used
                       FROM valuation vv WHERE vv.ipo_id = i.id AND vv.engine_version LIKE 'v2-score-%'
                       ORDER BY computed_at DESC LIMIT 1) v ON true
    LEFT JOIN listing_outcomes lo ON lo.ipo_id = i.id
    LEFT JOIN LATERAL (SELECT fundamental_verdict FROM decisions dd
                       WHERE dd.ipo_id = i.id ORDER BY decided_at DESC LIMIT 1) d ON true
    WHERE i.listing_date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date
      AND i.is_mainboard = true
      AND (iss.issue_size_cr IS NULL OR iss.issue_size_cr >= 200)
      AND i.name_display !~* '\\y(REIT|InvIT)\\y'
      AND COALESCE(i.symbol, '') !~* '(INVIT|REIT)'
    ORDER BY iss.issue_size_cr DESC NULLS LAST`;
}

export function scoreStatic(c: Record<string, unknown>) {
  const size = num(c.issue_size_cr);
  const anchors = num(c.anchor_count);
  const ofs = num(c.ofs_pct);
  const price = num(c.issue_price);
  const ipoPe = num(c.ipo_pe);
  const rhpGate = String(c.rhp_gate ?? "").toLowerCase();

  const isMega = size != null && size > 2000;
  const has30 = anchors != null && anchors >= 30;
  const has50 = anchors != null && anchors >= 50;
  const lowBand = price != null && price < 300;
  const fresh = ofs != null && ofs < 30;

  const rules: Rule[] = [];
  rules.push({ name: "30+ anchors", passed: anchors == null ? null : has30, win: has50 ? 79 : WIN.anchors_30,
    detail: anchors == null ? "anchor count pending" : has50 ? `${anchors} anchors (50+ — strongest)` : has30 ? `${anchors} anchors` : `${anchors} anchors (below 30)` });
  rules.push({ name: "Low band + fresh", passed: (price == null || ofs == null) ? null : (lowBand && fresh), win: WIN.low_fresh,
    detail: price == null ? "band pending" : `band ₹${price}${lowBand ? " (<300 ✓)" : " (≥300)"}, OFS ${ofs ?? "?"}%${fresh ? " (fresh ✓)" : ""}` });
  rules.push({ name: "Mega issue (>₹2000cr)", passed: size == null ? null : isMega, win: WIN.mega_positive,
    detail: size == null ? "size pending" : `₹${Math.round(size)}cr${isMega ? " (mega ✓)" : ""}` });
  rules.push({ name: "50+ anchors (strongest)", passed: anchors == null ? null : has50, win: 79,
    detail: anchors == null ? "anchor count pending" : has50 ? `${anchors} anchors (50+ ✓)` : `${anchors} anchors (below 50)` });
  {
    const stackOk = anchors != null && anchors >= 30 && size != null && size >= 200 && ofs != null && ofs < 30;
    const missing: string[] = [];
    if (!(anchors != null && anchors >= 30)) missing.push(anchors == null ? "anchors pending" : `${anchors} anchors`);
    if (!(size != null && size >= 200)) missing.push(size == null ? "size pending" : `₹${Math.round(size)}cr`);
    if (!(ofs != null && ofs < 30)) missing.push(ofs == null ? "OFS pending" : `OFS ${Math.round(ofs)}%`);
    rules.push({ name: "The House Stack (30 anchors + ₹200cr + fresh)",
      passed: (anchors == null || size == null || ofs == null) ? null : stackOk, win: 73,
      detail: stackOk ? "all three — 72.7% win, +17.2% med (D30, n=55)" : `missing: ${missing.join(" · ")}` });
  }
  rules.push({ name: "Reasonable P/E (≤70)", passed: ipoPe == null ? null : ipoPe <= PE_RICH, win: WIN.low_fresh,
    detail: ipoPe == null ? "P/E pending" : ipoPe <= PE_RICH ? `P/E ${ipoPe} (≤70 ✓)` : `P/E ${ipoPe} (>70 — rich)` });

  const avoid: string[] = [];
  if (size != null && size < 500) avoid.push(`small issue ₹${Math.round(size)}cr (<500)`);
  if (price != null && price > 600) avoid.push(`pricey band ₹${price} (>600)`);
  if (ofs != null && ofs > OFS_HEAVY) avoid.push(`OFS-heavy ${ofs}% (>50)`);
  if (ipoPe != null && ipoPe > PE_RICH) avoid.push(`expensive P/E ${ipoPe} (>70)`);
  const ofsPeReject = ofs != null && ipoPe != null && ofs > OFS_HEAVY && ipoPe > PE_RICH;
  const rhpReject = rhpGate.includes("reject");

  return { rules, avoid, ofsPeReject, rhpReject, isMega, has30, rhpGate };
}

// Margin-of-safety waterfall: modeled FV → issue-price floor. The V1 GMP-implied
// tier is REMOVED (no fresh GMP in V2). `gmpRemoved` is surfaced so the UI can say
// so rather than showing a silently weaker anchor.
export function marginOfSafety(c: Record<string, unknown>) {
  const price = num(c.issue_price);
  const open = num(c.listing_open);
  const fv = fairValue(c as Record<string, unknown>).fair_value;

  let anchor: number | null = null;
  let source = "unavailable";
  let note = "";
  if (fv != null && fv > 0) {
    anchor = fv; source = "modeled";
    note = "Fair value modeled from EPS × peer P/E.";
  } else if (price != null) {
    anchor = price; source = "issue-price-floor";
    note = "No modeled fair value — using issue price as the floor anchor. (GMP-implied fallback removed in V2: GMP returns via its own pipeline; a stale GMP must never anchor a listing-day decision.)";
  }

  if (anchor == null || open == null || open <= 0) {
    return { mosPct: null, cushion: null, fairAnchor: anchor, anchorSource: source, gmpRemoved: true, note: note || "Awaiting listing open." };
  }
  const mosPct = Math.round(((anchor / open) - 1) * 1000) / 10;
  const cushion = Math.round(anchor - open);
  return { mosPct, cushion, fairAnchor: Math.round(anchor), anchorSource: source, gmpRemoved: true, note };
}

export function scoreLive(c: Record<string, unknown>, mos: ReturnType<typeof marginOfSafety>) {
  const price = num(c.issue_price);
  const open = num(c.listing_open);
  const rules: Rule[] = [];
  const openPct = (price != null && open != null && price > 0) ? Math.round(((open / price) - 1) * 1000) / 10 : null;
  const openPositive = openPct != null && openPct >= 0;
  const euphoric = openPct != null && openPct >= 50;
  rules.push({ name: "Opening positive", passed: openPct == null ? null : (openPositive && !euphoric), win: WIN.mega_positive,
    detail: openPct == null ? "awaiting open" : euphoric ? `opened +${openPct}% — euphoric, pop priced in (avoid)` : openPositive ? `opened +${openPct}%` : `opened ${openPct}%` });
  rules.push({ name: "Margin of safety", passed: mos.mosPct == null ? null : mos.mosPct >= MOS_PASS, win: WIN.mos,
    detail: mos.mosPct == null ? "awaiting fair anchor / open" : `${mos.mosPct >= 0 ? "+" : ""}${mos.mosPct}% (₹${mos.cushion} vs fair ₹${mos.fairAnchor}, ${mos.anchorSource})` });
  return { rules, openPct, euphoric };
}

export function confidence(all: Rule[], rhpReject: boolean, ofsPeReject: boolean, anyAvoid: boolean) {
  if (rhpReject) return 0;
  const passed = all.filter((r) => r.passed === true && r.win != null);
  if (!passed.length) return 0;
  const avg = passed.reduce((s, r) => s + (r.win as number), 0) / passed.length;
  const scoreable = all.filter((r) => r.win != null).length || 1;
  let conf = avg * (0.5 + 0.5 * (passed.length / scoreable));
  if (ofsPeReject) conf -= 20;
  else if (anyAvoid) conf -= 10;
  return Math.max(0, Math.min(100, Math.round(conf)));
}

// Full per-listing scoring for ONE row (everything except the live broker depth /
// book / live_price, which the route attaches). Extracted from the route so the
// money path is unit-testable against real captured rows. `gmp.available` is always
// false and explicit — never a silent omission.
export function scoreListing(c: Record<string, unknown>) {
  const s = scoreStatic(c);
  const mos = marginOfSafety(c);
  const lv = scoreLive(c, mos);

  const researchMissing: string[] = [];
  if (c.rhp_gate == null) researchMissing.push("RHP analysis pending");
  if (c.eps_post == null && c.ipo_pe == null) researchMissing.push("fair value inputs (EPS / P·E)");
  if (c.issue_price == null) researchMissing.push("issue price");

  const stackPassed = s.isMega && s.has30 && lv.openPct != null
    ? (lv.openPct >= 0 && lv.openPct < 50)
    : (lv.openPct == null ? null : false);
  const stackRule: Rule = {
    name: "The Stack (mega+positive+30 anchors)",
    passed: stackPassed, win: 85,
    detail: stackPassed === true ? "cleanest setup — all three align"
          : stackPassed === null ? "awaiting open" : "not all three aligned",
  };

  const staticRules = s.rules;
  const liveRules = [...lv.rules, stackRule];
  const anyAvoid = s.avoid.length > 0 || lv.euphoric;
  const conf = confidence([...staticRules, ...liveRules], s.rhpReject, s.ofsPeReject, anyAvoid);
  const allScored = [...staticRules, ...liveRules].filter((r) => r.passed !== null);
  const passedCount = allScored.filter((r) => r.passed === true).length;

  return {
    sym: String(c.nse_symbol || "").toUpperCase(),
    company_name: c.company_name,
    listing_date: c.listing_date,
    research_ready: researchMissing.length === 0,
    research_missing: researchMissing,
    rules_static: staticRules,
    rules_live: liveRules,
    avoid_flags: s.avoid,
    rhp_reject: s.rhpReject,
    rhp_gate: s.rhpGate,
    mos: {
      pct: mos.mosPct, cushion_rupees: mos.cushion,
      fair_anchor: mos.fairAnchor, anchor_source: mos.anchorSource, note: mos.note,
    },
    // GMP explicitly UNAVAILABLE in V2 (never a silent fallback anchor).
    gmp: { available: false as const, note: "GMP feed not wired in V2 (returns via its own pipeline); never used as a fallback anchor." },
    pe_source: c.pe_source ?? null,   // disclosure: how P/E was derived
    open_pct: lv.openPct,
    rules_passed: passedCount,
    rules_total: staticRules.length + liveRules.length,
    rules_scored: allScored.length,
    confidence: conf,
    deadline_ist: "09:58",
  };
}
