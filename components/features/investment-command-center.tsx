"use client"
// components/features/investment-command-center.tsx
// The unified Investment Command Center — Sprint 8+
// All 6 engines in one screen: Technical DNA + Business DNA + Earnings + Smart Money + Convergence

import { useState, useEffect, useCallback } from "react"
import { colors } from "@/lib/design/tokens"

// ── Types ─────────────────────────────────────────────────────────────────────
interface StockRow {
  nse_symbol: string
  name: string
  industry: string
  current_price: number
  market_cap: number
  business_dna_score: number
  business_dna_grade: string
  earnings_score: number
  earnings_category: string
  smart_money_score: number
  smart_money_signal: string
  roce: number
  sales_growth_3y: number
  eps_growth_3y: number
  debt_to_equity: number
  business_dna_signals: string[]
  convergence_score: number
  multibagger_probability?: number
  eps_yoy_growth?: number
  bulk_net_flow?: number
  conviction?: {
    score: number
    conviction: string
    expected_6m: string
    expected_12m: string
    risk: string
  }
}

interface Summary {
  total_stocks: number
  aplus: number
  a_grade: number
  rerating: number
  accumulation: number
  high_conviction: number
  avg_dna_score: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const GRADE_COLORS: Record<string, { bg: string; text: string }> = {
  "A+": { bg: "#f3e8ff", text: "#7c3aed" },
  "A":  { bg: "#EFF6FF", text: "#2563EB" },
  "B":  { bg: "#F0FDF4", text: "#16A34A" },
  "C":  { bg: "#F9FAFB", text: "#6b7280" },
}

const CONVICTION_COLORS: Record<string, string> = {
  "Exceptional": "#7c3aed",
  "High":        "#2563EB",
  "Medium":      "#D97706",
  "Low":         "#6b7280",
}

const SIGNAL_COLORS: Record<string, string> = {
  "Strong Accumulation": "#16A34A",
  "Accumulation":        "#65a30d",
  "Neutral":             "#6b7280",
  "Distribution":        "#D97706",
  "Heavy Distribution":  "#DC2626",
}

function ScoreBar({ score, color, label }: { score: number; color: string; label: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 10, color: "#6b7280" }}>{label}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color }}>{score}</span>
      </div>
      <div style={{ height: 4, background: "#F3F4F6", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${score}%`, height: "100%", background: color,
          borderRadius: 2, transition: "width 0.5s ease" }} />
      </div>
    </div>
  )
}

function GradeBadge({ grade }: { grade: string }) {
  const c = GRADE_COLORS[grade] ?? GRADE_COLORS["C"]
  return (
    <span style={{ background: c.bg, color: c.text, fontSize: 11, fontWeight: 800,
      padding: "2px 8px", borderRadius: 6 }}>{grade}</span>
  )
}


function inrFormat(raw: unknown) {
  const n = Number(raw)
  if (!n) return "—"
  if (n >= 10000) return `₹${(n / 1000).toFixed(0)}K Cr`
  if (n >= 1000)  return `₹${(n / 1000).toFixed(1)}K Cr`
return `₹${n.toFixed(0)} Cr`
}


// ── Main component ────────────────────────────────────────────────────────────
export function InvestmentCommandCenter() {
  const [view, setView]         = useState<"top"|"rerating"|"multibagger"|"smart_money">("top")
  const [data, setData]         = useState<StockRow[]>([])
  const [summary, setSummary]   = useState<Summary | null>(null)
  const [loading, setLoading]   = useState(true)
  const [search, setSearch]     = useState("")
  const [error, setError]       = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail]     = useState<Record<string, unknown> | null>(null)

  const fetchData = useCallback(async (v: string) => {
    setLoading(true); setError(null)
    try {
      const [dataRes, summaryRes] = await Promise.all([
        fetch(`/api/investment-command-center?view=${v}&limit=30`).then(r => r.json()),
        fetch(`/api/investment-command-center`).then(r => r.json()),
      ])
      if (dataRes.ok) setData(dataRes.data ?? [])
      else setError(dataRes.error)
      if (summaryRes.ok) setSummary(summaryRes.summary)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed")
    } finally { setLoading(false) }
  }, [])

  const fetchDetail = useCallback(async (symbol: string) => {
    try {
      const r = await fetch(`/api/investment-command-center?symbol=${symbol}`)
      const d = await r.json()
      if (d.ok) setDetail(d)
    } catch {}
  }, [])

  useEffect(() => { fetchData(view) }, [view, fetchData])

  const filtered = data.filter(r =>
    !search || r.nse_symbol.toLowerCase().includes(search.toLowerCase()) ||
    r.name.toLowerCase().includes(search.toLowerCase())
  )

  const tabs = [
    { key: "top",         label: "⚡ Top Convergence" },
    { key: "rerating",    label: "🚀 Rerating" },
    { key: "multibagger", label: "🧬 Multibagger" },
    { key: "smart_money", label: "🐋 Smart Money" },
  ] as const

  return (
    <div style={{ background: colors.background, minHeight: "100vh", paddingBottom: 80 }}>
      {/* Header */}
      <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB",
        padding: "20px 20px 0", position: "sticky", top: 0, zIndex: 10 }}>

        <div style={{ display: "flex", justifyContent: "space-between",
          alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: colors.textPrimary,
              letterSpacing: "-0.4px" }}>Investment Command Center</div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
              6-engine convergence · {summary?.total_stocks ?? "—"} stocks scored
            </div>
          </div>
          <button onClick={() => fetchData(view)}
            style={{ background: "#EFF6FF", color: colors.blue,
              border: "1px solid #BFDBFE", borderRadius: 10,
              padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            ↻ Refresh
          </button>
        </div>

        {/* Summary pills */}
        {summary && (
          <div style={{ display: "flex", gap: 6, overflowX: "auto",
            paddingBottom: 4, scrollbarWidth: "none" as const, marginBottom: 10 }}>
            {[
              { label: "A+ DNA",       value: summary.aplus,           color: "#7c3aed" },
              { label: "A Grade",       value: summary.a_grade,         color: "#2563EB" },
              { label: "Rerating",      value: summary.rerating,        color: "#16A34A" },
              { label: "Smart Buying",  value: summary.accumulation,    color: "#D97706" },
              { label: "High Conv.",    value: summary.high_conviction,  color: "#DC2626" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ background: color + "12",
                border: `1px solid ${color}30`, borderRadius: 8,
                padding: "4px 10px", whiteSpace: "nowrap" as const, flexShrink: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 800, color }}>{value}</span>
                <span style={{ fontSize: 10, color, marginLeft: 4 }}>{label}</span>
              </div>
            ))}
          </div>
        )}

        {/* Search */}
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search symbol or company..."
          style={{ width: "100%", border: "1px solid #E5E7EB", borderRadius: 10,
            padding: "9px 12px", fontSize: 13, color: colors.textPrimary,
            background: "#F9FAFB", boxSizing: "border-box" as const,
            marginBottom: 8 }} />

        {/* Tabs */}
        <div style={{ display: "flex", borderTop: "1px solid #E5E7EB" }}>
          {tabs.map(t => (
            <button key={t.key} onClick={() => { setView(t.key); setSelected(null) }}
              style={{ flex: 1, padding: "11px 4px", fontSize: 11,
                fontWeight: view === t.key ? 700 : 500,
                color: view === t.key ? colors.blue : "#6b7280",
                background: "transparent", border: "none", cursor: "pointer",
                borderBottom: view === t.key ? `2px solid ${colors.blue}` : "2px solid transparent" }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: 16 }}>
        {error && (
          <div style={{ background: "#FEF2F2", border: "1px solid #FECACA",
            borderRadius: 12, padding: 14, color: "#DC2626", fontSize: 13,
            marginBottom: 12 }}>
            {error.includes("not imported") ? (
              <span>Run <code style={{ background: "#F3F4F6", padding: "1px 5px",
                borderRadius: 3 }}>node scripts/fundamentals-import.mjs</code> first to load fundamental data.</span>
            ) : error}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#9CA3AF" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
            <div>Scoring {summary?.total_stocks ?? ""} stocks across 6 engines…</div>
          </div>
        ) : (
          <>
            {/* Detail panel */}
            {selected && detail && <DetailPanel data={detail} onClose={() => { setSelected(null); setDetail(null) }} />}

            {/* Stock list */}
            {!selected && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {filtered.length === 0 && (
                  <div style={{ textAlign: "center", padding: "40px 0",
                    color: "#9CA3AF", fontSize: 13 }}>No stocks match this filter</div>
                )}
                {filtered.map((stock, i) => (
                  <StockCard key={stock.nse_symbol} stock={stock} rank={i + 1}
                    view={view}
                    onSelect={() => {
                      setSelected(stock.nse_symbol)
                      fetchDetail(stock.nse_symbol)
                    }} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Stock Card ────────────────────────────────────────────────────────────────
function StockCard({ stock, rank, view, onSelect }: {
  stock: StockRow; rank: number; view: string; onSelect: () => void
}) {
  const convScore = stock.conviction?.score ?? stock.convergence_score ?? 0
  const convColor = convScore >= 75 ? "#7c3aed" : convScore >= 60 ? "#2563EB" :
                    convScore >= 45 ? "#D97706" : "#6b7280"
  const smColor = SIGNAL_COLORS[stock.smart_money_signal] ?? "#6b7280"

  return (
    <div onClick={onSelect}
      style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 14,
        padding: "14px 16px", boxShadow: "0 1px 6px rgba(0,0,0,0.04)",
        cursor: "pointer", transition: "box-shadow 0.15s" }}>

      {/* Top row */}
      <div style={{ display: "flex", justifyContent: "space-between",
        alignItems: "flex-start", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 44, height: 44, borderRadius: "50%",
            background: `conic-gradient(${convColor} ${convScore}%, #F3F4F6 0%)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0 }}>
            <div style={{ width: 32, height: 32, borderRadius: "50%",
              background: "#fff", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 11, fontWeight: 800, color: convColor }}>
              {convScore}
            </div>
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ fontSize: 15, fontWeight: 800,
                color: colors.textPrimary }}>{stock.nse_symbol}</span>
              <GradeBadge grade={stock.business_dna_grade} />
              {view === "multibagger" && stock.multibagger_probability && (
                <span style={{ background: "#f3e8ff", color: "#7c3aed",
                  fontSize: 10, fontWeight: 700, padding: "2px 6px",
                  borderRadius: 5 }}>{stock.multibagger_probability}%</span>
              )}
            </div>
            <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 1 }}>
              {stock.name} · {stock.industry}
            </div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 14, fontWeight: 700,
            color: colors.textPrimary }}>₹{Number(stock.current_price).toFixed(0)}</div>
          <div style={{ fontSize: 10, color: "#9CA3AF" }}>{inrFormat(stock.market_cap)}</div>
        </div>
      </div>

      {/* Score bars */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
        <ScoreBar score={stock.business_dna_score ?? 0} color="#2563EB" label="Business DNA" />
        <ScoreBar score={stock.earnings_score ?? 0} color="#16A34A" label="Earnings" />
      </div>

      {/* Bottom row */}
      <div style={{ display: "flex", justifyContent: "space-between",
        alignItems: "center", marginTop: 8 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" as const }}>
          {stock.roce > 0 && (
            <span style={{ fontSize: 10, color: "#6b7280",
              background: "#F9FAFB", padding: "2px 7px",
              borderRadius: 5, border: "1px solid #E5E7EB" }}>
              ROCE {Number(stock.roce).toFixed(0)}%
            </span>
          )}
          {stock.sales_growth_3y > 0 && (
            <span style={{ fontSize: 10, color: "#6b7280",
              background: "#F9FAFB", padding: "2px 7px",
              borderRadius: 5, border: "1px solid #E5E7EB" }}>
              Rev {Number(stock.sales_growth_3y).toFixed(0)}% CAGR
            </span>
          )}
          {view === "rerating" && stock.eps_yoy_growth && (
            <span style={{ fontSize: 10, fontWeight: 700,
              color: "#16A34A", background: "#F0FDF4",
              padding: "2px 7px", borderRadius: 5 }}>
              EPS +{Number(stock.eps_yoy_growth).toFixed(0)}% YoY
            </span>
          )}
        </div>
        <span style={{ fontSize: 10, fontWeight: 600, color: smColor }}>
          {stock.smart_money_signal}
        </span>
      </div>

      {/* Signals */}
      {stock.business_dna_signals?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap" as const,
          gap: 4, marginTop: 8 }}>
          {stock.business_dna_signals.slice(0, 3).map(s => (
            <span key={s} style={{ fontSize: 9, color: "#16A34A",
              background: "#F0FDF4", padding: "2px 6px", borderRadius: 4,
              border: "1px solid #BBF7D0" }}>{s}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Detail Panel ──────────────────────────────────────────────────────────────
function DetailPanel({ data, onClose }: { data: Record<string, unknown>; onClose: () => void }) {
  const scores = data.scores as Record<string, unknown> ?? {}
  const conv   = data.conviction as Record<string, unknown> ?? {}
  const fund   = data.fundamentals as Record<string, unknown> ?? {}
  const tech   = data.technical as Record<string, unknown> ?? {}
  const sigs   = data.signals as Record<string, unknown[]> ?? {}

  const convColor = Number(scores.convergence) >= 75 ? "#7c3aed" :
                    Number(scores.convergence) >= 60 ? "#2563EB" : "#D97706"

  return (
    <div style={{ background: "#fff", border: "1px solid #E5E7EB",
      borderRadius: 16, padding: 20, marginBottom: 16,
      boxShadow: "0 4px 20px rgba(0,0,0,0.08)" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
        alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20, fontWeight: 800,
              color: colors.textPrimary }}>{data.symbol as string}</span>
            <span style={{ background: convColor + "18", color: convColor,
              fontSize: 12, fontWeight: 700, padding: "3px 10px",
              borderRadius: 7 }}>{conv.conviction as string}</span>
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
            {data.name as string} · ₹{Number(data.current_price)?.toFixed(0)} · {data.industry as string}
          </div>
        </div>
        <button onClick={onClose}
          style={{ background: "#F3F4F6", border: "none", borderRadius: 8,
            padding: "6px 12px", fontSize: 12, cursor: "pointer",
            color: "#6b7280" }}>✕ Close</button>
      </div>

      {/* 6 Engine Scores */}
      <div style={{ background: "#F9FAFB", borderRadius: 12,
        padding: 14, marginBottom: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280",
          marginBottom: 10 }}>6-ENGINE CONVERGENCE</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
          {[
            { label: "Technical DNA",  score: Number(scores.technical_dna),  color: "#2563EB" },
            { label: "Business DNA",   score: Number(scores.business_dna),   color: "#7c3aed" },
            { label: "Earnings Intel", score: Number(scores.earnings),       color: "#16A34A" },
            { label: "Smart Money",    score: Number(scores.smart_money),    color: "#D97706" },
            { label: "Sector",         score: 50,                            color: "#6b7280" },
            { label: "Convergence",    score: Number(scores.convergence),    color: convColor },
          ].map(({ label, score, color }) => (
            <div key={label} style={{ background: "#fff",
              border: `1px solid ${score >= 60 ? color + "40" : "#E5E7EB"}`,
              borderRadius: 8, padding: "8px 10px", textAlign: "center" }}>
              <div style={{ fontSize: 18, fontWeight: 800, color }}>{score}</div>
              <div style={{ fontSize: 9, color: "#9CA3AF", marginTop: 2 }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Conviction box */}
      <div style={{ background: convColor + "10",
        border: `1px solid ${convColor}30`,
        borderRadius: 12, padding: 14, marginBottom: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 8 }}>
          {[
            { label: "6M Expected",   value: conv.expected_6m as string },
            { label: "12M Expected",  value: conv.expected_12m as string },
            { label: "Position Size", value: conv.position_size as string },
            { label: "Risk",          value: conv.risk as string },
          ].map(({ label, value }) => (
            <div key={label}>
              <div style={{ fontSize: 10, color: "#6b7280" }}>{label}</div>
              <div style={{ fontSize: 14, fontWeight: 700,
                color: convColor, marginTop: 2 }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Fundamentals */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280",
          marginBottom: 8 }}>FUNDAMENTALS</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 6 }}>
          {[
            { label: "ROCE",        value: `${Number(fund.roce)?.toFixed(1)}%` },
            { label: "ROE",         value: `${Number(fund.roe)?.toFixed(1)}%` },
            { label: "Rev CAGR 3Y", value: `${Number(fund.sales_cagr_3y)?.toFixed(1)}%` },
            { label: "EPS CAGR 3Y", value: `${Number(fund.eps_cagr_3y)?.toFixed(1)}%` },
            { label: "D/E",         value: Number(fund.debt_equity)?.toFixed(2) },
            { label: "Int. Cover",  value: Number(fund.interest_cover)?.toFixed(1) },
          ].map(({ label, value }) => (
            <div key={label} style={{ background: "#F9FAFB",
              border: "1px solid #E5E7EB", borderRadius: 8,
              padding: "6px 8px", textAlign: "center" }}>
              <div style={{ fontSize: 13, fontWeight: 700,
                color: colors.textPrimary }}>{value}</div>
              <div style={{ fontSize: 9, color: "#9CA3AF" }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Signals */}
      {(sigs.business as string[] ?? []).length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700,
            color: "#6b7280", marginBottom: 6 }}>SIGNALS</div>
          <div style={{ display: "flex", flexWrap: "wrap" as const, gap: 5 }}>
            {(sigs.business as string[]).map(s => (
              <span key={s} style={{ background: "#F0FDF4", color: "#16A34A",
                fontSize: 11, fontWeight: 600, padding: "3px 9px",
                borderRadius: 6, border: "1px solid #BBF7D0" }}>✓ {s}</span>
            ))}
            {(sigs.warnings as string[] ?? []).map(w => (
              <span key={w} style={{ background: "#FEF3C7", color: "#D97706",
                fontSize: 11, fontWeight: 600, padding: "3px 9px",
                borderRadius: 6 }}>⚠ {w}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


