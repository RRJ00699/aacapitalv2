// components/features/portfolio-intelligence.tsx
// Sprint 12: Portfolio Intelligence Engine
// - Concentration risk alerts (sector overweight)
// - Rebalancing suggestions with specific amounts
// - CAGR vs optimal allocation comparison
// Usage in portfolio-tab.tsx:
//   import { PortfolioIntelligence } from "./portfolio-intelligence"
//   <PortfolioIntelligence />

"use client"
import { useState, useEffect } from "react"

const C = {
  bg: "#FAFAF8", surface: "#FFFFFF", blue: "#2563EB", blueBg: "#EFF6FF",
  green: "#16A34A", amber: "#D97706", red: "#DC2626", purple: "#7c3aed",
  text: "#111827", border: "#E5E7EB", gray: "#6b7280",
}

interface Holding {
  symbol: string
  avgPrice: number
  lastPrice: number
  quantity: number
  currentValue: number
  investedValue: number
  pnl: number
  pnlPct: number
}

interface AlertRow {
  symbol: string
  action: string
  urgency: string
  convergence_score: number
  pnl_pct: number
  reasons: string[]
  suggested_action: string
  risk_flags: string[]
}

interface ConcentrationRisk {
  type: "SECTOR" | "SINGLE_STOCK" | "OVERALL"
  label: string
  current_pct: number
  max_recommended_pct: number
  excess_pct: number
  severity: "HIGH" | "MEDIUM" | "LOW"
  action: string
}

interface RebalanceSuggestion {
  symbol: string
  current_pct: number
  target_pct: number
  current_value: number
  target_value: number
  action: "REDUCE" | "INCREASE" | "EXIT"
  amount_inr: number
  reason: string
}

interface PortfolioMetrics {
  total_value: number
  total_invested: number
  total_pnl: number
  total_pnl_pct: number
  cagr_1y: number | null
  best_performer: string
  worst_performer: string
  avg_convergence: number
  holdings_count: number
  high_conviction_count: number // convergence >= 65
}

function computeMetrics(
  holdings: Holding[],
  alerts: AlertRow[]
): PortfolioMetrics {
  const totalValue    = holdings.reduce((s, h) => s + h.currentValue, 0)
  const totalInvested = holdings.reduce((s, h) => s + h.investedValue, 0)
  const totalPnl      = totalValue - totalInvested
  const totalPnlPct   = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0

  // Rough 1Y CAGR assuming average holding period ~1Y
  const cagr1y = totalInvested > 0
    ? ((totalValue / totalInvested) ** 1 - 1) * 100
    : null

  const sorted = [...holdings].sort((a, b) => b.pnlPct - a.pnlPct)
  const best  = sorted[0]?.symbol ?? "—"
  const worst = sorted[sorted.length - 1]?.symbol ?? "—"

  const alertMap = new Map(alerts.map(a => [a.symbol, a]))
  const scores = holdings.map(h => alertMap.get(h.symbol)?.convergence_score ?? 50)
  const avgConvergence = scores.length ? Math.round(scores.reduce((s, v) => s + v, 0) / scores.length) : 0
  const highConviction = scores.filter(s => s >= 65).length

  return {
    total_value: totalValue,
    total_invested: totalInvested,
    total_pnl: totalPnl,
    total_pnl_pct: totalPnlPct,
    cagr_1y: cagr1y,
    best_performer: best,
    worst_performer: worst,
    avg_convergence: avgConvergence,
    holdings_count: holdings.length,
    high_conviction_count: highConviction,
  }
}

