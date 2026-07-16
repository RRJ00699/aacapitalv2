// app/api/ipo/live-preopen/route.ts
// Listing-day pre-open decision engine. Returns an ARRAY of IPOs listing
// in the current window, each scored independently against the Quick-Profit
// Playbook rules, with a margin-of-safety read and (when available) the
// live pre-open order-book lean.
//
// Timing model (IST): static rules resolve from 09:30; live rules (open-price
// dependent) firm as the open prints. NSE bid cutoff for new listings ~10:14
// (2-min grace before the true ~10:16). The UI shows a countdown to 10:14.
//
// Money-critical rules (size / anchors / OFS / PE / MoS / RHP) come from the
// DB and never depend on the fragile live-depth call — if Kite depth is
// unavailable the book-lean degrades to null, everything else still scores.

import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getBroker } from "@/lib/brokers";

export const dynamic = "force-dynamic";

function db() { return neon(process.env.DATABASE_URL!); }

// ── Playbook win rates (from backtests, for win-rate-weighted confidence) ──
const WIN = {
  mega_positive: 92,      // Rule 1: mega + opening positive
  anchors_30: 77,         // Rule 2: 30+ anchors
  stack: 85,              // Rule 3: mega + positive + 30 anchors
  low_fresh: 86,          // Rule 4: low band + fresh (82–90 midpoint)
  mos: 80,                // MoS-positive on a quality name (thesis-level)
};

const MOS_PASS = 5;       // MoS >= +5% to pass (Rakesh-confirmed)
const PE_RICH = 70;       // ipo_pe > 70 = expensive (Rakesh-confirmed)
const OFS_HEAVY = 50;     // ofs_pct > 50 = OFS-heavy (Rakesh-confirmed)

