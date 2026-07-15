"use client";
import React, { useState } from "react";

/* ────────────────────────────────────────────────────────────────────────
   IpoCard — premium institutional IPO card. Built to *exceed*:
   • Score 40px with a conviction ring · Decision as a bold color pill
   • Emphasized metric row (Fair Value colored, MoS prominent)
   • "AACapital House Rules" pills (ticks, max 3 + "+N more")
   • Compact 3-verdict footer · unmissable gold journey CTA (the unburied gold)
   • RHP + AI collapsed behind a tap
   Same --t-* theme vars → light + dark both crisp. Bindings preserved 1:1.
   ──────────────────────────────────────────────────────────────────────── */

const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";
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
  return String(s).split(/[|;]|(?:^|\n)\s*[•✓✕⚠●]\s*/).map((x) => x.trim().replace(/^[•✓✕⚠●]\s*/, "")).filter(Boolean);
}

function scoreColor(score: number | null): string {
  if (score == null) return C.dim;
  if (score >= 65) return C.green;
  if (score >= 40) return C.amber;
  return C.red;
}

function ScoreDial({ score, conf }: { score: number | null; conf: number | null }) {
  const col = scoreColor(score);
  const pct = score != null ? Math.max(0, Math.min(100, score)) : 0;
  const r = 30, circ = 2 * Math.PI * r, off = circ * (1 - pct / 100);
  return (
    <div style={{ position: "relative", width: 72, height: 72, flexShrink: 0 }}>
      <svg width="72" height="72" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="36" cy="36" r={r} fill="none" stroke={C.grayBg} strokeWidth="5" />
        {score != null && (
          <circle cx="36" cy="36" r={r} fill="none" stroke={col} strokeWidth="5"
            strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off} />
        )}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ ...num, fontSize: 26, fontWeight: 800, color: col, lineHeight: 1 }}>
          {score != null ? score : "—"}
        </span>
        {conf != null && <span style={{ fontSize: 8.5, color: C.meta, marginTop: 1 }}>{conf}%</span>}
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
      flex: 1, minWidth: 0, background: C.bg,
      border: `1px solid ${emphasis ? C.gold : C.border}`,
      borderRadius: 11, padding: "10px 13px",
    }}>
      <div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.5, textTransform: "uppercase", fontWeight: 600 }}>{label}</div>
      <div style={{ ...num, fontSize: 20, fontWeight: 800, color: color || C.text, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", lineHeight: 1.1 }}>
        {value}
      </div>
      {sub && <div style={{ ...num, fontSize: 12, fontWeight: 600, color: color || C.meta, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export default function IpoCard({ c, onJourney }: { c: Row; onJourney?: (sym: string) => void }) {
  const [showRules, setShowRules] = useState(false);
  const [showRhp, setShowRhp] = useState(false);

  const score = (c.vscore ?? c.ipo_score) as number | null;
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
  // dedupe near-identical signals (e.g. size warning appearing in both why_avoid + red_flags)
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

  const street = c.street_consensus ? String(c.street_consensus) : null;
  const brokers = N(c.street_brokers);
  const rhpGate = c.rhp_gate ? String(c.rhp_gate) : null;

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${isTrade ? C.greenBd : C.border}`,
      borderLeft: `4px solid ${vs.col}`,
      borderRadius: 16, padding: "20px 22px", marginBottom: 14,
      boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
    }}>
      {/* ROW 1: hero */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 23, fontWeight: 800, color: C.text, lineHeight: 1.12, letterSpacing: -0.4 }}>
            {String(c.company_name || "")}
          </div>
          <div style={{ fontSize: 12, color: C.meta, marginTop: 5 }}>
            {c.state ? String(c.state) : ""}{c.listing_date ? ` · lists ${D(c.listing_date)}` : ""}
            {c.quality_promoter === true && <span style={{ color: C.gold, fontWeight: 600 }}> · ★ Quality promoter</span>}
          </div>
          <div style={{ marginTop: 12 }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 7, background: vs.bg, color: vs.col,
              border: `1px solid ${vs.bd}`, fontSize: 15, fontWeight: 800, padding: "6px 15px",
              borderRadius: 10, letterSpacing: 0.3,
            }}>
              {verdict === "TRADE" ? "✓" : verdict === "AVOID" ? "✕" : "◆"} {vs.label}
            </span>
            {verdict === "WATCH" && <span style={{ fontSize: 12, color: C.meta, marginLeft: 10 }}>gap at open decides</span>}
            {isTrade && <span style={{ fontSize: 12, color: C.meta, marginLeft: 10 }}>buy at open · trail −5%</span>}
          </div>
        </div>
        <ScoreDial score={score} conf={conf} />
      </div>

      {/* ROW 2: metrics */}
      <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
        {fv != null
          ? <Metric label="Fair Value" value={`₹${fv}`} sub={mos != null ? `${mos > 0 ? "+" : ""}${mos}% MoS` : undefined} color={fvColor} emphasis />
          : <Metric label="Fair Value" value="—" color={C.dim} />}
        <Metric label="IPO Price" value={c.issue_price != null ? `₹${c.issue_price}` : "—"} />
        <Metric label="Size" value={c.issue_size_cr != null ? `₹${Number(c.issue_size_cr).toLocaleString()}cr` : "—"} />
      </div>

      {/* ROW 3: House Rules */}
      {allPills.length > 0 && (
        <div style={{ marginTop: 18 }}>
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

      {/* ROW 4: footer */}
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

      {/* ROW 5: journey CTA */}
      {listed && sym && (
        <button onClick={() => onJourney?.(sym)} style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8, width: "100%",
          background: C.gold, color: C.bg, fontSize: 14, fontWeight: 800, padding: "12px 16px",
          borderRadius: 11, border: "none", cursor: "pointer", marginTop: 16, letterSpacing: 0.2,
        }}>
          ⟶ Track the hold — live exit engine
        </button>
      )}

      {/* RHP toggle */}
      {(c.rhp_one_line || c.rhp_full || c.ai_summary) && (
        <button onClick={() => setShowRhp((v) => !v)} style={{
          background: "transparent", border: "none", color: C.meta,
          fontSize: 12, fontWeight: 600, padding: "10px 0 0", cursor: "pointer", display: "block",
        }}>
          {showRhp ? "▲ Hide details" : "▼ RHP details · risks · AI read"}
        </button>
      )}

      {showRhp && (() => {
        // full_json (rhp_full) carries the complete RHP intel — parse + render it all,
        // so the full text is available on-app without any DB query.
        const fj = typeof c.rhp_full === "string"
          ? (() => { try { return JSON.parse(String(c.rhp_full)); } catch { return null; } })()
          : (c.rhp_full as Record<string, unknown> | null);
        const risks = fj && Array.isArray((fj as Record<string, unknown>).top_3_material_risks)
          ? ((fj as Record<string, unknown>).top_3_material_risks as string[]) : [];
        const ddNote = fj && (fj as Record<string, unknown>).aacapital_decision
          ? ((fj as Record<string, Record<string, unknown>>).aacapital_decision?.dd_note as string) : null;
        const trustSummary = fj ? ((fj as Record<string, unknown>).trust_summary as string) : null;
        return (
          <div style={{ marginTop: 10, padding: "14px 16px", background: C.bg, border: `1px solid ${C.border}`, borderRadius: 11 }}>
            {c.rhp_gate && <div style={{ fontSize: 11, fontWeight: 700, color: C.meta, letterSpacing: 0.4, marginBottom: 8 }}>
              🔍 RHP TRUST · {String(c.rhp_gate).toUpperCase()}{c.rhp_mos ? ` · margin of safety: ${String(c.rhp_mos)}` : ""}{c.rhp_confidence ? ` · confidence ${String(c.rhp_confidence)}` : ""}</div>}
            {c.rhp_one_line && <div style={{ fontSize: 13, color: C.sub, lineHeight: 1.55, marginBottom: trustSummary || risks.length ? 10 : 0 }}>{String(c.rhp_one_line)}</div>}
            {trustSummary && <p style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.6, marginBottom: 10 }}>{trustSummary}</p>}
            {risks.length > 0 && <>
              <div style={{ fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: C.meta, margin: "10px 0 6px" }}>Top material risks</div>
              {risks.map((r, i) => <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5, fontSize: 12.5, color: C.sub, lineHeight: 1.5 }}>
                <span style={{ color: C.amber, fontWeight: 700 }}>{i + 1}.</span><span>{r}</span></div>)}
            </>}
            {ddNote && <>
              <div style={{ fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: C.meta, margin: "11px 0 5px" }}>Due-diligence to verify</div>
              <div style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.5 }}>{ddNote}</div></>}
            {c.ai_summary && <div style={{ fontSize: 12.5, color: C.meta, lineHeight: 1.5, marginTop: 11, display: "flex", gap: 7 }}>
              <span>🤖</span><span>{String(c.ai_summary)}</span></div>}
            <div style={{ marginTop: 11, fontSize: 10, color: C.dim }}>Source: Red Herring Prospectus · extracted by Claude · research signal, not a buy call</div>
          </div>
        );
      })()}
    </div>
  );
}
