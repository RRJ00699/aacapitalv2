// app/api/ipo/live-preopen/route.ts — listing-day pre-open decision engine.
// V2: money-critical rules come from canonical tables (see lib/v2/live-preopen.ts).
// SBI, street news and GMP are DROPPED (no maintained V2 source); GMP's absence is
// surfaced explicitly (gmp.available=false) rather than degrading the MoS anchor.
// Timing/decision-window and live broker depth capture are unchanged.
import { NextResponse } from "next/server";
import { cached } from "@/lib/kv-cache";
import { getBroker } from "@/lib/brokers";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { fixtureAwareNeon } from "@/lib/db";
import { fetchPreopenRows, scoreStatic, marginOfSafety, scoreLive, confidence, type Rule } from "@/lib/v2/live-preopen";
import type { SqlClient } from "@/lib/v2/sql";

export const dynamic = "force-dynamic";
function db() { return fixtureAwareNeon(process.env.DATABASE_URL!); }

// KV cache — 60s TTL, HARD BYPASS during the official NSE special pre-open window
// (08:55–10:05 IST) so the decision screen is never served stale when it matters.
const CACHE_KEY = "ipo-live-preopen:v2";
const CACHE_TTL_S = 60;
function inDecisionWindowIST(now = new Date()): boolean {
  const [h, m] = now.toLocaleTimeString("en-GB", {
    timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit",
  }).split(":").map(Number);
  const mins = h * 60 + m;
  return mins >= 8 * 60 + 55 && mins <= 10 * 60 + 5;
}
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null; }
  catch { return null; }
}

export async function GET() {
  const bypass = inDecisionWindowIST();
  const kv = bypass ? null : await getKV();
  if (kv) {
    try {
      const hit = await kv.get(CACHE_KEY);
      if (hit) return new NextResponse(hit, { headers: { "content-type": "application/json", "x-cache": "HIT" } });
    } catch { /* cache read failed — fall through to DB */ }
  }
  try {
    const sql = db() as unknown as SqlClient;
    // Cache the Neon READ for 1h (key bumped v2->v3 for canonical sources). Broker
    // depth + ipo_preopen_book capture below are live/WRITE paths, per-request.
    const rows = JSON.parse(await cached("live-preopen:rows:v3", () => fetchPreopenRows(sql), 3600)) as Array<Record<string, unknown>>;

    let broker: { isConnected: () => Promise<boolean>; getDepth: (s: string, ex: string) => Promise<{ lastPrice?: number; open?: number; totalBuyQty: number; totalSellQty: number } | null> } | null = null;
    try {
      broker = getBroker() as unknown as typeof broker;
      if (broker && !(await broker.isConnected())) broker = null;
    } catch { broker = null; }

    const listings = await Promise.all(rows.map(async (c) => {
      const s = scoreStatic(c);
      const mos = marginOfSafety(c);
      const lv = scoreLive(c, mos);

      // research-readiness gate — a missing RHP must never read as a passed gate.
      // SBI is no longer part of this (dropped in V2).
      const researchMissing: string[] = [];
      if (c.rhp_gate == null) researchMissing.push("RHP analysis pending");
      if (c.eps_post == null && c.ipo_pe == null) researchMissing.push("fair value inputs (EPS / P·E)");
      if (c.issue_price == null) researchMissing.push("issue price");
      const researchReady = researchMissing.length === 0;

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

      // Pre-open book lean (live depth — degrades to null off-hours / no creds).
      let book: { discoveryPrice: number | null; buyQty: number; sellQty: number; leanPct: number | null } | null = null;
      let livePrice: number | null = null;
      const sym = String(c.nse_symbol || "").toUpperCase();
      if (broker && sym) {
        try {
          const d = await broker.getDepth(sym, "NSE");
          livePrice = Number(d?.lastPrice) > 0 ? Number(d!.lastPrice) : null;
          if (d) {
            const tot = d.totalBuyQty + d.totalSellQty;
            book = {
              discoveryPrice: d.open || d.lastPrice || null,
              buyQty: d.totalBuyQty, sellQty: d.totalSellQty,
              leanPct: tot > 0 ? Math.round(((d.totalBuyQty - d.totalSellQty) / tot) * 1000) / 10 : null,
            };
            // Capture every poll's book snapshot (Zerodha has no historical depth API).
            try {
              await sql`CREATE TABLE IF NOT EXISTS ipo_preopen_book (
                id SERIAL PRIMARY KEY, symbol TEXT, discovery_price NUMERIC,
                buy_qty BIGINT, sell_qty BIGINT, lean_pct NUMERIC,
                captured_at TIMESTAMPTZ DEFAULT NOW())`;
              await sql`INSERT INTO ipo_preopen_book
                (symbol, discovery_price, buy_qty, sell_qty, lean_pct)
                VALUES (${sym}, ${book.discoveryPrice}, ${book.buyQty}, ${book.sellQty}, ${book.leanPct})`;
            } catch { /* capture is best-effort */ }
          }
        } catch { book = null; }
      }

      return {
        sym,
        company_name: c.company_name,
        listing_date: c.listing_date,
        research_ready: researchReady,
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
        gmp: { available: false, note: "GMP feed not wired in V2 (returns via its own pipeline); never used as a fallback anchor." },
        pe_source: c.pe_source ?? null,   // disclosure: how P/E was derived
        open_pct: lv.openPct,
        book,
        live_price: livePrice,
        rules_passed: passedCount,
        rules_total: staticRules.length + liveRules.length,
        rules_scored: allScored.length,
        confidence: conf,
        deadline_ist: "09:58",
        last_eval_ist: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }),
      };
    }));

    const payload = JSON.stringify({
      ok: true,
      window: "listing_date = IST-today",
      book_live: broker != null,
      count: listings.length,
      listings,
      fetchedAt: new Date().toISOString(),
    });
    if (kv) {
      try { await kv.put(CACHE_KEY, payload, { expirationTtl: CACHE_TTL_S }); } catch { /* best-effort */ }
    }
    return new NextResponse(payload, {
      headers: { "content-type": "application/json", "x-cache": bypass ? "BYPASS-DECISION-WINDOW" : "MISS" },
    });
  } catch (err: unknown) {
    return NextResponse.json(
      { ok: false, error: "live-preopen failed", detail: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
