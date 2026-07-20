"use client";
import React, { useState } from "react";

/* ────────────────────────────────────────────────────────────────────────
   IpoCard v2 — every locked edge on the card. Extends v1's language
   (dial · pill · pills · gold CTA), adds the previously-unrendered signal:
   • SETUP line — the tested playbook engine (STACK/CORE/core-lite/avoid)
   • GMP strip — day-before % (the r=+0.74 predictor) + hi–lo range + band
   • EDGE grid — anchors · OFS mix · PE vs peer · QIB · band, colored by
     the locked thresholds from IPO_BUSINESS_REQUIREMENTS.md §5
   • FV empty-state — shows fair_note reason, never a fake number
   • RHP expand — + governance flag chips when present in full_json
   All --t-* vars → light/dark/PWA identical. Bindings: route.ts payload only.
   ──────────────────────────────────────────────────────────────────────── */

const MONO = "var(--f-mono)";
const DISPLAY = "var(--f-display)";
const C = {
  bg: "var(--t-bg)", surface: "var(--t-surface)", surface2: "var(--t-surface2)",
  border: "var(--t-border)", line: "var(--t-line)", text: "var(--t-text)",
  sub: "var(--t-sub)", meta: "var(--t-meta)", dim: "var(--t-dim)",
  green: "var(--t-green)", greenBg: "var(--t-greenBg)", greenBd: "var(--t-greenBd)",
  blue: "var(--t-blue)", blueBg: "var(--t-blueBg)", blueBd: "var(--t-blueBd)",
  amber: "var(--t-amber)", amberBg: "var(--t-amberBg)", amberBd: "var(--t-amberBd)",
  red: "var(--t-red)", redBg: "var(--t-redBg)", redBd: "var(--t-redBd)",
  grayBg: "var(--t-grayBg)", gold: "var(--t-gold)",
};
const num: React.CSSProperties = { fontFamily: MONO, fontVariantNumeric: "tabular-nums" };
const D = (v: unknown) => String(v ?? "").slice(0, 10);
const N = (v: unknown) => (v == null ? null : Number(v));

type Row = Record<string, unknown>;

function verdictStyle(v: string | null): { col: string; bg: string; bd: string; label: string } {
  switch (v) {
    case "TRADE": return { col: C.green, bg: C.greenBg, bd: C.greenBd, label: "TRADE" };
    case "AVOID": return { col: C.red, bg: C.redBg, bd: C.redBd, label: "AVOID" };
    case "CAUTION": return { col: C.amber, bg: C.amberBg, bd: C.amberBd, label: "CAUTION" };
    case "WATCH": default: return { col: C.gold, bg: C.amberBg, bd: C.amberBd, label: v || "WATCH" };
  }
}

function items(s: unknown): string[] {
  if (!s) return [];
  const str = String(s).trim();
  // Postgres array literal leaking through ({"a","b"} or {a,b}) — parse, don't print
  if (/^\{.*\}$/.test(str)) {
    const inner = str.slice(1, -1);
    const parts = inner.match(/"([^"]*)"|[^,]+/g) || [];
    return parts.map((p) => p.replace(/^"|"$/g, "").trim()).filter(Boolean);
  }
  return str.split(/[|;]|(?:^|\n)\s*[•✓✕⚠●]\s*/).map((x) => x.trim().replace(/^[•✓✕⚠●]\s*/, "")).filter(Boolean);
}

function scoreColor(score: number | null): string {
  if (score == null) return C.dim;
  if (score >= 65) return C.green;
  if (score >= 40) return C.amber;
  return C.red;
}

function ScoreDial({ score, conf, sub, tally, band, win }: { score: number | null; conf: number | null; sub?: string; tally?: boolean; band?: string | null; win?: number | null }) {
  // tally mode: ipo_score v0 is a backtested additive tally (-4..+6), NOT a
  // percent — showing it on a 0-100 arc made every IPO read as 0/1/-2 garbage
  // (Rakesh 2026-07-17). Number = signed tally; arc = position within the
  // tally's true range (visual only).
  const col = tally ? (score != null && score >= 2 ? C.green : score != null && score <= -1 ? C.red : C.amber) : scoreColor(score);
  const pct = score == null ? 0
    : tally ? (win != null ? Math.max(0, Math.min(100, Number(win))) : Math.max(0, Math.min(100, ((Number(score) + 4) / 10) * 100)))
    : Math.max(0, Math.min(100, score));
  const r = 30, circ = 2 * Math.PI * r, off = circ * (1 - pct / 100);
  return (
    <div style={{ position: "relative", width: 72, height: 72, flexShrink: 0 }}>
      <svg width="72" height="72" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="36" cy="36" r={r} fill="none" stroke={C.grayBg} strokeWidth="5" />
        {score != null && (
          <circle cx="36" cy="36" r={r} fill="none" stroke={col} strokeWidth="5"
            strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
            style={{ transition: "stroke-dashoffset .6s var(--ease), stroke .3s var(--ease)" }} />
        )}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        {score == null
          ? <span style={{ fontSize: 7.5, color: C.dim, textAlign: "center", lineHeight: 1.2 }}>scores at{"\n"}listing</span>
          : tally
            ? <>
                {/* BIG number = backtested win% (what a user grasps); the raw
                   tally is the small signed chip below. Fixes "0/1/-2 means
                   nothing" — the number people see is now 60-81, not the tally. */}
                <span style={{ ...num, fontSize: 24, fontWeight: 800, color: col, lineHeight: 1 }}>
                  {win != null ? `${Math.round(Number(win))}%` : (band ? String(band).slice(0, 4) : "—")}</span>
                <span style={{ fontSize: 7.5, color: C.meta, marginTop: 1, textAlign: "center", lineHeight: 1.15 }}>
                  {band ? String(band).toLowerCase() : ""}{win != null ? " hist" : ""}</span>
                <span style={{ ...num, fontSize: 8, color: C.dim, marginTop: 1 }}>
                  tally {Number(score) > 0 ? `+${Math.round(Number(score))}` : Math.round(Number(score))}</span>
              </>
            : <>
                <span style={{ ...num, fontSize: 26, fontWeight: 800, color: col, lineHeight: 1 }}>{Math.round(Number(score))}</span>
                {conf != null && <span style={{ fontSize: 8.5, color: C.meta, marginTop: 1 }}>{conf}%</span>}
                {sub && <span style={{ fontSize: 7, color: C.meta, marginTop: 1, textAlign: "center", lineHeight: 1.1 }}>{sub}</span>}
              </>}
      </div>
    </div>
  );
}

