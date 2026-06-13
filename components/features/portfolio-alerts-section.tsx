// components/features/portfolio-alerts-section.tsx
// Used inside command-center.tsx — the Portfolio Alerts panel
// Drop-in replacement for the placeholder "Portfolio Alerts" section in Sprint 9 Command Center
//
// Usage in command-center.tsx:
//   import { PortfolioAlertsSection } from "./portfolio-alerts-section";
//   ... replace the existing Portfolio Alerts placeholder div with <PortfolioAlertsSection />

"use client";

import { useEffect, useState } from "react";

interface AlertResult {
  symbol: string;
  action: "EXIT" | "TRIM" | "ADD" | "HOLD";
  urgency: "IMMEDIATE" | "THIS_WEEK" | "MONITOR";
  current_price: number;
  average_price: number;
  pnl_pct: number;
  convergence_score: number;
  convergence_version: string;
  engines_fired: number;
  reasons: string[];
  weekly_signal?: string;
  suggested_action: string;
  risk_flags: string[];
}

interface AlertSummary {
  total: number;
  exit: number;
  trim: number;
  add: number;
  hold: number;
  immediate_action: number;
  weekly_coverage: number;
  v2_scored: number;
}

interface AlertsResponse {
  summary: AlertSummary;
  alerts: AlertResult[];
}

// Design system tokens (from foundation)
const TOKENS = {
  background: "#FAFAF8",
  surface: "#FFFFFF",
  blue: "#2563EB",
  blueBg: "#EFF6FF",
  green: "#16A34A",
  amber: "#D97706",
  red: "#DC2626",
  textPrimary: "#111827",
  border: "#E5E7EB",
  gray: "#6b7280",
  purple: "#7c3aed",
};

const ACTION_CONFIG = {
  EXIT: { color: TOKENS.red, bg: "#FEF2F2", label: "EXIT", emoji: "🔴" },
  TRIM: { color: TOKENS.amber, bg: "#FEF3C7", label: "TRIM", emoji: "🟡" },
  ADD: { color: TOKENS.green, bg: "#F0FDF4", label: "ADD", emoji: "🟢" },
  HOLD: { color: TOKENS.gray, bg: "#F9FAFB", label: "HOLD", emoji: "⚪" },
};

const URGENCY_CONFIG = {
  IMMEDIATE: { label: "Act now", color: TOKENS.red },
  THIS_WEEK: { label: "This week", color: TOKENS.amber },
  MONITOR: { label: "Monitor", color: TOKENS.gray },
};

function PnlBadge({ pnl }: { pnl: number }) {
  const positive = pnl >= 0;
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        color: positive ? TOKENS.green : TOKENS.red,
        background: positive ? "#F0FDF4" : "#FEF2F2",
        padding: "1px 6px",
        borderRadius: 4,
      }}
    >
      {positive ? "+" : ""}
      {pnl.toFixed(1)}%
    </span>
  );
}

function ScoreBadge({ score, version }: { score: number; version: string }) {
  const color =
    score >= 80 ? TOKENS.purple
    : score >= 65 ? TOKENS.blue
    : score >= 50 ? TOKENS.amber
    : TOKENS.gray;

  return (
    <span
      title={`Convergence ${version}`}
      style={{
        fontSize: 11,
        fontWeight: 600,
        color,
        background: version === "V2" ? "#F5F3FF" : "#F3F4F6",
        padding: "1px 6px",
        borderRadius: 4,
        border: version === "V2" ? `1px solid #DDD6FE` : "none",
      }}
    >
      {score} {version === "V2" ? "V2" : ""}
    </span>
  );
}

