// app/api/ipo/live-preopen/route.ts
// Listing-day pre-open decision engine. Returns an ARRAY of IPOs listing
// in the current window, each scored independently against the Quick-Profit
// Playbook rules, with a margin-of-safety read and (when available) the
// live pre-open order-book lean.
//
// Timing model — OFFICIAL NSE special pre-open for IPO/re-listed (all IST),
// corrected 2026-07-16 after LASER (the old 10:14 model was wrong):
//   09:00–09:45  order entry (modify/cancel allowed)
//   09:45–09:55  matching — opening price discovery, book frozen
//   09:55–10:00  buffer
//   10:00        continuous trading at the discovered open
// DECISION DEADLINE: 09:58 (2-min AACapital buffer before trading opens).
// Static rules resolve from 09:00; discovery-dependent rules firm 09:45–09:55.
//
// Money-critical rules (size / anchors / OFS / PE / MoS / RHP) come from the
// DB and never depend on the fragile live-depth call — if Kite depth is
// unavailable the book-lean degrades to null, everything else still scores.

import { NextResponse } from "next/server";
import { fairValue } from "@/lib/fair-value";
import { neon } from "@neondatabase/serverless";
import { cached } from "@/lib/kv-cache";
import { getBroker } from "@/lib/brokers";
import { getCloudflareContext } from "@opennextjs/cloudflare";

export const dynamic = "force-dynamic";

function db() { return neon(process.env.DATABASE_URL!); }

