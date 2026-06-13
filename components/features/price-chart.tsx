// components/features/price-chart.tsx
// Sprint 13: Price chart for Stock Research Workspace
// Uses price_monthly data from /api/price-history?symbol=DIXON
// Shows 1Y/3Y/5Y/10Y views with volume bars
// Drop-in: import { PriceChart } from "./price-chart"
// Usage:   <PriceChart symbol="DIXON" />

"use client"
import { useState, useEffect } from "react"
import {
  ResponsiveContainer, ComposedChart, Line, Bar,
  XAxis, YAxis, Tooltip, ReferenceLine, CartesianGrid
} from "recharts"

const C = {
  bg: "#FAFAF8", surface: "#FFFFFF", blue: "#2563EB",
  green: "#16A34A", red: "#DC2626", gray: "#6b7280",
  border: "#E5E7EB", text: "#111827", gridLine: "#F3F4F6",
}

interface Candle {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface ChartPoint {
  date: string
  label: string
  close: number
  volume: number
  ma50?: number
  ma200?: number
}

const PERIODS = [
  { key: "1Y", months: 12, label: "1Y" },
  { key: "3Y", months: 36, label: "3Y" },
  { key: "5Y", months: 60, label: "5Y" },
  { key: "10Y", months: 120, label: "10Y" },
]

function computeMA(data: ChartPoint[], n: number): ChartPoint[] {
  return data.map((d, i) => {
    if (i < n - 1) return d
    const slice = data.slice(i - n + 1, i + 1)
    const avg = slice.reduce((s, x) => s + x.close, 0) / n
    return { ...d, [`ma${n}`]: Math.round(avg) }
  })
}

function formatDate(dateStr: string, months: number): string {
  const d = new Date(dateStr)
  if (months <= 12) return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" })
  if (months <= 36) return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" })
  return d.getFullYear().toString()
}

function inr(n: number): string {
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `₹${(n / 100000).toFixed(1)}L`
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const change = payload.find((p: any) => p.dataKey === "close")
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 8, padding: "8px 12px", fontSize: 11, boxShadow: "0 2px 8px rgba(0,0,0,0.1)" }}>
      <div style={{ fontWeight: 700, color: C.text, marginBottom: 4 }}>{d.label}</div>
      <div style={{ color: C.blue }}>Close: ₹{Number(d.close).toLocaleString("en-IN")}</div>
      {d.ma50  && <div style={{ color: "#F59E0B" }}>MA50: ₹{Math.round(d.ma50).toLocaleString("en-IN")}</div>}
      {d.ma200 && <div style={{ color: C.red }}>MA200: ₹{Math.round(d.ma200).toLocaleString("en-IN")}</div>}
      <div style={{ color: C.gray, marginTop: 2 }}>Vol: {(d.volume / 1000).toFixed(0)}K</div>
    </div>
  )
}

interface Props {
  symbol: string
  height?: number
}

