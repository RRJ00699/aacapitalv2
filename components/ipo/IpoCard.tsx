"use client";
import React, { useState } from "react";

/* ────────────────────────────────────────────────────────────────────────
   IpoCard — redesigned IPO card (premium institutional, "under 3 seconds")
   Spec: score+decision co-dominant hero · 3-metric row · AACapital House Rules
   pills (with ticks, max 3 + "+N more") · compact 3-verdict footer · prominent
   journey CTA (unbury the gold) · RHP/flags collapsed behind a tap.
   Reuses the same --t-* theme vars as ipo2, so light+dark both work.
   Data bindings preserved 1:1 from the old card block.
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

// verdict → color + label
function verdictStyle(v: string | null) {
  switch (v) {
    case "TRADE": return { col: C.green, label: "TRADE" };
    case "AVOID": return { col: C.red, label: "AVOID" };
    case "CAUTION": return { col: C.amber, label: "CAUTION" };
    case "WATCH": default: return { col: C.gold, label: v || "WATCH" };
  }
}

// split a comma/pipe string into trimmed items
function items(s: unknown): string[] {
  if (!s) return [];
  return String(s).split(/[|]/).map((x) => x.trim()).filter(Boolean);
}

// a single House-Rule pill
function Pill({ kind, text }: { kind: "pass" | "warn" | "neutral"; text: string }) {
  const map = {
    pass: { bg: C.greenBg, fg: C.green, mark: "✓" },
    warn: { bg: C.redBg, fg: C.red, mark: "✕" },
    neutral: { bg: C.grayBg, fg: C.sub, mark: "•" },
  }[kind];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, background: map.bg, color: map.fg,
      fontSize: 12, fontWeight: 500, padding: "5px 11px", borderRadius: 999, lineHeight: 1.3,
    }}>
      <span style={{ fontWeight: 700 }}>{map.mark}</span>{text}
    </span>
  );
}

// one metric box in the 3-col row
function Metric({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ flex: 1, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 10, padding: "9px 12px", minWidth: 0 }}>
      <div style={{ fontSize: 10.5, color: C.meta, letterSpacing: 0.4, textTransform: "uppercase", fontWeight: 600 }}>{label}</div>
      <div style={{ ...num, fontSize: 16, fontWeight: 700, color: color || C.text, marginTop: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {value}{sub && <span style={{ fontSize: 11.5, fontWeight: 500, color: C.meta }}> {sub}</span>}
      </div>
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

  // House Rules: build pills from the why_* signals + flags
  const passes = [...items(c.why_trade), ...items(c.why_passes)].map((t) => ({ kind: "pass" as const, text: t }));
  const warns = [...items(c.why_avoid), ...items(c.red_flags)].map((t) => ({ kind: "warn" as const, text: t }));
  const neutrals = items(c.why_caution).map((t) => ({ kind: "neutral" as const, text: t }));
  const allPills: { kind: "pass" | "warn" | "neutral"; text: string }[] = [...passes, ...warns, ...neutrals];
  const shown = showRules ? allPills : allPills.slice(0, 3);
  const moreCount = allPills.length - 3;

  // Fair value (already computed server-side)
  const fv = N(c.fair_value);
  const mos = N(c.fair_mos);
  const fvVerdict = c.fair_verdict as string | null;
  const fvColor = fvVerdict === "undervalued" ? C.green : fvVerdict === "rich" ? C.red : C.text;

  // Street + RHP for footer
  const street = c.street_consensus ? String(c.street_consensus) : null;
  const brokers = N(c.street_brokers);
  const rhpGate = c.rhp_gate ? String(c.rhp_gate) : null;

  return (
    <div style={{
      background: isTrade ? C.greenBg : C.surface,
      border: `1px solid ${isTrade ? C.greenBd : C.border}`,
      borderLeft: isTrade ? `4px solid ${C.green}` : `1px solid ${C.border}`,
      borderRadius: 14, padding: "16px 18px", marginBottom: 12,
    }}>
      {/* ── ROW 1: hero — company + score/decision ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.text, lineHeight: 1.15, letterSpacing: -0.3 }}>
            {String(c.company_name || "")}
          </div>
          <div style={{ fontSize: 12, color: C.meta, marginTop: 4 }}>
            {c.state ? String(c.state) : ""}{c.listing_date ? ` · lists ${D(c.listing_date)}` : ""}
            {c.quality_promoter === true && <span style={{ color: C.gold, fontWeight: 600 }}> · ★ Quality promoter</span>}
          </div>
        </div>
        <div style={{ textAlign: "center", flexShrink: 0, minWidth: 58 }}>
          <div style={{ ...num, fontSize: 34, fontWeight: 800, color: C.text, lineHeight: 1 }}>
            {score != null ? score : "—"}
          </div>
          <div style={{ fontSize: 9.5, color: C.meta, letterSpacing: 0.4 }}>
            SCORE{conf != null ? ` · ${conf}%` : ""}
          </div>
        </div>
      </div>

      {/* ── decision line ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 19, fontWeight: 700, color: vs.col }}>{vs.label}</span>
        {verdict === "WATCH" && <span style={{ fontSize: 12, color: C.meta }}>· gap at open decides the trade</span>}
        {isTrade && <span style={{ fontSize: 12, color: C.meta }}>· buy at open, trail −5%</span>}
      </div>

      {/* ── ROW 2: 3 metric boxes ── */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        {fv != null
          ? <Metric label="Fair Value" value={`₹${fv}`} sub={mos != null ? `${mos > 0 ? "+" : ""}${mos}%` : undefined} color={fvColor} />
          : <Metric label="Fair Value" value="—" color={C.dim} />}
        <Metric label="IPO Price" value={c.issue_price != null ? `₹${c.issue_price}` : "—"} />
        <Metric label="Size" value={c.issue_size_cr != null ? `₹${Number(c.issue_size_cr).toLocaleString()}cr` : "—"} />
      </div>

      {/* ── ROW 3: AACapital House Rules ── */}
      {allPills.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: C.meta, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 8 }}>
            AACapital House Rules
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {shown.map((p, i) => <Pill key={i} kind={p.kind} text={p.text} />)}
            {!showRules && moreCount > 0 && (
              <button onClick={() => setShowRules(true)} style={{
                background: "transparent", border: `1px dashed ${C.border}`, color: C.meta,
                fontSize: 12, fontWeight: 500, padding: "5px 11px", borderRadius: 999, cursor: "pointer",
              }}>+{moreCount} more</button>
            )}
          </div>
        </div>
      )}

      {/* ── ROW 4: compact 3-verdict footer ── */}
      <div style={{ display: "flex", gap: 18, padding: "11px 0", borderTop: `1px solid ${C.line}`, flexWrap: "wrap" }}>
        {street && <div><div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.3 }}>STREET</div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>{street}{brokers != null ? ` · ${brokers}` : ""}</div></div>}
        {verdict && <div><div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.3 }}>AACAPITAL</div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: vs.col }}>{vs.label}</div></div>}
        {rhpGate && <div><div style={{ fontSize: 10, color: C.meta, letterSpacing: 0.3 }}>RHP TRUST</div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>{rhpGate}</div></div>}
      </div>

      {/* ── ROW 5: journey CTA (the unburied gold) + RHP toggle ── */}
      <div style={{ display: "flex", gap: 10, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
        {listed && sym && (
          <button onClick={() => onJourney?.(sym)} style={{
            display: "inline-flex", alignItems: "center", gap: 7, background: C.gold, color: C.bg,
            fontSize: 13, fontWeight: 700, padding: "9px 16px", borderRadius: 10, border: "none", cursor: "pointer",
          }}>
            ⟶ Track the hold
          </button>
        )}
        {(c.rhp_one_line || c.rhp_full) && (
          <button onClick={() => setShowRhp((v) => !v)} style={{
            background: "transparent", border: `1px solid ${C.border}`, color: C.sub,
            fontSize: 12, fontWeight: 500, padding: "8px 14px", borderRadius: 8, cursor: "pointer",
          }}>
            {showRhp ? "Hide" : "RHP details · risks"}
          </button>
        )}
      </div>

      {/* ── collapsed: RHP one-liner + AI summary ── */}
      {showRhp && (
        <div style={{ marginTop: 12, padding: "12px 14px", background: C.bg, border: `1px solid ${C.border}`, borderRadius: 10 }}>
          {c.rhp_gate && <div style={{ fontSize: 11, fontWeight: 700, color: C.meta, letterSpacing: 0.4, marginBottom: 6 }}>
            🔍 RHP TRUST · {String(c.rhp_gate)}{c.rhp_mos ? ` · margin of safety: ${String(c.rhp_mos)}` : ""}</div>}
          {c.rhp_one_line && <div style={{ fontSize: 13, color: C.sub, lineHeight: 1.55 }}>{String(c.rhp_one_line)}</div>}
          {c.ai_summary && <div style={{ fontSize: 12.5, color: C.meta, lineHeight: 1.5, marginTop: 9, display: "flex", gap: 7 }}>
            <span>🤖</span><span>{String(c.ai_summary)}</span></div>}
        </div>
      )}
    </div>
  );
}
