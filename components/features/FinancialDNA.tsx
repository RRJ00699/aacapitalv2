"use client"
// components/features/FinancialDNA.tsx
// Financial DNA — the 10-year fundamentals engine surfaced for one stock, from
// /api/financial-dna?symbol=. Shows the investment grade, 0-100 DNA score, the 7 weighted
// sub-scores (+ a risk/safety score), and explainable green/red flags.
//
// HONEST FRAMING (validated by backtest): DNA is a QUALITY / RISK lens — higher grades carry
// lower volatility, shallower drawdowns and fewer blow-ups. It is NOT a return predictor (raw
// returns inverted over 2021-26 in a junk-led market). Presented as durability + downside, not alpha.

import { useEffect, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", border2: "#F1F5F9", bg: "#F7F9FC",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", blue: "#2563EB", amber: "#D97706",
  orange: "#EA580C", red: "#DC2626", redBg: "#FEF2F2", track: "#EEF2F7",
}

// grade -> colour tier
function gradeColor(g: string): string {
  if (g === "AAA+" || g === "AAA") return T.green
  if (g === "AA") return "#15803D"
  if (g === "A") return T.blue
  if (g === "BBB") return T.amber
  if (g === "BB") return T.orange
  if (g === "B") return "#C2410C"
  return T.red // Avoid
}
function barColor(v: number | null): string {
  if (v == null) return T.textMeta
  if (v >= 70) return T.green
  if (v >= 50) return T.blue
  if (v >= 36) return T.amber
  return T.red
}

const SUBS: [string, string, number | null][] = [
  ["growth", "Growth", 25],
  ["profitability", "Profitability", 20],
  ["cashflow", "Cash flow", 15],
  ["balancesheet", "Balance sheet", 15],
  ["earnings_quality", "Earnings quality", 10],
  ["capalloc", "Capital allocation", 10],
  ["efficiency", "Efficiency", 5],
  ["risk", "Risk / safety", null], // 100 = fewest red flags; not part of weighted score
]

function Bar({ label, value, weight }: { label: string; value: number | null; weight: number | null }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: T.textSub, fontWeight: 600 }}>
          {label}
          {weight != null && <span style={{ color: T.textMeta, fontWeight: 500 }}> · {weight}%</span>}
        </span>
        <span style={{ fontSize: 11, fontWeight: 800, color: barColor(value) }}>
          {value == null ? "—" : Math.round(value)}
        </span>
      </div>
      <div style={{ height: 6, background: T.track, borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, height: "100%", background: barColor(value), borderRadius: 4 }} />
      </div>
    </div>
  )
}

export default function FinancialDNA({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setData(null)
    fetch(`/api/financial-dna?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json()).then(setData).catch(() => setData({ error: true }))
      .finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Loading Financial DNA…</div>
  if (!data || data.error) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Financial DNA unavailable.</div>
  if (data.graded === false)
    return (
      <div style={{ fontSize: 12, color: T.textSub, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 12px" }}>
        Not yet graded — needs 10-year annual fundamentals for this name. It will appear once the financials are loaded.
      </div>
    )

  const gc = gradeColor(data.grade)
  const red: { text: string; severity: string }[] = data.red_flags || []
  const green: string[] = data.green_flags || []

  return (
    <div>
      {/* grade + score header */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 8 }}>
        <div style={{
          minWidth: 76, textAlign: "center", padding: "8px 10px", borderRadius: 12,
          background: gc, color: "#fff", fontWeight: 900, fontSize: 22, lineHeight: 1,
          boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
        }}>
          {data.grade}
          <div style={{ fontSize: 9, fontWeight: 700, opacity: 0.9, marginTop: 3 }}>GRADE</div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span style={{ fontSize: 26, fontWeight: 900, color: T.text }}>{data.dna_score ?? "—"}</span>
            <span style={{ fontSize: 12, color: T.textMeta, fontWeight: 600 }}>/ 100 DNA</span>
          </div>
          <div style={{ fontSize: 10, color: T.textMeta, marginTop: 2 }}>
            {data.years ? `${data.years}-yr fundamentals` : "—"} · quality & risk lens, not a return forecast
          </div>
        </div>
      </div>

      {/* sub-scores */}
      <div style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 12, padding: "12px 12px 6px" }}>
        {SUBS.map(([key, label, w]) => <Bar key={key} label={label} value={data.subs?.[key] ?? null} weight={w} />)}
      </div>

      {/* flags */}
      {(green.length > 0 || red.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: green.length && red.length ? "1fr 1fr" : "1fr", gap: 8, marginTop: 8 }}>
          {green.length > 0 && (
            <div style={{ background: T.greenBg, border: `1px solid #BBF7D0`, borderRadius: 10, padding: "8px 10px" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: T.green, marginBottom: 4 }}>STRENGTHS</div>
              {green.slice(0, 6).map((x, i) => (
                <div key={i} style={{ fontSize: 11, color: T.text, marginBottom: 2 }}>+ {x}</div>
              ))}
            </div>
          )}
          {red.length > 0 && (
            <div style={{ background: T.redBg, border: `1px solid #FECACA`, borderRadius: 10, padding: "8px 10px" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: T.red, marginBottom: 4 }}>RED FLAGS</div>
              {red.slice(0, 6).map((x, i) => (
                <div key={i} style={{ fontSize: 11, color: T.text, marginBottom: 2 }}>
                  <span style={{
                    fontSize: 8, fontWeight: 800, textTransform: "uppercase", padding: "1px 4px", borderRadius: 4, marginRight: 5,
                    background: /crit|high/i.test(x.severity) ? T.red : T.amber, color: "#fff",
                  }}>{x.severity}</span>
                  {x.text}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ fontSize: 9, color: T.textMeta, marginTop: 8, lineHeight: 1.5 }}>
        DNA grades durability from 10-yr financials. Validated as a <b>risk lens</b> (higher grades = lower
        volatility, shallower drawdowns, fewer blow-ups) — use it for conviction & position-sizing, not as a
        return signal. Weights shown drive the score; Risk reflects red-flag severity (100 = fewest).
      </div>
    </div>
  )
}
