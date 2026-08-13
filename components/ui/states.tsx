"use client";
// components/ui/states.tsx — the ONE screen-state vocabulary, applied to every
// data surface in this cycle (Command Center + Admin). Six honest states plus a
// provenance line. Rules that hold everywhere:
//   • missing data is NEVER rendered as zero — it renders as a pending/empty state;
//   • source + "as of" show whenever the caller has them;
//   • every failure offers a retry.
// Consumes CSS-var tokens only, so all six adapt to system/light/dark.
import { type ReactNode } from "react";

export type ScreenStateKind =
  | "loading"
  | "empty"
  | "pending" // partial / awaiting more data
  | "stale" // data older than expected
  | "config" // configuration-required
  | "error"; // failed request

const TOKENS: Record<ScreenStateKind, { fg: string; bg: string; bd: string; glyph: string }> = {
  loading: { fg: "var(--c-text-meta)", bg: "var(--c-surface-2)", bd: "var(--c-border)", glyph: "⋯" },
  empty: { fg: "var(--c-text-meta)", bg: "var(--c-surface)", bd: "var(--c-border)", glyph: "∅" },
  pending: { fg: "var(--c-warning)", bg: "var(--c-warning-bg)", bd: "var(--c-warning-bd)", glyph: "◔" },
  stale: { fg: "var(--c-warning)", bg: "var(--c-warning-bg)", bd: "var(--c-warning-bd)", glyph: "◷" },
  config: { fg: "var(--s-info)", bg: "var(--s-info-bg)", bd: "var(--s-info-bd)", glyph: "⚙" },
  error: { fg: "var(--c-negative)", bg: "var(--c-negative-bg)", bd: "var(--c-negative-bd)", glyph: "!" },
};

// Provenance line — renders only when the caller actually has source/as-of.
export function SourceAsOf({ source, asOf }: { source?: string | null; asOf?: string | null }) {
  if (!source && !asOf) return null;
  return (
    <div style={{ fontSize: 10.5, color: "var(--c-text-meta)", marginTop: 6, fontFamily: "var(--f-mono)" }}>
      {source ? <span>source: {source}</span> : null}
      {source && asOf ? <span> · </span> : null}
      {asOf ? <span>as of {asOf}</span> : null}
    </div>
  );
}

export function ScreenState({
  kind,
  title,
  detail,
  source,
  asOf,
  retryLabel = "Retry",
  onRetry,
  action,
  compact = false,
}: {
  kind: ScreenStateKind;
  title: string;
  detail?: ReactNode;
  source?: string | null;
  asOf?: string | null;
  retryLabel?: string;
  onRetry?: () => void;
  action?: ReactNode;
  compact?: boolean;
}) {
  const t = TOKENS[kind];
  const busy = kind === "loading";
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      aria-busy={busy || undefined}
      className={busy ? "aac-skeleton" : undefined}
      style={{
        background: t.bg,
        border: `1px solid ${t.bd}`,
        borderRadius: "var(--radius-3)",
        padding: compact ? "10px 12px" : "14px 16px",
      }}
    >
      <div style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
        <span aria-hidden style={{ color: t.fg, fontWeight: 800, fontSize: 14, lineHeight: 1.3 }}>{t.glyph}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: compact ? 12 : 13, fontWeight: 700, color: t.fg }}>{title}</div>
          {detail ? (
            <div style={{ fontSize: 11.5, color: "var(--c-text-sub)", marginTop: 3, lineHeight: 1.45 }}>{detail}</div>
          ) : null}
          <SourceAsOf source={source} asOf={asOf} />
          {(onRetry || action) && (
            <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {onRetry ? (
                <button
                  type="button"
                  onClick={onRetry}
                  style={{
                    fontSize: 11,
                    fontWeight: 800,
                    color: "#fff",
                    background: t.fg,
                    border: "none",
                    borderRadius: "var(--radius-1)",
                    padding: "6px 13px",
                    cursor: "pointer",
                  }}
                >
                  {retryLabel}
                </button>
              ) : null}
              {action}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Named convenience wrappers so call sites read as the state they mean.
export const LoadingState = (p: Omit<Parameters<typeof ScreenState>[0], "kind">) => <ScreenState kind="loading" {...p} />;
export const EmptyDataState = (p: Omit<Parameters<typeof ScreenState>[0], "kind">) => <ScreenState kind="empty" {...p} />;
export const PendingState = (p: Omit<Parameters<typeof ScreenState>[0], "kind">) => <ScreenState kind="pending" {...p} />;
export const StaleState = (p: Omit<Parameters<typeof ScreenState>[0], "kind">) => <ScreenState kind="stale" {...p} />;
export const ConfigRequiredState = (p: Omit<Parameters<typeof ScreenState>[0], "kind">) => <ScreenState kind="config" {...p} />;
export const FailedState = (p: Omit<Parameters<typeof ScreenState>[0], "kind">) => <ScreenState kind="error" {...p} />;