function AlertCard({ alert }: { alert: AlertResult }) {
  const cfg = ACTION_CONFIG[alert.action];
  const urgCfg = URGENCY_CONFIG[alert.urgency];
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{
        background: TOKENS.surface,
        border: `1px solid ${alert.urgency === "IMMEDIATE" ? cfg.color : TOKENS.border}`,
        borderLeft: `3px solid ${cfg.color}`,
        borderRadius: 8,
        padding: "10px 12px",
        cursor: "pointer",
        transition: "box-shadow 0.15s",
      }}
      onClick={() => setExpanded((e) => !e)}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, minWidth: 24 }}>
          {cfg.emoji}
        </span>

        {/* Symbol + action */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                fontWeight: 700,
                fontSize: 14,
                color: TOKENS.textPrimary,
                fontFamily: "monospace",
              }}
            >
              {alert.symbol}
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: cfg.color,
                background: cfg.bg,
                padding: "2px 7px",
                borderRadius: 4,
                letterSpacing: "0.5px",
              }}
            >
              {cfg.label}
            </span>
            {alert.urgency !== "MONITOR" && (
              <span
                style={{
                  fontSize: 10,
                  color: urgCfg.color,
                  fontWeight: 600,
                }}
              >
                {urgCfg.label}
              </span>
            )}
          </div>

          {/* Primary reason */}
          <div
            style={{
              fontSize: 11,
              color: "#6b7280",
              marginTop: 2,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: 280,
            }}
          >
            {alert.reasons[0]}
          </div>
        </div>

        {/* Right side: price + scores */}
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ display: "flex", gap: 4, justifyContent: "flex-end", marginBottom: 3 }}>
            <PnlBadge pnl={alert.pnl_pct} />
            <ScoreBadge score={alert.convergence_score} version={alert.convergence_version} />
          </div>
          <div style={{ fontSize: 10, color: TOKENS.gray }}>
            ₹{alert.current_price.toFixed(2)} · {alert.engines_fired} engines
          </div>
        </div>

        {/* Expand indicator */}
        <span style={{ color: TOKENS.gray, fontSize: 12, marginLeft: 4 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            marginTop: 10,
            paddingTop: 10,
            borderTop: `1px solid ${TOKENS.border}`,
          }}
        >
          {/* Suggested action */}
          <div
            style={{
              fontSize: 12,
              color: cfg.color,
              fontWeight: 600,
              marginBottom: 6,
              background: cfg.bg,
              padding: "5px 8px",
              borderRadius: 6,
            }}
          >
            💡 {alert.suggested_action}
          </div>

          {/* All reasons */}
          {alert.reasons.length > 1 && (
            <div style={{ marginBottom: 6 }}>
              {alert.reasons.map((r, i) => (
                <div
                  key={i}
                  style={{ fontSize: 11, color: "#374151", padding: "1px 0" }}
                >
                  · {r}
                </div>
              ))}
            </div>
          )}

          {/* Weekly DNA signal */}
          {alert.weekly_signal && (
            <div
              style={{
                fontSize: 11,
                color: TOKENS.blue,
                background: TOKENS.blueBg,
                padding: "3px 8px",
                borderRadius: 4,
                marginBottom: 4,
              }}
            >
              📊 Weekly: {alert.weekly_signal}
            </div>
          )}

          {/* Risk flags */}
          {alert.risk_flags.length > 0 && (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {alert.risk_flags.map((f) => (
                <span
                  key={f}
                  style={{
                    fontSize: 10,
                    color: TOKENS.red,
                    background: "#FEF2F2",
                    padding: "1px 5px",
                    borderRadius: 3,
                    fontWeight: 600,
                  }}
                >
                  {f}
                </span>
              ))}
            </div>
          )}

          {/* Price detail */}
          <div
            style={{
              marginTop: 8,
              fontSize: 10,
              color: TOKENS.gray,
              display: "flex",
              gap: 12,
            }}
          >
            <span>Avg: ₹{alert.average_price.toFixed(2)}</span>
            <span>LTP: ₹{alert.current_price.toFixed(2)}</span>
            <span>Conv: {alert.convergence_score} ({alert.convergence_version})</span>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryBar({ summary }: { summary: AlertSummary }) {
  const items = [
    { label: "EXIT", count: summary.exit, color: TOKENS.red },
    { label: "TRIM", count: summary.trim, color: TOKENS.amber },
    { label: "ADD", count: summary.add, color: TOKENS.green },
    { label: "HOLD", count: summary.hold, color: TOKENS.gray },
  ];

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        marginBottom: 12,
        padding: "8px 12px",
        background: TOKENS.surface,
        borderRadius: 8,
        border: `1px solid ${TOKENS.border}`,
        flexWrap: "wrap",
      }}
    >
      {items.map((item) => (
        <div
          key={item.label}
          style={{ display: "flex", alignItems: "center", gap: 4 }}
        >
          <span
            style={{
              fontWeight: 700,
              fontSize: 15,
              color: item.color,
            }}
          >
            {item.count}
          </span>
          <span style={{ fontSize: 10, color: TOKENS.gray, fontWeight: 600 }}>
            {item.label}
          </span>
        </div>
      ))}

      <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
        <span style={{ fontSize: 10, color: TOKENS.gray }}>
          {summary.v2_scored}/{summary.total} V2
        </span>
        <span style={{ fontSize: 10, color: TOKENS.blue }}>
          {summary.weekly_coverage} weekly
        </span>
        {summary.immediate_action > 0 && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: TOKENS.red,
              background: "#FEF2F2",
              padding: "1px 6px",
              borderRadius: 4,
            }}
          >
            {summary.immediate_action} URGENT
          </span>
        )}
      </div>
    </div>
  );
}

