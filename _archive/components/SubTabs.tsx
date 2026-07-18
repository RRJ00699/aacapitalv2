"use client";
// components/app-shell/SubTabs.tsx — the pill sub-nav used inside routes.

export default function SubTabs({
  tabs, active, onChange, top = 64,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  top?: number;
}) {
  return (
    <div style={{ background: "var(--t-surface)", borderBottom: "1px solid var(--t-border)", padding: "8px 20px", display: "flex", gap: 6, position: "sticky", top, zIndex: 9, overflowX: "auto" }}>
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          style={{
            padding: "5px 12px", borderRadius: 20,
            border: `1px solid ${active === t.id ? "var(--t-blue)" : "var(--t-border)"}`,
            background: active === t.id ? "var(--t-blueBg)" : "transparent",
            color: active === t.id ? "var(--t-blue)" : "var(--t-meta)",
            fontSize: 12, fontWeight: active === t.id ? 700 : 400, cursor: "pointer", whiteSpace: "nowrap",
          }}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
