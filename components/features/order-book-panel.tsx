// components/features/order-book-panel.tsx
// Order book history panel for Stock Research Workspace
// Shows 8 quarters of order book vs revenue + signal badge
// Usage: <OrderBookPanel symbol="WABAG" />

"use client"
import { useState, useEffect } from "react"

const C = {
  surface: "#FFFFFF", border: "#E5E7EB", text: "#111827",
  green: "#16A34A", red: "#DC2626", blue: "#2563EB",
  amber: "#D97706", gray: "#6b7280", purple: "#7c3aed",
  greenBg: "#F0FDF4", redBg: "#FEF2F2", amberBg: "#FFFBEB",
}

interface Quarter {
  quarter: string
  order_book_cr: number
  revenue_cr: number
  coverage_ratio: number
  qoq_growth: number
  yoy_growth: number
  source: string
  confidence: string
}

interface Signal {
  ob_score: number
  trend: string
  coverage_tier: string
  current_ob_cr: number
  current_coverage: number
  consecutive_growth: number
  peak_coverage: number
  latest_quarter: string
}

function inrCr(n: number): string {
  if (!n) return "—"
  if (n >= 10000) return `₹${(n / 10000).toFixed(1)}T Cr`
  if (n >= 1000)  return `₹${(n / 1000).toFixed(1)}K Cr`
  return `₹${Math.round(n).toLocaleString("en-IN")} Cr`
}

function tierColor(tier: string): string {
  return tier === "STRONG" ? C.green : tier === "HEALTHY" ? C.amber : C.red
}

function tierBg(tier: string): string {
  return tier === "STRONG" ? C.greenBg : tier === "HEALTHY" ? C.amberBg : C.redBg
}

function trendArrow(trend: string): string {
  return trend === "ACCELERATING" ? "↗" : trend === "GROWING" ? "↑" : trend === "DECLINING" ? "↓" : "→"
}