function Pill({ kind, text }: { kind: "pass" | "warn" | "neutral"; text: string }) {
  const map = {
    pass: { bg: C.greenBg, fg: C.green, bd: C.greenBd, mark: "✓" },
    warn: { bg: C.redBg, fg: C.red, bd: C.redBd, mark: "✕" },
    neutral: { bg: C.grayBg, fg: C.sub, bd: C.border, mark: "•" },
  }[kind];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, background: map.bg, color: map.fg,
      border: `1px solid ${map.bd}`, fontSize: 12, fontWeight: 500, padding: "5px 11px",
      borderRadius: 999, lineHeight: 1.3,
    }}>
      <span style={{ fontWeight: 800 }}>{map.mark}</span>{text}
    </span>
  );
}

function Metric({ label, value, sub, color, emphasis }: { label: string; value: string; sub?: string; color?: string; emphasis?: boolean }) {
  return (
    <div style={{
      flex: "1 1 96px", minWidth: 0, background: C.bg,
      border: `1px solid ${emphasis ? C.gold : C.border}`,
      borderRadius: 11, padding: "10px 13px",
    }}>
      <div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.5, textTransform: "uppercase", fontWeight: 600 }}>{label}</div>
      <div style={{ ...num, fontSize: 20, fontWeight: 800, color: color || C.text, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", lineHeight: 1.1 }}>
        {value}
      </div>
      {sub && <div style={{ ...num, fontSize: 12, fontWeight: 600, color: color || C.meta, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>}
    </div>
  );
}

/* ── Setup line — the playbook engine finally on screen ─────────────────── */
function setupStyle(setup: string | null): { col: string; bg: string; mark: string; name: string } {
  switch (setup) {
    case "stack":     return { col: C.gold,  bg: C.amberBg, mark: "◆◆", name: "STACK" };
    case "core":      return { col: C.green, bg: C.greenBg, mark: "◆",  name: "CORE" };
    case "core-lite": return { col: C.green, bg: C.greenBg, mark: "◇",  name: "CORE-LITE" };
    case "avoid":     return { col: C.red,   bg: C.redBg,   mark: "✕",  name: "SKIP" };
    default:          return { col: C.sub,   bg: C.grayBg,  mark: "•",  name: "WATCH" };
  }
}

/* ── GMP strip — day-before is THE predictor (r=+0.74) ──────────────────── */
function gmpBandStyle(band: string | null): { col: string; bg: string; bd: string } {
  switch (band) {
    case "STRONG":   return { col: C.green, bg: C.greenBg, bd: C.greenBd };
    case "GOOD":     return { col: C.green, bg: C.greenBg, bd: C.greenBd };
    case "WEAK":     return { col: C.amber, bg: C.amberBg, bd: C.amberBd };
    case "NEGATIVE": return { col: C.red,   bg: C.redBg,   bd: C.redBd };
    default:         return { col: C.sub,   bg: C.grayBg,  bd: C.border };
  }
}

function GmpStrip({ db, hi, lo, band, hint }: { db: number | null; hi: number | null; lo: number | null; band: string | null; hint: string | null }) {
  if (db == null && hi == null && lo == null) return null;
  const bs = gmpBandStyle(band);
  // range bar: lo→hi with a marker at day-before
  const min = Math.min(lo ?? db ?? 0, 0);
  const max = Math.max(hi ?? db ?? 0, 1);
  const span = max - min || 1;
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - min) / span) * 100));
  return (
    <div style={{ marginTop: 14, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 11, padding: "11px 13px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.5, textTransform: "uppercase", fontWeight: 600 }}>GMP day-before</div>
        {db != null && <span style={{ ...num, fontSize: 20, fontWeight: 800, color: bs.col }}>{db > 0 ? "+" : ""}{db}%</span>}
        {band && <span style={{ background: bs.bg, color: bs.col, border: `1px solid ${bs.bd}`, fontSize: 11, fontWeight: 800, padding: "3px 9px", borderRadius: 999, letterSpacing: 0.4 }}>{band}</span>}
      </div>
      {(hi != null || lo != null) && (
        <div style={{ marginTop: 9 }}>
          <div style={{ position: "relative", height: 6, background: C.grayBg, borderRadius: 3 }}>
            {lo != null && hi != null && (
              <div style={{ position: "absolute", left: `${pos(lo)}%`, width: `${Math.max(2, pos(hi) - pos(lo))}%`, top: 0, bottom: 0, background: bs.bg, border: `1px solid ${bs.bd}`, borderRadius: 3 }} />
            )}
            {db != null && (
              <div style={{ position: "absolute", left: `calc(${pos(db)}% - 4px)`, top: -3, width: 8, height: 12, background: bs.col, borderRadius: 2 }} />
            )}
          </div>
          <div style={{ ...num, display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.meta, marginTop: 4 }}>
            <span>low {lo != null ? `${lo}%` : "—"}</span>
            <span>high {hi != null ? `${hi}%` : "—"}</span>
          </div>
        </div>
      )}
      {hint && <div style={{ fontSize: 11.5, color: C.meta, marginTop: 7 }}>{hint}</div>}
    </div>
  );
}

/* ── Edge grid — locked thresholds from the spec (§5) ───────────────────── */
type Edge = { label: string; value: string; sub?: string; state: "pass" | "warn" | "neutral" | "na" };
function edgeColor(state: Edge["state"]): string {
  return state === "pass" ? C.green : state === "warn" ? C.red : state === "na" ? C.dim : C.text;
}
function EdgeGrid({ edges }: { edges: Edge[] }): React.ReactElement | null {
  if (!edges.length) return null;
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
      {edges.map((e, i) => (
        <div key={i} style={{ flex: "1 1 88px", minWidth: 88, background: e.state === "na" ? "transparent" : C.bg,
          border: e.state === "na" ? `1px dashed ${C.border}` : `1px solid ${e.state === "pass" ? C.greenBd : e.state === "warn" ? C.redBd : C.border}`,
          borderRadius: 10, padding: "8px 10px", transition: "border-color .25s var(--ease)" }}>
          <div style={{ fontSize: 9.5, color: C.meta, letterSpacing: 0.4, textTransform: "uppercase", fontWeight: 600 }}>{e.label}</div>
          <div style={{ ...num, fontSize: 15, fontWeight: 800, color: edgeColor(e.state), marginTop: 3, whiteSpace: "nowrap" }}>{e.value}</div>
          {e.sub && <div style={{ fontSize: 10, color: C.meta, marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/* ── RHP governance flag chips (rendered only when present in full_json) ── */
const RHP_FLAGS: { key: string; label: string }[] = [
  { key: "auditor_qualified", label: "Auditor qualified" },
  { key: "sebi_action", label: "SEBI action" },
  { key: "criminal_litigation", label: "Criminal litigation" },
  { key: "related_party_concern", label: "Related-party concern" },
  { key: "ofs_heavy", label: "OFS-heavy exit" },
  { key: "customer_concentration_high", label: "Customer concentration" },
  { key: "numbers_integrity_flag", label: "Numbers integrity" },
  { key: "cash_conversion_flag", label: "Cash conversion" },
  { key: "working_capital_flag", label: "Working capital" },
  { key: "contingent_liabilities_material", label: "Contingent liabilities" },
  { key: "promoter_pledge_flag", label: "Promoter pledge" },
  { key: "debt_trend", label: "Debt rising" },
];
function rhpFlagChips(fj: Record<string, unknown> | null): { raised: string[]; clear: number } {
  if (!fj) return { raised: [], clear: 0 };
  // flags live under full_json.db_fields (verified: TrustReport in ipo2/page.tsx
  // reads the same path); fall back to `flags` / top level for older records.
  const src = (typeof fj.db_fields === "object" && fj.db_fields !== null ? fj.db_fields
    : typeof fj.flags === "object" && fj.flags !== null ? fj.flags : fj) as Record<string, unknown>;
  // four flags are string-valued, not boolean (same semantics as TrustReport)
  const STR_RAISED: Record<string, string> = {
    numbers_integrity_flag: "watch", cash_conversion_flag: "weak",
    working_capital_flag: "watch", debt_trend: "rising",
  };
  const raised: string[] = []; let clear = 0;
  for (const f of RHP_FLAGS) {
    const v = src[f.key];
    const strBad = STR_RAISED[f.key];
    if (strBad !== undefined) {
      if (v === strBad) raised.push(f.label);
      else if (v != null) clear++;
    } else if (v === true) raised.push(f.label);
    else if (v === false) clear++;
  }
  return { raised, clear };
}

export default function IpoCard({ c, onJourney, onLive }: { c: Row; onJourney?: (sym: string) => void; onLive?: () => void }) {
  const [showRules, setShowRules] = useState(false);
  const [showRhp, setShowRhp] = useState(false);

  // vscore = verdict engine 0-100. ipo_score is a RAW additive factor score
  // (±few points) — leaking it into a 0-100 dial rendered "-1"/"-2" (2026-07-16).
  // Pre-scoring IPOs now get an honest awaiting dial instead.
  // vscore (0-100, verdict engine) once listed; BEFORE listing, the dial now
  // shows the pre-list QUALITY score (computed from RHP forensics + promoter +
  // structure + valuation + fundamentals — docs/QUALITY_SCORE_SPEC.md, v1
  // weights pending calibration). "scores at listing" only when neither exists.
  const q = c.quality_score as number | null;
  const score = (c.vscore ?? q) as number | null;
  const isQuality = c.vscore == null && q != null;
  const conf = N(c.vconf);
  const verdict = (c.verdict as string) ?? null;
  const vs = verdictStyle(verdict);
  const isTrade = verdict === "TRADE";
  const sym = c.sym ? String(c.sym) : "";
  const listed = !!c.listing_date && (c.state === "INWINDOW" || c.state === "POST");

  const passes = [...items(c.why_trade), ...items(c.why_passes)].map((t) => ({ kind: "pass" as const, text: t }));
  const warns = [...items(c.why_avoid), ...items(c.red_flags)].map((t) => ({ kind: "warn" as const, text: t }));
  const neutrals = items(c.why_caution).map((t) => ({ kind: "neutral" as const, text: t }));
  const rawPills: { kind: "pass" | "warn" | "neutral"; text: string }[] = [...passes, ...warns, ...neutrals];
  const seen = new Set<string>();
  const allPills = rawPills.filter((p) => {
    const key = p.text.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 24);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
  const shown = showRules ? allPills : allPills.slice(0, 3);
  const moreCount = allPills.length - 3;

  const fv = N(c.fair_value);
  const mos = N(c.fair_mos);
  const fvVerdict = c.fair_verdict as string | null;
  const fvColor = fvVerdict === "undervalued" ? C.green : fvVerdict === "rich" ? C.red : C.text;
  const fvNote = c.fair_note ? String(c.fair_note) : null;

  const street = c.street_consensus ? String(c.street_consensus) : null;
  const brokers = N(c.street_brokers);
  const rhpGate = c.rhp_gate ? String(c.rhp_gate) : null;

  // Setup (playbook engine — route.ts computes, v2 renders)
  const setup = c.playbook_setup ? String(c.playbook_setup) : null;
  const setupLine = c.playbook_verdict ? String(c.playbook_verdict) : null;
  const ss = setupStyle(setup);

  // GMP (derived fields only — gmp_day_before_pct/max/min upstream)
  const gmpDb = N(c.gmp_day_before);
  const gmpHi = N(c.gmp_high);
  const gmpLo = N(c.gmp_low);
  const gmpBand = c.gmp_band ? String(c.gmp_band) : null;
  const gmpHint = c.gmp_hint ? String(c.gmp_hint) : null;

  // Edge grid — locked thresholds (spec §5)
  const anc = N(c.anchor_count);
  const ofsCr = N(c.ofs_cr), freshCr = N(c.fresh_issue_cr);
  const ofsPct = ofsCr != null && freshCr != null && (ofsCr + freshCr) > 0
    ? Math.round((100 * ofsCr) / (ofsCr + freshCr)) : N(c.ofs_pct);
  const ipoPe = N(c.ipo_pe), peerPe = N(c.peer_median_pe);
  const peRatio = ipoPe != null && peerPe != null && peerPe > 0 ? ipoPe / peerPe : null;
  const qib = N(c.final_qib);
  const bandHigh = N(c.band_high);
  const bandLow = N(c.band_low);
  const lifecycle = (() => {
    const day = (x: unknown) => { const d = new Date(String(x)); return isNaN(+d) ? null : d; };
    const od = day(c.open_date), cd = day(c.close_date), ld = day(c.listing_date);
    // Today in IST — the market's clock, never the device's (CST is a day
    // behind IST every evening; that skew was the Caliber timeline bug).
    const istParts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const [iy, im, idd] = istParts.split("-").map(Number);
    const t0 = new Date(iy, im - 1, idd);
    const dd = (a: Date, b: Date) => Math.round((+a - +b) / 86400000);
    if (od && t0 < od) return { v: `opens in ${dd(od, t0)}d`, s: `subscription ${String(c.open_date).slice(5,10)} → ${String(c.close_date ?? "").slice(5,10)}`, st: "na" as const };
    if (od && cd && t0 >= od && t0 <= cd) {
      const n = dd(t0, od) + 1, last = dd(cd, t0) === 0;
      return { v: last ? `Day ${n} — closes today` : `Day ${n} of ${dd(cd, od) + 1}`, s: last ? "book closes 5pm" : `closes ${String(c.close_date).slice(5,10)}`, st: last ? "warn" as const : "pass" as const };
    }
    if (cd && ld && t0 > cd && t0 < ld) return { v: `lists in ${dd(ld, t0)}d`, s: "allotment window", st: "neutral" as const };
    if (ld && dd(t0, ld) === 0) return { v: "LISTING TODAY", s: "decision window 9:00–9:58", st: "warn" as const };
    if (ld && t0 > ld) return { v: `listed ${dd(t0, ld)}d ago`, s: String(c.listing_date).slice(0, 10), st: "na" as const };
    return null;
  })();
  const edges: Edge[] = [
    ...(lifecycle ? [{ label: "Timeline", value: lifecycle.v, sub: lifecycle.s, state: lifecycle.st } as Edge] : []),
    { label: "Anchors", value: anc != null ? String(anc) : "—",
      sub: anc != null ? (anc > 30 ? "30+ · 77% edge" : "below 30") : "awaiting",
      state: anc == null ? "na" : anc > 30 ? "pass" : "neutral" },
    { label: "OFS mix", value: ofsPct != null ? `${ofsPct}%` : "—",
      // Phase-7 (2026-07-20): ">60 = promoter cash-out" was an evidence-free
      // interpretation of a structured number. The BACKTESTED fact is the
      // fresh-vs-OFS win-rate split; seller identity/motive needs the RHP.
      sub: ofsPct != null ? (ofsPct < 30 ? "fresh-heavy · 82%" : ofsPct > 60 ? "OFS-heavy" : "mixed") : "awaiting",
      state: ofsPct == null ? "na" : ofsPct < 30 ? "pass" : ofsPct > 60 ? "warn" : "neutral" },
    { label: "PE vs peer", value: peRatio != null ? `${peRatio.toFixed(2)}×` : ipoPe != null ? `${ipoPe.toFixed(0)}` : "—",
      sub: peRatio != null ? (peRatio < 0.6 ? "cheap · 77% edge" : peRatio > 1 ? "above peers" : "near peers") : peerPe == null ? "awaiting peer P/E" : "awaiting",
      state: peRatio == null ? "na" : peRatio < 0.6 ? "pass" : "neutral" },
    { label: "QIB", value: qib != null ? `${qib}×` : "—",
      sub: qib != null ? (qib >= 5 && qib <= 25 ? "5–25× · 78% zone" : qib > 25 ? "hot book" : "light book") : "awaiting close",
      state: qib == null ? "na" : qib >= 5 && qib <= 25 ? "pass" : "neutral" },
    // Band tile: a bare ₹high just repeated the IPO PRICE tile (Rakesh's
    // redundancy call, 2026-07-16). Show the low–high RANGE when we have it;
    // when we don't, the tile is pure duplication — drop it.
    ...(bandHigh != null && bandLow != null && bandLow < bandHigh ? [{
      label: "Band", value: `₹${bandLow}–${bandHigh}`,
      sub: bandHigh < 300 ? "under ₹300 · wins" : "premium band",
      state: (bandHigh < 300 ? "pass" : "neutral") } as Edge] : []),
  ];

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${isTrade ? C.greenBd : C.border}`,
      borderLeft: `4px solid ${vs.col}`,
      borderRadius: 16, padding: "18px clamp(14px, 4vw, 22px)", marginBottom: 14,
      boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
    }}>
      {/* ROW 1: hero */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: "clamp(19px, 5.2vw, 23px)", fontWeight: 800, color: C.text, lineHeight: 1.12, letterSpacing: -0.4 }}>
            {String(c.company_name || "")}
          </div>
          <div style={{ fontSize: 12, color: C.meta, marginTop: 5 }}>
            {/* OPEN-NOW (subscription window live). Shipped in #192, LOST in a
                later merge of this file, restored 2026-07-18. NOT the same as the
                "LIVE — trade it" chip, which keys off listing-day ticks. */}
            {String(c.state ?? "").toUpperCase() === "OPEN"
              ? <span style={{ color: C.green, fontWeight: 800 }}>● OPEN NOW</span>
              : (c.state ? String(c.state) : "")}{c.listing_date ? ` · lists ${D(c.listing_date)}` : ""}
            {c.quality_promoter === true ? <span style={{ color: C.gold, fontWeight: 600 }}> · ★ Quality promoter</span> : null}
            {/* HOUSE STACK — the only signal that beat baseline in the
                2026-07-19 sweep (n=55, D30 from listing open): 30+ anchors AND
                >=Rs.200cr AND OFS<30% -> 72.7% win vs 62.2%, +17.2% median vs
                +12.7%, drawdown risk 23.6% vs 32.4%. RHP flags, early volume,
                retail price-bids and MF share all failed to beat it. */}
            {c.house_stack === true ? (
              <span title={String(c.house_stack_stat ?? "")} style={{
                marginLeft: 8, color: C.green, background: C.greenBg,
                border: `1px solid ${C.greenBd}`, borderRadius: 999,
                padding: "1px 8px", fontSize: 10, fontWeight: 800 }}>
                ◆ HOUSE STACK · 72.7%
              </span>
            ) : null}
          </div>
          {onLive && (
            <span onClick={onLive} style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: 10.5, fontWeight: 700, color: C.green, background: C.greenBg,
              border: `1px solid ${C.greenBd}`, borderRadius: 999, padding: "2px 9px", marginTop: 6 }}>
              <span className="livedot" style={{ width: 5, height: 5 }} />LIVE — trade it →</span>
          )}
          <div style={{ marginTop: 12 }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 7, background: vs.bg, color: vs.col,
              border: `1px solid ${vs.bd}`, fontSize: 15, fontWeight: 800, padding: "6px 15px",
              borderRadius: 10, letterSpacing: 0.3, transition: "background .25s var(--ease), color .25s var(--ease)",
            }}>
              {verdict === "TRADE" ? "✓" : verdict === "AVOID" ? "✕" : "◆"} {vs.label}
            </span>
            {verdict === "WATCH" && <span style={{ fontSize: 12, color: C.meta, marginLeft: 10 }}>gap at open decides</span>}
            {isTrade && <span style={{ fontSize: 12, color: C.meta, marginLeft: 10 }}>buy at open · trail −5%</span>}
          </div>
        </div>
        <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <ScoreDial score={score} conf={isQuality ? (c.quality_conf as number | null) : conf} sub={isQuality ? "quality · pre-list" : "trade tally"} tally={!isQuality} band={isQuality ? null : (c.score_band as string | null)} win={isQuality ? null : (c.score_expected_win as number | null)} />
          {(() => {
            const r = c.sbi_rating ? String(c.sbi_rating) : null;
            if (!r) return null;
            const neg = /avoid|not\s*subscribe/i.test(r), pos = !neg && /subscribe/i.test(r);
            const [fg, bg, bd] = pos ? [C.green, C.greenBg, C.greenBd] : neg ? [C.red, C.redBg, C.redBd] : [C.amber, C.amberBg, C.amberBd];
            return <span title="SBI Securities' own call — independent lens, never blended into our score"
              style={{ fontSize: 9, fontWeight: 800, color: fg, background: bg, border: `1px solid ${bd}`,
                borderRadius: 999, padding: "2px 8px", letterSpacing: .3, whiteSpace: "nowrap" }}>
              SBI · {r.length > 14 ? (pos ? "Subscribe" : neg ? "Avoid" : r.slice(0, 12)) : r}</span>;
          })()}
        </span>
      </div>

      {/* ROW 2: SETUP — the playbook engine's call */}
      {setupLine && (
        <div style={{
          display: "flex", alignItems: "flex-start", gap: 9, marginTop: 14,
          background: ss.bg, border: `1px solid ${C.line}`, borderRadius: 11, padding: "10px 13px",
        }}>
          <span style={{ color: ss.col, fontWeight: 800, fontSize: 13, flexShrink: 0 }}>{ss.mark} {ss.name}</span>
          <span style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.45 }}>{setupLine}</span>
        </div>
      )}

      {/* ROW 3: metrics — FV never fakes a number */}
      <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
        {fv != null
          ? <Metric label="Fair Value" value={`₹${fv}`} sub={mos != null ? `${mos > 0 ? "+" : ""}${mos}% MoS` : undefined} color={fvColor} emphasis />
          : <div style={{ flex: "1 1 96px", minWidth: 0, border: `1px dashed ${C.border}`, borderRadius: 11, padding: "10px 13px" }}>
              <div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.5, textTransform: "uppercase", fontWeight: 600 }}>Fair Value</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.dim, marginTop: 5 }}>awaiting</div>
              <div style={{ fontSize: 10.5, color: C.dim, marginTop: 1, lineHeight: 1.35 }}>{fvNote || "fills at listing"}</div>
            </div>}
        <Metric label="IPO Price" value={c.issue_price != null ? `₹${c.issue_price}` : "—"} />
        <Metric label="Size" value={c.issue_size_cr != null ? `₹${Number(c.issue_size_cr).toLocaleString()}cr` : "—"} />
      </div>

      {/* ROW 4: GMP predictor strip */}
      <GmpStrip db={gmpDb} hi={gmpHi} lo={gmpLo} band={gmpBand} hint={gmpHint} />

      {/* ROW 5: edge grid — the locked factors */}
      <EdgeGrid edges={edges} />

      {/* ROW 6: House Rules */}
      {allPills.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: C.meta, letterSpacing: 0.6, textTransform: "uppercase", marginBottom: 9 }}>
            AACapital House Rules
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
            {shown.map((p, i) => <Pill key={i} kind={p.kind} text={p.text} />)}
            {!showRules && moreCount > 0 && (
              <button onClick={() => setShowRules(true)} style={{
                background: "transparent", border: `1px dashed ${C.border}`, color: C.meta,
                fontSize: 12, fontWeight: 600, padding: "5px 11px", borderRadius: 999, cursor: "pointer",
              }}>+{moreCount} more</button>
            )}
          </div>
        </div>
      )}

      {/* ROW 7: footer — Street vs AACapital vs RHP */}
      {(street || verdict || rhpGate) && (
        <div style={{ display: "flex", gap: 22, padding: "13px 0 3px", marginTop: 16, borderTop: `1px solid ${C.line}`, flexWrap: "wrap" }}>
          {street && <div><div style={{ fontSize: 9.5, color: C.meta, letterSpacing: 0.4, textTransform: "uppercase" }}>Street</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginTop: 2 }}>{street}{brokers != null ? ` · ${brokers}` : ""}</div></div>}
          {verdict && <div><div style={{ fontSize: 9.5, color: C.meta, letterSpacing: 0.4, textTransform: "uppercase" }}>AACapital</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: vs.col, marginTop: 2 }}>{vs.label}</div></div>}
          {rhpGate && <div><div style={{ fontSize: 9.5, color: C.meta, letterSpacing: 0.4, textTransform: "uppercase" }}>RHP Trust</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginTop: 2 }}>{rhpGate}</div></div>}
        </div>
      )}

      {/* ROW 8: journey CTA — the live exit engine */}
      {listed && sym && (
        <>
          {/* Journey: the stack is WHY you can sit through a dip — that cohort's
              -20% drawdown risk is 23.6% vs 32.4% baseline. */}
          {c.house_stack === true ? (
            <div style={{ fontSize: 10.5, color: C.green, fontWeight: 700, marginBottom: 6 }}>
              ◆ House Stack — historically {String(c.house_stack_stat ?? "")}; drawdown risk 23.6% vs 32.4% baseline
            </div>
          ) : null}
          <button onClick={() => onJourney?.(sym)} style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8, width: "100%",
            background: C.gold, color: C.bg, fontFamily: DISPLAY, fontSize: 14, fontWeight: 700, padding: "13px 16px",
            borderRadius: 11, border: "none", cursor: "pointer", marginTop: 16, letterSpacing: 0.2,
          }}>
            Track the hold — live exit engine →
          </button>
          <div style={{ ...num, fontSize: 10.5, color: C.dim, textAlign: "center", marginTop: 6 }}>
            lock8/trail12 · arm +8% · floor +3% · trail −12%
          </div>
        </>
      )}

      {/* RHP toggle */}
      {(() => {
        const fj0 = typeof c.rhp_full === "string"
          ? (() => { try { return JSON.parse(String(c.rhp_full)); } catch { return null; } })()
          : (c.rhp_full as Record<string, unknown> | null);
        const N = (x: unknown) => { const v = Number(x); return Number.isFinite(v) ? v : null; };
        // ── PR-B (Phase 6): evidence rows from ipo_insights ────────────────
        // Each row exists only WITH the source's quoted words (fan-out rule).
        // Reasons carry provenance; RHP-backed items render a "RHP · quoted"
        // badge with the excerpt on hover. insights==null (no fan-out yet)
        // -> full legacy fallback below, unchanged behavior.
        type Insight = { category?: string; direction?: string; statement?: string;
                         excerpt?: string | null; source?: string; locator?: string | null };
        const insights: Insight[] = (() => {
          const raw = (c as Record<string, unknown>).insights;
          if (Array.isArray(raw)) return raw as Insight[];
          if (typeof raw === "string") { try { const p = JSON.parse(raw); return Array.isArray(p) ? p : []; } catch { return []; } }
          return [];
        })();
        type Reason = { text: string; quote?: string | null; loc?: string | null };
        const bad: Reason[] = [];
        const good: Reason[] = [];
        const gate = String(c.rhp_gate ?? "").toLowerCase();
        if (gate === "reject") bad.push({ text: "RHP forensics: REJECT — the document itself argues against this issue" });
        const { raised, clear } = rhpFlagChips(fj0);
        for (const r of raised) bad.push({ text: r });
        const insRisks = insights.filter((i) => i.category === "risk" && i.direction === "negative" && i.statement);
        if (insRisks.length) {
          for (const r of insRisks) bad.push({ text: String(r.statement), quote: r.excerpt, loc: r.locator });
        } else {
          const risks = fj0 && Array.isArray((fj0 as Record<string, unknown>).top_3_material_risks)
            ? ((fj0 as Record<string, unknown>).top_3_material_risks as string[]) : [];
          for (const r of risks) bad.push({ text: r });
        }
        const ofsC = N(c.ofs_cr), freshC = N(c.fresh_issue_cr);
        const tot = (ofsC ?? 0) + (freshC ?? 0);
        const ofsPct = tot > 0 ? Math.round((ofsC ?? 0) / tot * 100) : null;
        // ── Phase-7 OFS repair (2026-07-20) ────────────────────────────────
        // ofs_pct is a STRUCTURED FACT: it proves the issue is an offer for
        // sale — nothing about seller identity or motive. "Promoter cash-out"
        // is an INTERPRETATION and requires document evidence. Sonnet already
        // extracts it (structure.ofs_heavy + quoted detail, rhp_sonnet.py):
        //   evidence present  -> confirmed negative WITH the RHP's own words
        //   evidence absent   -> neutral fact + explicit pending state
        // Quantitative OFS weighting (fair-value, backtest factors) unchanged.
        const pend: string[] = [];
        if (ofsPct != null && ofsPct >= 60) {
          const stIns = insights.find((i) => i.category === "structure" && i.statement);
          const st = fj0 && typeof fj0 === "object" ? (fj0 as Record<string, unknown>).structure as Record<string, unknown> | undefined : undefined;
          const stDetail = st && typeof st.detail === "string" ? (st.detail as string).trim() : "";
          if (stIns && stIns.direction === "negative") {
            bad.push({ text: `${ofsPct}% OFS — RHP: ${String(stIns.statement).slice(0, 160)}`, quote: stIns.excerpt, loc: stIns.locator });
          } else if (stIns) {
            // evidence WAS read and is not a confirmed negative (e.g. an
            // institutional seller) — no pending line, no manufactured claim
          } else if (st?.ofs_heavy === true && stDetail) {
            bad.push({ text: `${ofsPct}% OFS — RHP: ${stDetail.slice(0, 160)}` });
          } else {
            pend.push(`${ofsPct}% offer for sale confirmed. Seller rationale and use-of-proceeds assessment pending RHP analysis.`);
          }
        }
        const pe = N(c.ipo_pe), ppe = N(c.peer_median_pe);
        if (pe != null && ppe != null && ppe > 0 && pe / ppe >= 1.5) bad.push({ text: `Priced ${(pe / ppe).toFixed(1)}× the sector median P/E (${pe.toFixed(0)} vs ${ppe.toFixed(0)})` });
        const roe = N(c.roe), de = N(c.debt_equity), cagr = N(c.revenue_cagr_3y), pat = N(c.pat_cr);
        if (pat != null && pat < 0) bad.push({ text: "Loss-making — negative PAT" });
        // exact 0 for ROE/CAGR is almost always null-coded missing data, not a
        // real reading (Caliber showed "ROE 0.0%" — Rakesh's screenshot) — a
        // missing number must never manufacture a negative.
        if (roe != null && roe !== 0 && roe < 10) bad.push({ text: `Weak ROE ${roe.toFixed(1)}%` });
        if (de != null && de > 1.5) bad.push({ text: `Heavy leverage — D/E ${de.toFixed(1)}` });
        if (cagr != null && cagr !== 0 && cagr < 8) bad.push({ text: `Sluggish revenue growth ${cagr.toFixed(0)}%/yr` });
        // strengths (fill only when the negative case is thin AND gate isn't reject)
        if (bad.length < 5 && gate !== "reject") {
          if (ofsPct != null && ofsPct <= 20) good.push({ text: `${100 - (ofsPct ?? 0)}% fresh issue — capital goes INTO the business` });
          if (roe != null && roe >= 18) good.push({ text: `Strong ROE ${roe.toFixed(1)}%` });
          if (cagr != null && cagr >= 20) good.push({ text: `Revenue compounding ${cagr.toFixed(0)}%/yr` });
          if (pe != null && ppe != null && ppe > 0 && pe / ppe <= 0.8) good.push({ text: `Priced BELOW sector median (${(pe / ppe).toFixed(1)}×)` });
          if (c.quality_promoter === true) good.push({ text: "Quality promoter track record" });
          if (c.house_stack === true)
            good.push({ text: "HOUSE STACK: 30+ anchors + ≥₹200cr + fresh-issue — 72.7% win, +17.2% median (D30, n=55)" });
          if (clear > 0 && raised.length === 0) good.push({ text: `${clear} governance checks clear — no auditor/SEBI/pledge flags` });
        }
        const items = [...bad.slice(0, 5), ...good.slice(0, Math.max(0, 5 - Math.min(bad.length, 5)))];
        if (!items.length && !pend.length) return null;
        const clean = bad.length === 0;
        const nBad = Math.min(bad.length, 5);
        return (
          <div style={{ marginTop: 12, padding: "13px 15px", borderRadius: 11,
            background: clean ? C.greenBg : C.redBg, border: `1px solid ${clean ? C.greenBd : C.redBd}` }}>
            <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: .4, textTransform: "uppercase",
              color: clean ? C.green : C.red, marginBottom: 7 }}>Why should I NOT buy this IPO?</div>
            {items.map((r, i) => {
              const isBad = i < nBad;
              return <div key={i}>
                {/* Phase-7: strengths were rendered flush under the "NOT buy"
                    question ("Strong ROE" read as a not-buy reason — owner
                    screenshot). Divide the lanes explicitly. */}
                {i === nBad && <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: .4, textTransform: "uppercase",
                  color: C.green, margin: "7px 0 4px" }}>{nBad ? "…and in its favour" : "No confirmed negatives — in its favour"}</div>}
                <div style={{ display: "flex", gap: 8, marginBottom: 5, fontSize: 12.5, lineHeight: 1.5, color: C.sub }}>
                  <span style={{ fontWeight: 800, flexShrink: 0, color: isBad ? C.red : C.green }}>{isBad ? "✕" : "✓"}</span>
                  <span>{r.text}
                    {r.quote ? <span title={`RHP${r.loc ? ` · ${r.loc}` : ""}: “${String(r.quote).slice(0, 220)}”`}
                      style={{ marginLeft: 6, fontSize: 9, fontWeight: 800, letterSpacing: .3, padding: "1px 5px",
                               borderRadius: 4, background: "rgba(120,120,140,.15)", color: C.meta,
                               cursor: "help", whiteSpace: "nowrap" }}>RHP · quoted</span> : null}
                  </span></div>
              </div>;
            })}
            {pend.map((r, i) => (
              <div key={`p${i}`} style={{ display: "flex", gap: 8, marginBottom: 5, fontSize: 12.5, lineHeight: 1.5, color: C.meta }}>
                <span style={{ fontWeight: 800, flexShrink: 0, color: C.meta }}>◌</span>
                <span>{r}</span></div>
            ))}
            {clean && !pend.length && <div style={{ fontSize: 10.5, color: C.meta, marginTop: 4 }}>Honest answer: we couldn't find a strong reason not to. That itself is the finding.</div>}
            {/* PROVENANCE (fixed 2026-07-20). This said "From the RHP + filings"
                unconditionally. But these reasons are computed from STRUCTURED
                fields — ofs_pct, roe, issue size — sourced from Chittorgarh /
                IPOMatrix. On an IPO with no RHP extraction (Lohia, Indo-MIM) the
                footer claimed a source that had never been read. Say what was
                actually used. */}
            <div style={{ fontSize: 10, color: C.dim, marginTop: 6 }}>
              {c.rhp_verdict ? "From the RHP + filings" : "From filings & issue data — RHP not yet read"}
              {" · research signal, not a buy call"}
            </div>
          </div>
        );
      })()}
      {Boolean(c.rhp_one_line || c.rhp_full || c.ai_summary || c.sbi_full || c.sbi_one_line || c.sbi_rating) && (
        <button onClick={() => setShowRhp((v) => !v)} style={{
          background: "transparent", border: "none", color: C.meta,
          fontSize: 12, fontWeight: 600, padding: "10px 0 0", cursor: "pointer", display: "block",
        }}>
          {showRhp ? "▲ Hide details" : "▼ RHP + SBI research · risks · flags · AI read"}
        </button>
      )}
      {c.chittorgarh_slug ? (
        <a href={`https://www.chittorgarh.com/ipo/${String(c.chittorgarh_slug)}/`}
          target="_blank" rel="noopener noreferrer"
          style={{ display: "inline-block", marginTop: 8, fontSize: 11, fontWeight: 700,
            color: C.gold, textDecoration: "none" }}>
          IPO docs & RHP ⎘</a>
      ) : null}

      {showRhp && (() => {
        const fj = typeof c.rhp_full === "string"
          ? (() => { try { return JSON.parse(String(c.rhp_full)); } catch { return null; } })()
          : (c.rhp_full as Record<string, unknown> | null);
        const risks = fj && Array.isArray((fj as Record<string, unknown>).top_3_material_risks)
          ? ((fj as Record<string, unknown>).top_3_material_risks as string[]) : [];
        const ddNote = fj && (fj as Record<string, unknown>).aacapital_decision
          ? ((fj as Record<string, Record<string, unknown>>).aacapital_decision?.dd_note as string) : null;
        const trustSummary = fj ? ((fj as Record<string, unknown>).trust_summary as string) : null;
        const { raised, clear } = rhpFlagChips(fj);
        const sj = typeof c.sbi_full === "string"
          ? (() => { try { return JSON.parse(String(c.sbi_full)); } catch { return null; } })()
          : (c.sbi_full as Record<string, unknown> | null);
        return (<>
          <div style={{ marginTop: 10, padding: "14px 16px", background: C.bg, border: `1px solid ${C.border}`, borderRadius: 11 }}>
            {c.rhp_gate ? <div style={{ fontSize: 11, fontWeight: 700, color: C.meta, letterSpacing: 0.4, marginBottom: 8 }}>
              RHP TRUST · {String(c.rhp_gate).toUpperCase()}{c.rhp_mos ? ` · margin of safety: ${String(c.rhp_mos)}` : ""}{c.rhp_confidence ? ` · confidence ${String(c.rhp_confidence)}` : ""}{c.rhp_url ? <a href={String(c.rhp_url)} target="_blank" rel="noreferrer" style={{ marginLeft: 8, fontSize: 10.5, color: C.gold, fontWeight: 700, textDecoration: "none" }}>RHP ↗</a> : null}</div> : null}
            {c.rhp_one_line ? <div style={{ fontSize: 13, color: C.sub, lineHeight: 1.55, marginBottom: trustSummary || risks.length ? 10 : 0 }}>{String(c.rhp_one_line)}</div> : null}
            {trustSummary && <p style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.6, marginBottom: 10 }}>{trustSummary}</p>}
            {(raised.length > 0 || clear > 0) && <>
              <div style={{ fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: C.meta, margin: "10px 0 6px" }}>Governance flags</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 4 }}>
                {raised.map((r, i) => <span key={i} style={{ background: C.redBg, color: C.red, border: `1px solid ${C.redBd}`, fontSize: 11, fontWeight: 600, padding: "4px 9px", borderRadius: 999 }}>⚑ {r}</span>)}
                {clear > 0 && <span style={{ background: C.greenBg, color: C.green, border: `1px solid ${C.greenBd}`, fontSize: 11, fontWeight: 600, padding: "4px 9px", borderRadius: 999 }}>✓ {clear} checks clear</span>}
              </div>
            </>}
            {risks.length > 0 && <>
              <div style={{ fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: C.meta, margin: "10px 0 6px" }}>Top material risks</div>
              {risks.map((r, i) => <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5, fontSize: 12.5, color: C.sub, lineHeight: 1.5 }}>
                <span style={{ color: C.amber, fontWeight: 700 }}>{i + 1}.</span><span>{r}</span></div>)}
            </>}
            {ddNote && <>
              <div style={{ fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: C.meta, margin: "11px 0 5px" }}>Due-diligence to verify</div>
              <div style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.5 }}>{ddNote}</div></>}
            {c.ai_summary ? <div style={{ fontSize: 12.5, color: C.meta, lineHeight: 1.5, marginTop: 11, display: "flex", gap: 7 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: C.meta, letterSpacing: 0.4, flexShrink: 0, marginTop: 1 }}>AI</span><span>{String(c.ai_summary)}</span></div> : null}
            {(() => {
              // ── PR-B/PR-D: the fan-out's quoted evidence, rendered raw ──
              const raw = (c as Record<string, unknown>).insights;
              const ins: Array<Record<string, unknown>> = Array.isArray(raw) ? raw as Array<Record<string, unknown>>
                : typeof raw === "string" ? (() => { try { const p2 = JSON.parse(raw); return Array.isArray(p2) ? p2 : []; } catch { return []; } })() : [];
              if (!ins.length) return null;
              return <>
                <div style={{ fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: C.meta, margin: "11px 0 6px" }}>RHP evidence · the document's own words</div>
                {ins.map((r, i) => {
                  const dir = String(r.direction ?? "");
                  const mark = dir === "negative" ? "−" : dir === "positive" ? "+" : "·";
                  const mc = dir === "negative" ? C.red : dir === "positive" ? C.green : C.meta;
                  return <div key={i} style={{ marginBottom: 6, fontSize: 12, color: C.sub, lineHeight: 1.5 }}>
                    <span style={{ color: mc, fontWeight: 800, marginRight: 7 }}>{mark}</span>
                    {String(r.statement ?? "")}
                    {r.excerpt ? <div style={{ marginTop: 2, marginLeft: 15, fontSize: 11, color: C.meta, fontStyle: "italic" }}>
                      “{String(r.excerpt).slice(0, 260)}”{r.locator ? <span style={{ fontStyle: "normal" }}> — {String(r.locator)}</span> : null}</div> : null}
                  </div>;
                })}
              </>;
            })()}
            <div style={{ marginTop: 11, fontSize: 10, color: C.dim }}>Source: Red Herring Prospectus · extracted by Claude · research signal, not a buy call</div>
          </div>
          {/* ── SBI Securities research (Haiku-parsed) — independent lens, never
                blended into our score. Missing note -> the directive's exact
                pending language, never an invented recommendation. ── */}
          <div style={{ marginTop: 8, padding: "13px 16px", background: C.bg, border: `1px solid ${C.border}`, borderRadius: 11 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.meta, letterSpacing: 0.4, marginBottom: 6 }}>
              SBI SECURITIES RESEARCH{c.sbi_rating ? ` · ${String(c.sbi_rating)}` : ""}</div>
            {sj ? <>
              {(sj.one_line || c.sbi_one_line) ? <div style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.55, marginBottom: 8 }}>{String(sj.one_line ?? c.sbi_one_line)}</div> : null}
              {Array.isArray(sj.strengths) && sj.strengths.length ? <div style={{ marginBottom: 6 }}>
                {(sj.strengths as string[]).slice(0, 4).map((t, i) => <div key={i} style={{ display: "flex", gap: 7, fontSize: 12, color: C.sub, lineHeight: 1.5, marginBottom: 3 }}><span style={{ color: C.green, fontWeight: 800 }}>+</span><span>{t}</span></div>)}
              </div> : null}
              {Array.isArray(sj.risks) && sj.risks.length ? <div style={{ marginBottom: 6 }}>
                {(sj.risks as string[]).slice(0, 4).map((t, i) => <div key={i} style={{ display: "flex", gap: 7, fontSize: 12, color: C.sub, lineHeight: 1.5, marginBottom: 3 }}><span style={{ color: C.red, fontWeight: 800 }}>−</span><span>{t}</span></div>)}
              </div> : null}
              {sj.valuation_comment ? <div style={{ fontSize: 11.5, color: C.meta, lineHeight: 1.5, marginBottom: 4 }}>Valuation: {String(sj.valuation_comment)}</div> : null}
              {Array.isArray(sj.peer_comparison) && (sj.peer_comparison as unknown[]).length ? <div style={{ fontSize: 11, color: C.meta }}>Peer table: {(sj.peer_comparison as unknown[]).length} peers captured{sj.clean_or_flagged ? ` · note self-reports ${String(sj.clean_or_flagged)}` : ""}</div> : null}
              <div style={{ marginTop: 9, fontSize: 10, color: C.dim }}>Source: SBI Securities IPO note · parsed by Claude Haiku · their call, not ours</div>
            </> : <div style={{ fontSize: 12, color: C.meta }}>SBI research note not available or not yet parsed.</div>}
          </div>
        </>
        );
      })()}
    </div>
  );
}