export function PortfolioAlertsSection() {
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"ALL" | "EXIT" | "TRIM" | "ADD">("ALL");

  useEffect(() => {
    fetch("/api/portfolio-alerts")
      .then((r) => {
        if (r.status === 401) throw new Error("Connect Zerodha in Settings");
        if (!r.ok) throw new Error(`API error ${r.status}`);
        return r.json();
      })
      .then((d: AlertsResponse) => {
        setData(d);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 16, color: TOKENS.gray, fontSize: 13 }}>
        Scoring holdings against all engines...
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: 12,
          background: "#FEF2F2",
          borderRadius: 8,
          fontSize: 13,
          color: TOKENS.red,
        }}
      >
        {error}
      </div>
    );
  }

  if (!data || data.alerts.length === 0) {
    return (
      <div
        style={{
          padding: 16,
          color: TOKENS.gray,
          fontSize: 13,
          textAlign: "center",
        }}
      >
        No holdings found — connect Zerodha in Settings to see portfolio alerts.
      </div>
    );
  }

  const filtered =
    filter === "ALL"
      ? data.alerts
      : data.alerts.filter((a) => a.action === filter);

  return (
    <div>
      {/* Summary bar */}
      <SummaryBar summary={data.summary} />

      {/* Filter tabs */}
      <div
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 10,
        }}
      >
        {(["ALL", "EXIT", "TRIM", "ADD"] as const).map((f) => {
          const active = filter === f;
          const cfg = f === "ALL" ? null : ACTION_CONFIG[f];
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: "4px 10px",
                borderRadius: 6,
                border: active
                  ? `1px solid ${cfg?.color ?? TOKENS.blue}`
                  : `1px solid ${TOKENS.border}`,
                background: active ? (cfg?.bg ?? TOKENS.blueBg) : TOKENS.surface,
                color: active ? (cfg?.color ?? TOKENS.blue) : TOKENS.gray,
                cursor: "pointer",
              }}
            >
              {f}
              {f !== "ALL" && (
                <span style={{ marginLeft: 4, opacity: 0.8 }}>
                  {data.summary[f.toLowerCase() as keyof AlertSummary] as number}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Alert cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {filtered.map((alert) => (
          <AlertCard key={alert.symbol} alert={alert} />
        ))}
      </div>

      {/* Footer note */}
      <div
        style={{
          marginTop: 10,
          fontSize: 10,
          color: TOKENS.gray,
          textAlign: "right",
        }}
      >
        Refreshes on page load · V2 = weekly DNA integrated ·{" "}
        {data.summary.v2_scored}/{data.summary.total} holdings V2 scored
      </div>
    </div>
  );
}