export function OrderBookPanel({ symbol }: { symbol: string }) {
  const [data, setData]     = useState<{ signal: Signal | null; history: Quarter[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    fetch(`/api/order-book?symbol=${symbol}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [symbol])

  if (loading) return (
    <div style={{ padding: "12px 0", fontSize: 12, color: C.gray }}>
      Loading order book...
    </div>
  )

  if (!data?.history?.length) return (
    <div style={{ padding: "12px 0", fontSize: 12, color: C.gray }}>
      No order book data — run: <code>node scripts/orderbook-seed.mjs --symbol {symbol}</code>
    </div>
  )

  const { signal, history } = data
  const maxOB = Math.max(...history.map(h => h.order_book_cr || 0))

  return (
    <div>
      {/* Signal header */}
      {signal && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {/* Score */}
          <div style={{ background: tierBg(signal.coverage_tier),
            border: `1px solid ${tierColor(signal.coverage_tier)}30`,
            borderRadius: 8, padding: "6px 12px", textAlign: "center" }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: tierColor(signal.coverage_tier) }}>
              {signal.ob_score}
            </div>
            <div style={{ fontSize: 9, color: C.gray }}>OB SCORE</div>
          </div>

          {/* Coverage */}
          <div style={{ background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 8, padding: "6px 12px" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: tierColor(signal.coverage_tier) }}>
              {signal.current_coverage}x
            </div>
            <div style={{ fontSize: 9, color: C.gray }}>COVERAGE RATIO</div>
          </div>

          {/* Current OB */}
          <div style={{ background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 8, padding: "6px 12px" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>
              {inrCr(signal.current_ob_cr)}
            </div>
            <div style={{ fontSize: 9, color: C.gray }}>ORDER BOOK</div>
          </div>

          {/* Trend */}
          <div style={{ background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 8, padding: "6px 12px" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.blue }}>
              {trendArrow(signal.trend)} {signal.trend}
            </div>
            <div style={{ fontSize: 9, color: C.gray }}>TREND</div>
          </div>

          {/* Consecutive growth */}
          {signal.consecutive_growth >= 2 && (
            <div style={{ background: "#F5F3FF", border: "1px solid #DDD6FE",
              borderRadius: 8, padding: "6px 12px" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.purple }}>
                {signal.consecutive_growth}Q ↑
              </div>
              <div style={{ fontSize: 9, color: C.gray }}>CONSECUTIVE</div>
            </div>
          )}
        </div>
      )}

      {/* Bar chart — 8 quarters */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 80 }}>
          {history.slice().reverse().map(h => {
            const pct = maxOB > 0 ? (h.order_book_cr / maxOB) * 100 : 0
            const revPct = maxOB > 0 && h.revenue_cr ? (h.revenue_cr / maxOB) * 100 : 0
            const color = h.coverage_ratio >= 2 ? C.green
                        : h.coverage_ratio >= 1 ? C.amber : C.red
            return (
              <div key={h.quarter} style={{ flex: 1, display: "flex",
                flexDirection: "column", alignItems: "center", gap: 2 }}>
                <div style={{ width: "100%", position: "relative",
                  height: 64, display: "flex", alignItems: "flex-end", gap: 1 }}>
                  {/* Revenue bar (gray, shorter) */}
                  {h.revenue_cr > 0 && (
                    <div style={{ flex: 1, height: `${revPct}%`, background: "#E5E7EB",
                      borderRadius: "2px 2px 0 0" }} />
                  )}
                  {/* Order book bar (colored) */}
                  <div style={{ flex: 1, height: `${pct}%`, background: color,
                    borderRadius: "2px 2px 0 0", opacity: 0.85 }} />
                </div>
                <div style={{ fontSize: 8, color: C.gray, textAlign: "center" }}>
                  {h.quarter.replace("FY", "'")}
                </div>
              </div>
            )
          })}
        </div>

        {/* Legend */}
        <div style={{ display: "flex", gap: 12, marginTop: 4, justifyContent: "flex-end" }}>
          {[
            { color: "#E5E7EB", label: "Revenue" },
            { color: C.green,   label: "Order book (≥2x)" },
            { color: C.amber,   label: "Order book (1-2x)" },
          ].map(l => (
            <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 8, height: 8, background: l.color, borderRadius: 1 }} />
              <span style={{ fontSize: 9, color: C.gray }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Quarter table */}
      <div style={{ borderRadius: 8, border: `1px solid ${C.border}`, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead>
            <tr style={{ background: "#F9FAFB" }}>
              <th style={{ padding: "6px 10px", textAlign: "left",   color: C.gray, fontWeight: 500 }}>Quarter</th>
              <th style={{ padding: "6px 10px", textAlign: "right",  color: C.gray, fontWeight: 500 }}>Order Book</th>
              <th style={{ padding: "6px 10px", textAlign: "right",  color: C.gray, fontWeight: 500 }}>Coverage</th>
              <th style={{ padding: "6px 10px", textAlign: "right",  color: C.gray, fontWeight: 500 }}>QoQ</th>
              <th style={{ padding: "6px 10px", textAlign: "right",  color: C.gray, fontWeight: 500 }}>YoY</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h, i) => {
              const covColor = h.coverage_ratio >= 2 ? C.green : h.coverage_ratio >= 1 ? C.amber : C.red
              return (
                <tr key={h.quarter} style={{ borderTop: `1px solid ${C.border}`,
                  background: i === 0 ? "#FAFFFE" : "transparent" }}>
                  <td style={{ padding: "6px 10px", fontWeight: i === 0 ? 700 : 400, color: C.text }}>
                    {h.quarter}
                    {i === 0 && <span style={{ marginLeft: 4, fontSize: 9,
                      background: "#EFF6FF", color: C.blue,
                      padding: "1px 4px", borderRadius: 3 }}>latest</span>}
                  </td>
                  <td style={{ padding: "6px 10px", textAlign: "right",
                    fontWeight: 600, color: C.text }}>{inrCr(h.order_book_cr)}</td>
                  <td style={{ padding: "6px 10px", textAlign: "right",
                    fontWeight: 600, color: covColor }}>
                    {h.coverage_ratio > 0 ? `${h.coverage_ratio}x` : "—"}
                  </td>
                  <td style={{ padding: "6px 10px", textAlign: "right",
                    color: h.qoq_growth > 0 ? C.green : h.qoq_growth < 0 ? C.red : C.gray }}>
                    {h.qoq_growth !== 0 ? `${h.qoq_growth > 0 ? "+" : ""}${h.qoq_growth}%` : "—"}
                  </td>
                  <td style={{ padding: "6px 10px", textAlign: "right",
                    color: h.yoy_growth > 0 ? C.green : h.yoy_growth < 0 ? C.red : C.gray }}>
                    {h.yoy_growth !== 0 ? `${h.yoy_growth > 0 ? "+" : ""}${h.yoy_growth}%` : "—"}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 6, fontSize: 10, color: "#D1D5DB", textAlign: "right" }}>
        Source: {history[0]?.source ?? "—"} · Confidence: {history[0]?.confidence ?? "—"}
      </div>
    </div>
  )
}
