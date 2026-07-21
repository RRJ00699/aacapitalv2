"use client";
// components/ui/primitives.tsx — the shared building blocks (feat/ux-premium).
// Every badge, card, stat tile, section header, action button, skeleton and
// empty state in the app converges on these, so spacing/typography/status
// colors stay identical everywhere. Consume tokens only — no raw hex.
import { type CSSProperties, type ReactNode } from "react";
import { VARS as C, FONT, TONE, toneFor, type Tone } from "@/lib/theme";

export function Badge({ label, tone, mono, title }: { label: string; tone?: Tone; mono?: boolean; title?: string }) {
  const t = TONE[tone ?? toneFor(label)];
  return (
    <span title={title} style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.4, textTransform: "uppercase",
      fontFamily: mono ? FONT.mono : undefined, color: t.fg, background: t.bg,
      border: `1px solid ${t.bd}`, borderRadius: 999, padding: "2px 8px", whiteSpace: "nowrap" }}>{label}</span>
  );
}

export function Card({ children, pad = 14, style }: { children: ReactNode; pad?: number; style?: CSSProperties }) {
  return (
    <div className="aac-card" style={{ background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: "var(--radius-3)", padding: pad, ...style }}>{children}</div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: Tone }) {
  return (
    <div style={{ background: C.surface2, border: `1px solid ${C.line}`, borderRadius: "var(--radius-2)", padding: "9px 11px", minWidth: 0 }}>
      <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: 0.5, textTransform: "uppercase", color: C.meta }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, fontFamily: FONT.mono, color: tone ? TONE[tone].fg : C.text,
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
      {sub ? <div style={{ fontSize: 9.5, color: C.dim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</div> : null}
    </div>
  );
}

export function SectionHeader({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 0.5, textTransform: "uppercase",
    color: C.meta, margin: "14px 0 7px" }}>{children}</div>;
}

export function ActionButton({ label, onClick, tone = "info", ariaLabel }:
  { label: string; onClick: () => void; tone?: Tone; ariaLabel?: string }) {
  const t = TONE[tone];
  return (
    <button onClick={onClick} aria-label={ariaLabel ?? label}
      style={{ fontSize: 11, fontWeight: 800, color: "#fff", background: t.fg, border: "none",
        borderRadius: "var(--radius-1)", padding: "7px 13px", cursor: "pointer" }}>{label}</button>
  );
}

export function Skeleton({ h = 44, n = 3 }: { h?: number; n?: number }) {
  return (
    <div aria-hidden aria-busy="true" style={{ display: "grid", gap: 8 }}>
      {Array.from({ length: n }).map((_, i) => <div key={i} className="aac-skeleton" style={{ height: h }} />)}
    </div>
  );
}

export function EmptyState({ title, hint, children }: { title: string; hint?: string; children?: ReactNode }) {
  return (
    <Card pad={18} style={{ textAlign: "center" }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{title}</div>
      {hint ? <div style={{ fontSize: 11.5, color: C.sub, marginTop: 4 }}>{hint}</div> : null}
      {children ? <div style={{ marginTop: 10, display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>{children}</div> : null}
    </Card>
  );
}

export function ErrorState({ title, detail, onRetry }: { title: string; detail?: string; onRetry?: () => void }) {
  const t = TONE.junk;
  return (
    <Card pad={16} style={{ borderColor: t.bd, background: t.bg }}>
      <div style={{ fontSize: 12.5, fontWeight: 800, color: t.fg }}>{title}</div>
      {detail ? <div style={{ fontSize: 11, color: C.sub, marginTop: 4, fontFamily: FONT.mono, overflowWrap: "anywhere" }}>{detail.slice(0, 200)}</div> : null}
      {onRetry ? <div style={{ marginTop: 9 }}><ActionButton label="Retry" onClick={onRetry} tone="junk" /></div> : null}
    </Card>
  );
}

export function Expander({ summary, children, defaultOpen }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} style={{ border: `1px solid ${C.line}`, borderRadius: "var(--radius-2)", background: C.surface2 }}>
      <summary style={{ cursor: "pointer", padding: "9px 12px", fontSize: 11, fontWeight: 700, color: C.sub,
        listStyle: "none", userSelect: "none" }}>{summary}</summary>
      <div style={{ padding: "2px 12px 12px" }}>{children}</div>
    </details>
  );
}