export function PriceChart({ symbol, height = 280 }: Props) {
  const [candles, setCandles] = useState<Candle[]>([])
  const [period, setPeriod] = useState("1Y")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return
    setLoading(true)
    setError(null)
    fetch(`/api/price-history?symbol=${symbol}&months=120`)
      .then(async r => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then(d => {
        setCandles(d.candles ?? [])
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [symbol])

  if (loading) return (
    <div style={{ height, display: "flex", alignItems: "center",
      justifyContent: "center", color: C.gray, fontSize: 12 }}>
      Loading chart...
    </div>
  )

  if (error || candles.length === 0) return (
    <div style={{ height, display: "flex", alignItems: "center",
      justifyContent: "center", color: C.gray, fontSize: 12 }}>
      {error ? `Chart unavailable (${error})` : "No price data"}
    </div>
  )

  const months = PERIODS.find(p => p.key === period)?.months ?? 12
  const cutoff = new Date()
  cutoff.setMonth(cutoff.getMonth() - months)

  const filtered = candles
    .filter(c => new Date(c.date) >= cutoff)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())

  let chartData: ChartPoint[] = filtered.map(c => ({
    date: c.date,
    label: formatDate(c.date, months),
    close: Number(c.close),
    volume: Number(c.volume),
  }))

  // Add moving averages
  chartData = computeMA(chartData, 50)
  chartData = computeMA(chartData, 200)

  const prices = chartData.map(d => d.close)
  const minPrice = Math.min(...prices) * 0.97
  const maxPrice = Math.max(...prices) * 1.03
  const firstPrice = prices[0]
  const lastPrice = prices[prices.length - 1]
  const changeAbs = lastPrice - firstPrice
  const changePct = ((changeAbs / firstPrice) * 100).toFixed(1)
  const isPositive = changeAbs >= 0
  const maxVol = Math.max(...chartData.map(d => d.volume))

  // Thin out labels for readability
  const labelStep = Math.max(1, Math.floor(chartData.length / 8))
  const displayData = chartData.map((d, i) => ({
    ...d,
    displayLabel: i % labelStep === 0 ? d.label : "",
  }))

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 18, fontWeight: 800, color: C.text }}>
            ₹{lastPrice.toLocaleString("en-IN")}
          </span>
          <span style={{ fontSize: 12, fontWeight: 600,
            color: isPositive ? C.green : C.red,
            background: isPositive ? "#F0FDF4" : "#FEF2F2",
            padding: "2px 8px", borderRadius: 4 }}>
            {isPositive ? "+" : ""}{changePct}% ({period})
          </span>
        </div>

        {/* Period selector */}
        <div style={{ display: "flex", gap: 4 }}>
          {PERIODS.map(p => (
            <button key={p.key} onClick={() => setPeriod(p.key)}
              style={{
                fontSize: 11, fontWeight: 600, padding: "3px 8px",
                borderRadius: 5,
                border: period === p.key ? `1px solid ${C.blue}` : `1px solid ${C.border}`,
                background: period === p.key ? C.blue : C.surface,
                color: period === p.key ? "#fff" : C.gray,
                cursor: "pointer",
              }}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={displayData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={C.gridLine} vertical={false} />
          <XAxis
            dataKey="displayLabel"
            tick={{ fontSize: 9, fill: C.gray }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="price"
            domain={[minPrice, maxPrice]}
            tick={{ fontSize: 9, fill: C.gray }}
            axisLine={false}
            tickLine={false}
            width={55}
            tickFormatter={v => `₹${(v/1000).toFixed(0)}K`}
          />
          <YAxis
            yAxisId="vol"
            orientation="right"
            domain={[0, maxVol * 4]}
            hide
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Volume bars */}
          <Bar yAxisId="vol" dataKey="volume"
            fill={isPositive ? "#BBF7D0" : "#FECACA"}
            opacity={0.6} radius={[1, 1, 0, 0]} />

          {/* MA200 */}
          <Line yAxisId="price" type="monotone" dataKey="ma200"
            stroke={C.red} strokeWidth={1} dot={false}
            strokeDasharray="4 2" connectNulls />

          {/* MA50 */}
          <Line yAxisId="price" type="monotone" dataKey="ma50"
            stroke="#F59E0B" strokeWidth={1} dot={false}
            connectNulls />

          {/* Price line */}
          <Line yAxisId="price" type="monotone" dataKey="close"
            stroke={isPositive ? C.green : C.red}
            strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginTop: 4, justifyContent: "flex-end" }}>
        {[
          { color: isPositive ? C.green : C.red, label: "Price" },
          { color: "#F59E0B", label: "MA50" },
          { color: C.red, label: "MA200", dashed: true },
        ].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ width: 16, height: 2,
              borderTop: l.dashed ? `2px dashed ${l.color}` : `2px solid ${l.color}` }} />
            <span style={{ fontSize: 9, color: C.gray }}>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
