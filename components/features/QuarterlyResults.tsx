"use client"
// components/features/QuarterlyResults.tsx
// Quarterly P&L trend for one stock, from /api/quarterly?symbol=. Latest-quarter headline
// (revenue / net profit / OPM%) with YoY, plus a net-profit trend across recent quarters.
// Data: quarterly_financials (Screener "Quarters" section). Research/context, not a buy call.

import { useEffect, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", border2: "#F1F5F9", bg: "#F7F9FC",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2",
  blue: "#2563EB", track: "#EEF2F7",
}

const inr = (v: number | null) => {
  if (v === null) return "—"
  const a = Math.abs(v)
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L cr`
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(2)}k cr`
  return `₹${v.toFixed(0)} cr`
}
const pct = (v: number | null) => (v === null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`)
const gcol = (v: number | null) => (v === null ? T.textMeta : v >= 0 ? T.green : T.red)

function Chip({ label, value }: { label: string; value: number | null }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 700, color: gcol(value),
      background: value === null ? T.bg : value >= 0 ? T.greenBg : T.redBg,
      padding: "1px 6px", borderRadius: 6, marginLeft: 6 }}>
      {label} {pct(value)}
    </span>
  )
}

export default function QuarterlyResults({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setData(null)
    fetch(`/api/quarterly?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json()).then(setData).catch(() => setData({ error: true }))
      .finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Loading quarterly results…</div>
  if (!data || data.error) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Quarterly results unavailable.</div>
  const q: any[] = data.quarters || []
  if (!q.length)
    return (
      <div style={{ fontSize: 12, color: T.textSub, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 12px" }}>
        No quarterly data for this name yet — it appears once the Quarters section is loaded.
      </div>
    )

  const latest = q[0]                                // most-recent-first from the API
  const trend = [...q].slice(0, 8).reverse()         // oldest→newest for the bars
  const maxNp = Math.max(...trend.map(t => Math.abs(t.net_profit ?? 0)), 1)

  return (
    <div>
      {/* latest-quarter headline */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <div style={{ flex: "1 1 120px", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "8px 10px" }}>
          <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600 }}>REVENUE · {latest.label}</div>
          <div style={{ fontSize: 15, fontWeight: 800, color: T.text }}>{inr(latest.sales)}<Chip label="YoY" value={latest.sales_yoy} /></div>
        </div>
        <div style={{ flex: "1 1 120px", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "8px 10px" }}>
          <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600 }}>NET PROFIT · {latest.label}</div>
          <div style={{ fontSize: 15, fontWeight: 800, color: T.text }}>{inr(latest.net_profit)}<Chip label="YoY" value={latest.np_yoy} /></div>
        </div>
        <div style={{ flex: "1 1 80px", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "8px 10px" }}>
          <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600 }}>OPM %</div>
          <div style={{ fontSize: 15, fontWeight: 800, color: T.text }}>{latest.opm_pct === null ? "—" : `${latest.opm_pct.toFixed(1)}%`}</div>
        </div>
      </div>

      {/* net-profit trend bars */}
      <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 4 }}>NET PROFIT TREND (last {trend.length} quarters)</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 5, height: 70 }}>
        {trend.map((t, i) => {
          const h = Math.max(3, (Math.abs(t.net_profit ?? 0) / maxNp) * 60)
          const neg = (t.net_profit ?? 0) < 0
          return (
            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end" }}>
              <div style={{ width: "100%", maxWidth: 26, height: h, background: neg ? T.red : T.blue, borderRadius: "3px 3px 0 0", opacity: i === trend.length - 1 ? 1 : 0.55 }} />
              <div style={{ fontSize: 7.5, color: T.textMeta, marginTop: 3, transform: "rotate(-35deg)", whiteSpace: "nowrap", height: 12 }}>{t.label}</div>
            </div>
          )
        })}
      </div>

      <div style={{ fontSize: 9, color: T.textMeta, marginTop: 8, lineHeight: 1.5 }}>
        Quarterly P&amp;L from Screener. YoY compares against the same quarter a year earlier. Latest quarter
        highlighted. OPM% = operating profit ÷ revenue. Research context — confirm against the actual filing.
      </div>
    </div>
  )
}