function computeConcentrationRisks(
  holdings: Holding[],
  fundamentalsMap: Map<string, { sector?: string; industry?: string }>
): ConcentrationRisk[] {
  const risks: ConcentrationRisk[] = []
  const totalValue = holdings.reduce((s, h) => s + h.currentValue, 0)
  if (totalValue === 0) return risks

  // Single stock concentration
  for (const h of holdings) {
    const pct = (h.currentValue / totalValue) * 100
    if (pct >= 20) {
      risks.push({
        type: "SINGLE_STOCK",
        label: h.symbol,
        current_pct: pct,
        max_recommended_pct: 15,
        excess_pct: pct - 15,
        severity: pct >= 30 ? "HIGH" : "MEDIUM",
        action: `Trim ${h.symbol} to reduce from ${pct.toFixed(1)}% → 15% of portfolio`,
      })
    }
  }

  // Sector concentration
  const sectorMap = new Map<string, number>()
  for (const h of holdings) {
    const f = fundamentalsMap.get(h.symbol)
    const sector = f?.industry ?? "Unknown"
    sectorMap.set(sector, (sectorMap.get(sector) ?? 0) + h.currentValue)
  }
  for (const [sector, value] of sectorMap) {
    const pct = (value / totalValue) * 100
    if (pct >= 35) {
      risks.push({
        type: "SECTOR",
        label: `${sector} sector`,
        current_pct: pct,
        max_recommended_pct: 30,
        excess_pct: pct - 30,
        severity: pct >= 50 ? "HIGH" : "MEDIUM",
        action: `${sector} overweight at ${pct.toFixed(1)}% — diversify into other sectors`,
      })
    }
  }

  // Too few holdings
  if (holdings.length < 5 && totalValue > 500000) {
    risks.push({
      type: "OVERALL",
      label: "Undiversified portfolio",
      current_pct: holdings.length,
      max_recommended_pct: 8,
      excess_pct: 0,
      severity: "MEDIUM",
      action: `Only ${holdings.length} holdings — consider spreading across 8-15 stocks`,
    })
  }

  return risks.sort((a, b) => {
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 }
    return order[a.severity] - order[b.severity]
  })
}

function computeRebalanceSuggestions(
  holdings: Holding[],
  alerts: AlertRow[]
): RebalanceSuggestion[] {
  const suggestions: RebalanceSuggestion[] = []
  const totalValue = holdings.reduce((s, h) => s + h.currentValue, 0)
  if (totalValue === 0) return suggestions

  const alertMap = new Map(alerts.map(a => [a.symbol, a]))

  // Target: equal weight adjusted by conviction
  // High conviction (convergence >= 70): 10-15%
  // Normal (convergence 50-69): 6-10%
  // Low conviction (< 50): reduce to 3-5%
  const n = holdings.length

  for (const h of holdings) {
    const alert  = alertMap.get(h.symbol)
    const score  = alert?.convergence_score ?? 50
    const action = alert?.action ?? "HOLD"
    const currentPct = (h.currentValue / totalValue) * 100

    let targetPct: number
    if (action === "EXIT")       targetPct = 0
    else if (score >= 70)        targetPct = Math.min(15, (100 / n) * 1.4)
    else if (score >= 60)        targetPct = 100 / n
    else if (score >= 50)        targetPct = Math.max(4, (100 / n) * 0.7)
    else                         targetPct = Math.max(3, (100 / n) * 0.5)

    const targetValue  = (targetPct / 100) * totalValue
    const diff         = targetValue - h.currentValue
    const absDiff      = Math.abs(diff)

    // Only suggest if difference is significant (>5% of position or >₹10,000)
    if (absDiff < Math.max(h.currentValue * 0.05, 10000)) continue

    let rebalanceAction: "REDUCE" | "INCREASE" | "EXIT" = diff > 0 ? "INCREASE" : "REDUCE"
    if (action === "EXIT") rebalanceAction = "EXIT"

    suggestions.push({
      symbol: h.symbol,
      current_pct: currentPct,
      target_pct: targetPct,
      current_value: h.currentValue,
      target_value: targetValue,
      action: rebalanceAction,
      amount_inr: absDiff,
      reason: action === "EXIT"
        ? `Exit signal from engines (convergence ${score})`
        : diff > 0
        ? `High conviction stock — increase allocation (convergence ${score})`
        : `Overweight vs conviction level — trim to ${targetPct.toFixed(1)}%`,
    })
  }

  return suggestions.sort((a, b) => b.amount_inr - a.amount_inr).slice(0, 6)
}

function inr(n: number): string {
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `₹${(n / 100000).toFixed(1)}L`
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}

function MetricCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string
}) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 8, padding: "10px 14px", flex: 1, minWidth: 100 }}>
      <div style={{ fontSize: 10, color: C.gray, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: color ?? C.text }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: C.gray, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export function PortfolioIntelligence() {
  const [holdings, setHoldings]     = useState<Holding[]>([])
  const [alerts, setAlerts]         = useState<AlertRow[]>([])
  const [fundamentals, setFundamentals] = useState<Map<string, { industry?: string }>>(new Map())
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState<string | null>(null)
  const [activeTab, setActiveTab]   = useState<"overview" | "concentration" | "rebalance">("overview")

  useEffect(() => {
    Promise.all([
      fetch("/api/broker/holdings").then(r => r.json()),
      fetch("/api/portfolio-alerts").then(r => r.json()),
    ])
      .then(([holdingsData, alertsData]) => {
        const h: Holding[] = holdingsData.holdings ?? []
        const a: AlertRow[] = alertsData.alerts ?? []
        setHoldings(h)
        setAlerts(a)

        // Fetch fundamentals for sector data
        if (h.length > 0) {
          const symbols = h.map((x: Holding) => x.symbol).join(",")
          return fetch(`/api/investment-command-center?symbols=${symbols}`)
            .then(r => r.json())
            .then(fd => {
              const map = new Map<string, { industry?: string }>()
              for (const row of fd.stocks ?? []) {
                map.set(row.nse_symbol, { industry: row.industry })
              }
              setFundamentals(map)
            })
            .catch(() => {}) // non-critical
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ padding: 16, color: C.gray, fontSize: 13 }}>
      Analysing portfolio...
    </div>
  )

  if (error) return (
    <div style={{ padding: 12, background: "#FEF2F2", borderRadius: 8,
      fontSize: 13, color: C.red }}>
      {error.includes("Broker") || error.includes("401")
        ? "🔗 Connect Zerodha in Settings to see portfolio intelligence"
        : error}
    </div>
  )

  if (holdings.length === 0) return (
    <div style={{ padding: 16, color: C.gray, fontSize: 13, textAlign: "center" }}>
      No holdings found — connect Zerodha in Settings.
    </div>
  )

  const metrics      = computeMetrics(holdings, alerts)
  const risks        = computeConcentrationRisks(holdings, fundamentals)
  const suggestions  = computeRebalanceSuggestions(holdings, alerts)
  const highRisks    = risks.filter(r => r.severity === "HIGH").length

  return (
    <div>
      {/* Tab bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
        {([
          { key: "overview",      label: "Overview" },
          { key: "concentration", label: `Concentration${highRisks > 0 ? ` 🔴${highRisks}` : ""}` },
          { key: "rebalance",     label: `Rebalance${suggestions.length > 0 ? ` (${suggestions.length})` : ""}` },
        ] as const).map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 6,
              border: activeTab === tab.key ? `1px solid ${C.blue}` : `1px solid ${C.border}`,
              background: activeTab === tab.key ? C.blueBg : C.surface,
              color: activeTab === tab.key ? C.blue : C.gray,
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <MetricCard
              label="Portfolio Value"
              value={inr(metrics.total_value)}
              sub={`Invested: ${inr(metrics.total_invested)}`}
            />
            <MetricCard
              label="Total P&L"
              value={`${metrics.total_pnl_pct >= 0 ? "+" : ""}${metrics.total_pnl_pct.toFixed(1)}%`}
              sub={inr(metrics.total_pnl)}
              color={metrics.total_pnl >= 0 ? C.green : C.red}
            />
            <MetricCard
              label="Avg Convergence"
              value={`${metrics.avg_convergence}`}
              sub={`${metrics.high_conviction_count}/${metrics.holdings_count} high conviction`}
              color={metrics.avg_convergence >= 65 ? C.blue : metrics.avg_convergence >= 50 ? C.amber : C.gray}
            />
          </div>

          {/* Best/worst */}
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <div style={{ flex: 1, background: "#F0FDF4", border: "1px solid #BBF7D0",
              borderRadius: 8, padding: "8px 12px" }}>
              <div style={{ fontSize: 10, color: C.gray }}>Best performer</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.green,
                fontFamily: "monospace" }}>{metrics.best_performer}</div>
            </div>
            <div style={{ flex: 1, background: "#FEF2F2", border: "1px solid #FECACA",
              borderRadius: 8, padding: "8px 12px" }}>
              <div style={{ fontSize: 10, color: C.gray }}>Worst performer</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.red,
                fontFamily: "monospace" }}>{metrics.worst_performer}</div>
            </div>
          </div>

          {/* Holdings breakdown */}
          <div style={{ background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 8, overflow: "hidden" }}>
            <div style={{ padding: "8px 12px", borderBottom: `1px solid ${C.border}`,
              fontSize: 11, fontWeight: 700, color: C.gray, textTransform: "uppercase" }}>
              Holdings breakdown
            </div>
            {holdings
              .sort((a, b) => b.currentValue - a.currentValue)
              .map(h => {
                const pct = (h.currentValue / metrics.total_value) * 100
                const alert = alerts.find(a => a.symbol === h.symbol)
                const score = alert?.convergence_score ?? 0
                return (
                  <div key={h.symbol} style={{ padding: "8px 12px",
                    borderBottom: `1px solid ${C.border}`, display: "flex",
                    alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, fontFamily: "monospace",
                      minWidth: 80 }}>{h.symbol}</span>
                    <div style={{ flex: 1, background: "#F3F4F6", borderRadius: 4,
                      height: 4, overflow: "hidden" }}>
                      <div style={{ width: `${Math.min(pct * 2, 100)}%`,
                        height: "100%", background: C.blue, borderRadius: 4 }} />
                    </div>
                    <span style={{ fontSize: 11, color: C.gray, minWidth: 35 }}>
                      {pct.toFixed(1)}%
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 600, minWidth: 55,
                      color: h.pnlPct >= 0 ? C.green : C.red }}>
                      {h.pnlPct >= 0 ? "+" : ""}{Number(h.pnlPct).toFixed(1)}%
                    </span>
                    {score > 0 && (
                      <span style={{ fontSize: 10, color: score >= 65 ? C.blue : C.gray }}>
                        {score}
                      </span>
                    )}
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {/* Concentration risk */}
      {activeTab === "concentration" && (
        <div>
          {risks.length === 0 ? (
            <div style={{ padding: 16, background: "#F0FDF4", borderRadius: 8,
              fontSize: 13, color: C.green, textAlign: "center" }}>
              ✓ Portfolio is well-diversified — no concentration risks detected
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {risks.map((r, i) => (
                <div key={i} style={{
                  background: C.surface,
                  border: `1px solid ${r.severity === "HIGH" ? C.red : C.amber}`,
                  borderLeft: `3px solid ${r.severity === "HIGH" ? C.red : C.amber}`,
                  borderRadius: 8, padding: "10px 12px",
                }}>
                  <div style={{ display: "flex", alignItems: "center",
                    gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: C.text }}>
                      {r.type === "SINGLE_STOCK" ? "📊" : r.type === "SECTOR" ? "🏭" : "⚠️"} {r.label}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 700,
                      color: r.severity === "HIGH" ? C.red : C.amber,
                      background: r.severity === "HIGH" ? "#FEF2F2" : "#FEF3C7",
                      padding: "1px 6px", borderRadius: 4 }}>
                      {r.severity}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>
                    Current: <strong>{r.current_pct.toFixed(1)}%</strong> ·
                    Recommended max: <strong>{r.max_recommended_pct}%</strong> ·
                    Excess: <strong style={{ color: C.red }}>+{r.excess_pct.toFixed(1)}%</strong>
                  </div>
                  <div style={{ fontSize: 11, color: C.text, background: "#F9FAFB",
                    padding: "5px 8px", borderRadius: 5 }}>
                    💡 {r.action}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Rebalancing suggestions */}
      {activeTab === "rebalance" && (
        <div>
          {suggestions.length === 0 ? (
            <div style={{ padding: 16, background: "#F0FDF4", borderRadius: 8,
              fontSize: 13, color: C.green, textAlign: "center" }}>
              ✓ Portfolio allocation looks optimal — no rebalancing needed
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>
                Suggestions based on convergence scores and current allocation
              </div>
              {suggestions.map((s, i) => (
                <div key={i} style={{ background: C.surface,
                  border: `1px solid ${C.border}`,
                  borderLeft: `3px solid ${s.action === "REDUCE" || s.action === "EXIT"
                    ? C.red : C.green}`,
                  borderRadius: 8, padding: "10px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center",
                    gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 13,
                      fontFamily: "monospace" }}>{s.symbol}</span>
                    <span style={{ fontSize: 11, fontWeight: 700,
                      color: s.action === "INCREASE" ? C.green : C.red,
                      background: s.action === "INCREASE" ? "#F0FDF4" : "#FEF2F2",
                      padding: "2px 7px", borderRadius: 4 }}>
                      {s.action === "REDUCE" ? "TRIM" : s.action}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 700,
                      color: s.action === "INCREASE" ? C.green : C.red,
                      marginLeft: "auto" }}>
                      {s.action === "INCREASE" ? "+" : "-"}{inr(s.amount_inr)}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>
                    {s.current_pct.toFixed(1)}% → {s.target_pct.toFixed(1)}% of portfolio
                  </div>
                  <div style={{ fontSize: 11, color: C.text }}>{s.reason}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
