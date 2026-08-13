"use client";
// components/ui/ThemeToggle.tsx — the ONE theme control for the whole app.
// Three explicit modes (System / Light / Dark) as an accessible radio group.
// "System" follows the OS; "Light"/"Dark" are manual overrides that persist.
// Consumes CSS-var tokens only, so it themes itself correctly in every mode.
import { useThemeControls, type Mode } from "@/lib/theme";

const OPTIONS: { mode: Mode; label: string; glyph: string; hint: string }[] = [
  { mode: "system", label: "System", glyph: "◐", hint: "Follow the device setting" },
  { mode: "light", label: "Light", glyph: "☀", hint: "Always light" },
  { mode: "dark", label: "Dark", glyph: "☾", hint: "Always dark" },
];

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { mode, setMode } = useThemeControls();
  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      style={{
        display: "inline-flex",
        gap: 2,
        padding: 2,
        borderRadius: 999,
        border: "1px solid var(--c-border)",
        background: "var(--c-surface-2)",
      }}
    >
      {OPTIONS.map((o) => {
        const on = mode === o.mode;
        return (
          <button
            key={o.mode}
            type="button"
            role="radio"
            aria-checked={on}
            title={o.hint}
            onClick={() => setMode(o.mode)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              cursor: "pointer",
              border: "none",
              borderRadius: 999,
              padding: compact ? "5px 9px" : "6px 12px",
              fontSize: 12,
              fontWeight: on ? 800 : 600,
              letterSpacing: 0.2,
              color: on ? "#fff" : "var(--c-text-meta)",
              background: on ? "var(--s-info)" : "transparent",
              transition: "background var(--m-fast) var(--m-ease), color var(--m-fast) var(--m-ease)",
            }}
          >
            <span aria-hidden style={{ fontSize: 13, lineHeight: 1 }}>{o.glyph}</span>
            {!compact && <span>{o.label}</span>}
          </button>
        );
      })}
    </div>
  );
}
