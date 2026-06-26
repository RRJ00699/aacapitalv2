"use client"
// components/features/StockDeals.tsx
// Institutional bulk/block deals for one stock, from /api/deals?symbol=.
// Answers "what are large players actually doing in this name?" — net buy/sell over the
// history + a recent deal list. Mounts inside the research workspace. Self-fetching, so
// it just needs a `symbol`. Research signal, not a buy call.

import { useEffect, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", border2: "#F1F5F9", bg: "#F7F9FC",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2",
}

const inr = (v: number) => {
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  return `₹${Math.round(v).toLocaleString("en-IN")}`
}

function Stat({ label, value, color, strong }: { label: string; value: string; color: string; strong?: boolean }) {
  return (
    <div style={{ flex: "1 1 90px", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "8px 10px" }}>
      <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: strong ? 16 : 14, fontWeight: 800, color }}>{value}</div>
    </div>
  )
}

export default function StockDeals({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setData(null)
    fetch(`/api/deals?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json())
      .then(j => { setData(j?.ok ? j : null); setLoading(false) })
      .catch(() => setLoading(false))
  }, [symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 0" }}>Loading institutional deals…</div>

  const deals = data?.deals ?? []
  if (!deals.length) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 0" }}>No bulk/block deals on record for {symbol}.</div>

  const s = data.summary || {}
  const net = s.net_value ?? 0

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <Stat label="Net flow" value={inr(net)} color={net >= 0 ? T.green : T.red} strong />
        <Stat label={`Buys (${s.buy_count ?? 0})`} value={inr(s.buy_value ?? 0)} color={T.green} />
        <Stat label={`Sells (${s.sell_count ?? 0})`} value={inr(s.sell_value ?? 0)} color={T.red} />
      </div>

      <div style={{ border: `1px solid ${T.border}`, borderRadius: 12, overflow: "hidden", maxHeight: 320, overflowY: "auto" }}>
        {deals.map((d: any, i: number) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
            borderBottom: `1px solid ${T.border2}`, fontSize: 12 }}>
            <span style={{ width: 74, color: T.textMeta, flexShrink: 0 }}>{d.date}</span>
            <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 5, flexShrink: 0,
              background: d.side === "BUY" ? T.greenBg : T.redBg, color: d.side === "BUY" ? T.green : T.red }}>
              {d.side}
            </span>
            <span style={{ fontSize: 8, fontWeight: 600, color: T.textMeta, flexShrink: 0 }}>{d.deal_type}</span>
            <span style={{ flex: 1, minWidth: 0, color: T.textSub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
              title={d.client}>{d.client}</span>
            <span style={{ color: T.text, fontWeight: 600, flexShrink: 0 }}>{inr(d.value)}</span>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 9, color: T.textMeta, marginTop: 6 }}>
        {data.count} deal{data.count === 1 ? "" : "s"} on record · bulk/block are disclosed, often partial positions. Research signal, not a buy call.
      </div>
    </div>
  )
}