// ── KV cache (ledger #13) — 60s TTL, HARD BYPASS during the official NSE
// special pre-open window (this file's timing model, corrected 2026-07-16):
// 09:00–10:00 IST order-entry→discovery→buffer, decision deadline 09:58.
// We bypass 08:55–10:05 IST (margin both sides) so the decision screen is
// NEVER served stale in the window it exists for. Outside it, 60s.
// NOTE: reviewer spec said bypass 10:00–10:14 — that is the OLD pre-2026-07-16
// model this route explicitly corrected; implemented against the current one.
const CACHE_KEY = "ipo-live-preopen:v1";
const CACHE_TTL_S = 60;
function inDecisionWindowIST(now = new Date()): boolean {
  const [h, m] = now.toLocaleTimeString("en-GB", {
    timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit",
  }).split(":").map(Number);
  const mins = h * 60 + m;
  return mins >= 8 * 60 + 55 && mins <= 10 * 60 + 5;   // 08:55–10:05 IST
}
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null; }
  catch { return null; }
}

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

  // Rule 5 — 50+ anchors (a distinct, stronger static signal than the 30+ gate:
  // 79% vs 77%). Surfaced as its own rule so the 5-static denominator is fixed
  // and stable, not a moving target that shifts as fields populate.
  rules.push({
    name: "50+ anchors (strongest)",
    passed: anchors == null ? null : has50,
    win: 79,
    detail: anchors == null ? "anchor count pending"
          : has50 ? `${anchors} anchors (50+ ✓)` : `${anchors} anchors (below 50)`,
  });

  // Rule 5b — HOUSE STACK (measured 2026-07-19, n=55, D30 from listing open).
  // 30+ anchors AND >=Rs.200cr AND OFS<30% -> 72.7% win / +17.2% median, vs a
  // 62.2% / +12.7% baseline, and drawdown risk 23.6% vs 32.4%. Fully STATIC —
  // every input is known before the open, so it resolves at 09:30 with the rest.
  // It out-performed every candidate signal tested that day (RHP governance
  // flags, executed early volume, retail price-bid ratio, mutual-fund share);
  // layering MF on top made it WORSE at D1/D2/D3/D5 and D30, so it ships alone.
  {
    const stackOk = anchors != null && anchors >= 30
                 && size != null && size >= 200
                 && ofs != null && ofs < 30;
    const missing: string[] = [];
    if (!(anchors != null && anchors >= 30)) missing.push(anchors == null ? "anchors pending" : `${anchors} anchors`);
    if (!(size != null && size >= 200))      missing.push(size == null ? "size pending" : `₹${Math.round(size)}cr`);
    if (!(ofs != null && ofs < 30))    missing.push(ofs == null ? "OFS pending" : `OFS ${Math.round(ofs)}%`);
    rules.push({
      name: "The House Stack (30 anchors + ₹200cr + fresh)",
      passed: (anchors == null || size == null || ofs == null) ? null : stackOk,
      win: 73,
      detail: stackOk ? "all three — 72.7% win, +17.2% med (D30, n=55)"
                      : `missing: ${missing.join(" · ")}`,
    });
  }

  // Rule 6 — not-expensive P/E (static, known pre-listing). P/E ≤ 70 passes;
  // above is the AVOID-flag territory. Backtest: cheap-vs-peer carries edge,
  // rich P/E decays. Makes the static set 5 rules total.
  rules.push({
    name: "Reasonable P/E (≤70)",
    passed: ipoPe == null ? null : ipoPe <= PE_RICH,
    win: WIN.low_fresh,
    detail: ipoPe == null ? "P/E pending"
          : ipoPe <= PE_RICH ? `P/E ${ipoPe} (≤70 ✓)` : `P/E ${ipoPe} (>70 — rich)`,
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
  // fv from the ONE shared implementation (lib/fair-value.ts) — same number the
  // command-center card shows. Null (missing EPS/peer P/E) → MoS falls to its
  // designed GMP-implied / issue-price-floor chain below, with anchor_source
  // labeling which tier fired. Unified 2026-07-16 after the ₹368-vs-₹419 split.
  const fv = fairValue(c as Record<string, unknown>).fair_value;

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
  // UAT bug 2026-07-21: avg-of-passed ONLY meant 2/9 elite passes (avg 89)
  // outranked 4/9 (avg 84) — coverage never entered. Blend: half the score
  // is the quality of what passed, half scales with HOW MUCH of the rulebook
  // passed. Deterministic, uses only existing backtested win rates.
  const scoreable = all.filter(r => r.win != null).length || 1;
  let conf = avg * (0.5 + 0.5 * (passed.length / scoreable));
  if (ofsPeReject) conf -= 20;
  else if (anyAvoid) conf -= 10;
  return Math.max(0, Math.min(100, Math.round(conf)));
}

export async function GET() {
  const bypass = inDecisionWindowIST();
  const kv = bypass ? null : await getKV();
  if (kv) {
    try {
      const cached = await kv.get(CACHE_KEY);
      if (cached) return new NextResponse(cached, { headers: { "content-type": "application/json", "x-cache": "HIT" } });
    } catch { /* cache read failed — fall through to DB */ }
  }
  try {
    const sql = db();
    // Phase-2 zero-idle: this route is polled every 60s through the 8:55–10:20
    // IST decision window, but the row set below only changes when the nightly
    // pipeline runs. KV-cache the Neon READ for 1h — repeat polls skip Neon.
    // Broker depth + the ipo_preopen_book capture below are live/WRITE paths
    // and intentionally stay per-request.
    const rows = JSON.parse(await cached("live-preopen:rows:v2" /* v2: audit #6 filter */, async () => (await sql`
      SELECT company_name, nse_symbol, symbol_final, listing_date,
             issue_size_cr, anchor_count, ofs_pct, issue_price, ipo_pe,
             peer_median_pe, listing_open, gmp_day_before_pct,
             eps_post, roe, revenue_cagr_3y, debt_equity,
             (SELECT COALESCE(ri.full_json->>'verdict', ri.full_json->'aacapital_decision'->>'verdict') FROM ipo_rhp_intel ri
              WHERE regexp_replace(lower(ri.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                  = regexp_replace(lower(ipo_consolidated.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')
              LIMIT 1) AS rhp_gate,
             (SELECT (n.full_json IS NOT NULL) FROM ipo_research_notes n
              WHERE n.source='SBI'
                AND (UPPER(n.nse_symbol)=UPPER(COALESCE(ipo_consolidated.symbol_final, ipo_consolidated.nse_symbol, ipo_consolidated.symbol))
                     OR regexp_replace(lower(n.company),'(ltd|limited|and|&)|[^a-z0-9]','','g')
                        = regexp_replace(lower(ipo_consolidated.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g'))
              LIMIT 1) AS sbi_parsed
      FROM ipo_consolidated
      WHERE listing_date IS NOT NULL
        AND listing_date >= CURRENT_DATE - INTERVAL '7 days'
        AND listing_date <= CURRENT_DATE + INTERVAL '1 day'
        -- HARD FILTER (audit #6): SME + confirmed <Rs.200cr never reach the
        -- listing-day decision surface (LOCKED rule); NULL size stays.
        AND COALESCE(is_sme, false) = false
        AND (issue_size_cr IS NULL OR issue_size_cr >= 200)
      ORDER BY listing_date ASC, issue_size_cr DESC NULLS LAST
    `), 3600)) as Array<Record<string, unknown>>;

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

      // ── PR-D research-readiness gate (directive: a missing RHP analysis
      // must never appear as a passed company-quality gate; INCOMPLETE is a
      // first-class state, distinct from a scored SKIP). Computed HERE so the
      // UI can only render what the server attests.
      const researchMissing: string[] = [];
      if (c.rhp_gate == null && c.sbi_parsed !== true) researchMissing.push("RHP & SBI research both unread");
      else if (c.rhp_gate == null) researchMissing.push("RHP analysis pending");
      if (c.eps_post == null || c.peer_median_pe == null) researchMissing.push("fair value inputs (EPS/peer P/E)");
      if (c.issue_price == null) researchMissing.push("issue price");
      const researchReady = researchMissing.length === 0;

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
      let livePrice: number | null = null;  // broker last_price — the ONLY live ₹ on listing day (no candles/ticks yet)
      const sym = String(c.nse_symbol || c.symbol_final || "").toUpperCase();
      if (broker && sym) {
        try {
          const d = await broker.getDepth(sym, "NSE");
          livePrice = Number(d?.lastPrice) > 0 ? Number(d!.lastPrice) : null;
          if (d) {
            const tot = d.totalBuyQty + d.totalSellQty;
            book = {
              discoveryPrice: d.open || d.lastPrice || null,
              buyQty: d.totalBuyQty, sellQty: d.totalSellQty,
              // lean: +100 = all buy (positive listing lean), -100 = all sell
              leanPct: tot > 0 ? Math.round(((d.totalBuyQty - d.totalSellQty) / tot) * 1000) / 10 : null,
            };
            // Persist every poll's book snapshot — Zerodha has NO historical
            // depth API, so the only way to ever backtest pre-open lean patterns
            // (Rakesh 2026-07-16) is to capture it ourselves from today forward.
            // Best-effort: a failure here never touches the response.
            try {
              await sql`CREATE TABLE IF NOT EXISTS ipo_preopen_book (
                id SERIAL PRIMARY KEY, symbol TEXT, discovery_price NUMERIC,
                buy_qty BIGINT, sell_qty BIGINT, lean_pct NUMERIC,
                captured_at TIMESTAMPTZ DEFAULT NOW())`;
              await sql`INSERT INTO ipo_preopen_book
                (symbol, discovery_price, buy_qty, sell_qty, lean_pct)
                VALUES (${sym}, ${book.discoveryPrice}, ${book.buyQty},
                        ${book.sellQty}, ${book.leanPct})`;
            } catch { /* capture is best-effort */ }
          }
        } catch { book = null; }
      }

      return {
        sym,
        company_name: c.company_name,
        listing_date: c.listing_date,
        research_ready: researchReady,
        research_missing: researchMissing,   // exact unavailable pieces — the UI names them
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
        live_price: livePrice,
        rules_passed: passedCount,
        rules_total: staticRules.length + liveRules.length,  // FIXED denominator (all rules)
        rules_scored: allScored.length,                       // how many have data yet
        confidence: conf,
        deadline_ist: "09:58",
        last_eval_ist: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }),
      };
    }));

    const payload = JSON.stringify({
      ok: true,
      window: "listing_date within -7d..+1d",
      book_live: broker != null,               // false = pre-open book not wired this call
      count: listings.length,
      listings,
      fetchedAt: new Date().toISOString(),
    });
    if (kv) {
      try { await kv.put(CACHE_KEY, payload, { expirationTtl: CACHE_TTL_S }); }
      catch { /* cache write failed — response still served */ }
    }
    return new NextResponse(payload, {
      headers: { "content-type": "application/json",
                 "x-cache": bypass ? "BYPASS-DECISION-WINDOW" : "MISS" },
    });
  } catch (err: any) {
    return NextResponse.json(
      { ok: false, error: "live-preopen failed", detail: String(err?.message ?? err) },
      { status: 500 }
    );
  }
}