const num = (v: unknown): number | null => {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

type Rule = { name: string; passed: boolean | null; win: number | null; detail: string };

function scoreStatic(c: Record<string, unknown>) {
  const size = num(c.issue_size_cr);
  const anchors = num(c.anchor_count);
  const ofs = num(c.ofs_pct);
  const price = num(c.issue_price);
  const ipoPe = num(c.ipo_pe);
  // rhp gate comes from ipo_rhp_intel.full_json (aacapital_decision.verdict) —
  // NOT a consolidated column; selecting rhp_verdict/rhp_gate there 500'd this
  // route on 2026-07-16 (second phantom after fair_value).
  const rhpGate = String(c.rhp_gate ?? "").toLowerCase();

  const isMega = size != null && size > 2000;
  const has30 = anchors != null && anchors >= 30;
  const has50 = anchors != null && anchors >= 50;
  const lowBand = price != null && price < 300;
  const fresh = ofs != null && ofs < 30;

  const rules: Rule[] = [];

  // Rule 2 — 30+ anchors (fully static, known pre-listing)
  rules.push({
    name: "30+ anchors",
    passed: anchors == null ? null : has30,
    win: has50 ? 79 : WIN.anchors_30,
    detail: anchors == null ? "anchor count pending"
          : has50 ? `${anchors} anchors (50+ — strongest)`
          : has30 ? `${anchors} anchors`
          : `${anchors} anchors (below 30)`,
  });

  // Rule 4 — low band + fresh issue (static)
  rules.push({
    name: "Low band + fresh",
    passed: (price == null || ofs == null) ? null : (lowBand && fresh),
    win: WIN.low_fresh,
    detail: price == null ? "band pending"
          : `band ₹${price}${lowBand ? " (<300 ✓)" : " (≥300)"}, OFS ${ofs ?? "?"}%${fresh ? " (fresh ✓)" : ""}`,
  });

  // Mega flag (static half of Rule 1 / Rule 3 — the open confirms the rest live)
  rules.push({
    name: "Mega issue (>₹2000cr)",
    passed: size == null ? null : isMega,
    win: WIN.mega_positive,
    detail: size == null ? "size pending" : `₹${Math.round(size)}cr${isMega ? " (mega ✓)" : ""}`,
  });

  // ── AVOID flags (any true = red) ──
  const avoid: string[] = [];
  if (size != null && size < 500) avoid.push(`small issue ₹${Math.round(size)}cr (<500)`);
  if (price != null && price > 600) avoid.push(`pricey band ₹${price} (>600)`);
  if (ofs != null && ofs > OFS_HEAVY) avoid.push(`OFS-heavy ${ofs}% (>50)`);
  if (ipoPe != null && ipoPe > PE_RICH) avoid.push(`expensive P/E ${ipoPe} (>70)`);
  const ofsPeReject = ofs != null && ipoPe != null && ofs > OFS_HEAVY && ipoPe > PE_RICH;

  // ── RHP quality gate (hard) ──
  const rhpReject = rhpGate.includes("reject");

  return { rules, avoid, ofsPeReject, rhpReject, isMega, has30, rhpGate };
}

// Margin-of-safety waterfall: modeled FV → GMP-implied → issue-price floor.
function marginOfSafety(c: Record<string, unknown>) {
  const price = num(c.issue_price);
  const open = num(c.listing_open);
  const gmpPct = num(c.gmp_day_before_pct);
  // fair_value is COMPUTED in /api/ipo-command (fairValue()), not a DB column —
  // selecting it crashed this route on 2026-07-16. Null here → MoS anchors on
  // market-implied-GMP / issue-price-floor, its designed fallback (today's IPOs
  // are GMP-anchored regardless since eps_post is null). TODO backend: persist
  // modeled FV or share the function when the eps_post fix lands.
  const fv = null as number | null;

  let anchor: number | null = null;
  let source = "unavailable";
  let note = "";

  if (fv != null && fv > 0) {
    anchor = fv; source = "modeled";
    note = "Fair value modeled from EPS × peer P/E.";
  } else if (price != null && gmpPct != null) {
    anchor = price * (1 + gmpPct / 100); source = "market-implied-GMP";
    // side note requested by Rakesh: flag that this is GMP-derived, not modeled
    note = `Fair value modeled from EPS is unavailable — using GMP-implied fair (₹${price} + ${gmpPct}% GMP = ₹${Math.round(anchor)}). Market's pre-listing read, not our DCF.`;
  } else if (price != null) {
    anchor = price; source = "issue-price-floor";
    note = "No premium data — using issue price as the floor anchor.";
  }

  if (anchor == null || open == null || open <= 0) {
    return { mosPct: null, cushion: null, fairAnchor: anchor, anchorSource: source,
             gmpRef: gmpPct, note: note || "Awaiting listing open." };
  }
  const mosPct = Math.round(((anchor / open) - 1) * 1000) / 10;
  const cushion = Math.round(anchor - open);
  return { mosPct, cushion, fairAnchor: Math.round(anchor), anchorSource: source, gmpRef: gmpPct, note };
}

// Live rules that depend on the actual open price.
function scoreLive(c: Record<string, unknown>, mos: ReturnType<typeof marginOfSafety>) {
  const price = num(c.issue_price);
  const open = num(c.listing_open);
  const rules: Rule[] = [];

  const openPct = (price != null && open != null && price > 0)
    ? Math.round(((open / price) - 1) * 1000) / 10 : null;
  const openPositive = openPct != null && openPct >= 0;
  const euphoric = openPct != null && openPct >= 50;   // AVOID: pop priced in

  rules.push({
    name: "Opening positive",
    passed: openPct == null ? null : (openPositive && !euphoric),
    win: WIN.mega_positive,
    detail: openPct == null ? "awaiting open"
          : euphoric ? `opened +${openPct}% — euphoric, pop priced in (avoid)`
          : openPositive ? `opened +${openPct}%` : `opened ${openPct}%`,
  });

  rules.push({
    name: "Margin of safety",
    passed: mos.mosPct == null ? null : mos.mosPct >= MOS_PASS,
    win: WIN.mos,
    detail: mos.mosPct == null ? "awaiting fair anchor / open"
          : `${mos.mosPct >= 0 ? "+" : ""}${mos.mosPct}% (₹${mos.cushion} vs fair ₹${mos.fairAnchor}, ${mos.anchorSource})`,
  });

  return { rules, openPct, euphoric };
}

// Win-rate-weighted confidence: blend the win rates of the rules that PASS.
function confidence(all: Rule[], rhpReject: boolean, ofsPeReject: boolean, anyAvoid: boolean) {
  if (rhpReject) return 0;                     // hard kill
  const passed = all.filter(r => r.passed === true && r.win != null);
  if (!passed.length) return 0;
  // weighted average of passed rules' win rates, penalised for avoid flags
  const avg = passed.reduce((s, r) => s + (r.win as number), 0) / passed.length;
  let conf = avg;
  if (ofsPeReject) conf -= 20;
  else if (anyAvoid) conf -= 10;
  return Math.max(0, Math.min(100, Math.round(conf)));
}

export async function GET() {
  try {
    const sql = db();
    // IPOs listing within the live window: from 1 day before today through
    // 7 days after listing (so a fresh listing shows immediately and stays a week).
    const rows = await sql`
      SELECT company_name, nse_symbol, symbol_final, listing_date,
             issue_size_cr, anchor_count, ofs_pct, issue_price, ipo_pe,
             peer_median_pe, listing_open, gmp_day_before_pct,
             (SELECT ri.full_json->'aacapital_decision'->>'verdict' FROM ipo_rhp_intel ri
              WHERE regexp_replace(lower(ri.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                  = regexp_replace(lower(ipo_consolidated.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')
              LIMIT 1) AS rhp_gate
      FROM ipo_consolidated
      WHERE listing_date IS NOT NULL
        AND listing_date >= CURRENT_DATE - INTERVAL '7 days'
        AND listing_date <= CURRENT_DATE + INTERVAL '1 day'
      ORDER BY listing_date ASC, issue_size_cr DESC NULLS LAST
    ` as Array<Record<string, unknown>>;

    // Try to get a live broker once (shared across listings). Degrade gracefully.
    let broker: any = null;
    try {
      broker = getBroker();
      if (!(await broker.isConnected())) broker = null;
    } catch { broker = null; }

    const listings = await Promise.all(rows.map(async (c) => {
      const s = scoreStatic(c);
      const mos = marginOfSafety(c);
      const lv = scoreLive(c, mos);

      // The Stack (Rule 3): mega + opening-positive + 30 anchors
      const stackPassed =
        s.isMega && s.has30 && lv.openPct != null
          ? (lv.openPct >= 0 && lv.openPct < 50)
          : (lv.openPct == null ? null : false);
      const stackRule: Rule = {
        name: "The Stack (mega+positive+30 anchors)",
        passed: stackPassed, win: WIN.stack,
        detail: stackPassed === true ? "cleanest setup — all three align"
              : stackPassed === null ? "awaiting open"
              : "not all three aligned",
      };

      const staticRules = s.rules;
      const liveRules = [...lv.rules, stackRule];
      const anyAvoid = s.avoid.length > 0 || lv.euphoric;
      const conf = confidence([...staticRules, ...liveRules], s.rhpReject, s.ofsPeReject, anyAvoid);

      const allScored = [...staticRules, ...liveRules].filter(r => r.passed !== null);
      const passedCount = allScored.filter(r => r.passed === true).length;

      // Pre-open book lean (live depth — degrades to null off-hours / no creds)
      let book: { discoveryPrice: number | null; buyQty: number; sellQty: number; leanPct: number | null } | null = null;
      const sym = String(c.nse_symbol || c.symbol_final || "").toUpperCase();
      if (broker && sym) {
        try {
          const d = await broker.getDepth(sym, "NSE");
          if (d) {
            const tot = d.totalBuyQty + d.totalSellQty;
            book = {
              discoveryPrice: d.open || d.lastPrice || null,
              buyQty: d.totalBuyQty, sellQty: d.totalSellQty,
              // lean: +100 = all buy (positive listing lean), -100 = all sell
              leanPct: tot > 0 ? Math.round(((d.totalBuyQty - d.totalSellQty) / tot) * 1000) / 10 : null,
            };
          }
        } catch { book = null; }
      }

      return {
        sym,
        company_name: c.company_name,
        listing_date: c.listing_date,
        rules_static: staticRules,
        rules_live: liveRules,
        avoid_flags: s.avoid,
        rhp_reject: s.rhpReject,
        rhp_gate: s.rhpGate,
        mos: {
          pct: mos.mosPct, cushion_rupees: mos.cushion,
          fair_anchor: mos.fairAnchor, anchor_source: mos.anchorSource,
          gmp_ref: mos.gmpRef, note: mos.note,
        },
        open_pct: lv.openPct,
        book,                                   // null when depth unavailable
        rules_passed: passedCount,
        rules_total: allScored.length,
        confidence: conf,
        deadline_ist: "10:14",
        last_eval_ist: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }),
      };
    }));

    return NextResponse.json({
      ok: true,
      window: "listing_date within -7d..+1d",
      book_live: broker != null,               // false = pre-open book not wired this call
      count: listings.length,
      listings,
      fetchedAt: new Date().toISOString(),
    });
  } catch (err: any) {
    return NextResponse.json(
      { ok: false, error: "live-preopen failed", detail: String(err?.message ?? err) },
      { status: 500 }
    );
  }
}
