// components/features/global-markets-strip.tsx
// Sprint 13: Global indices + commodities + advances/declines for Today tab
// Usage: <GlobalMarketsStrip />

"use client"
import { useState, useEffect } from "react"

const C = {
  surface: "#FFFFFF", border: "#E5E7EB", text: "#111827",
  green: "#16A34A", red: "#DC2626", gray: "#6b7280", blue: "#2563EB",
}

interface Asset {
  symbol: string
  name: string
  price: number
  change_pct: number
  currency?: string
}

interface MarketData {
  assets: Asset[]
  advances?: number
  declines?: number
  unchanged?: number
  fetched_at?: string
}

function AssetTile({ asset }: { asset: Asset }) {
  const up = asset.change_pct >= 0
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 8, padding: "8px 12px", minWidth: 110, flex: "0 0 auto" }}>
      <div style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>{asset.name}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
        {asset.currency === "INR" ? "₹" : asset.currency === "USD" ? "$" : ""}
        {Number(asset.price).toLocaleString("en-IN", { maximumFractionDigits: asset.price > 1000 ? 0 : 2 })}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: up ? C.green : C.red }}>
        {up ? "+" : ""}{asset.change_pct?.toFixed(2)}%
      </div>
    </div>
  )
}

export function GlobalMarketsStrip() {
  const [data, setData]     = useState<MarketData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/market/global")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ padding: "8px 16px", color: C.gray, fontSize: 11 }}>
      Loading global markets...
    </div>
  )

  if (!data?.assets?.length) return null

  const advances  = data.advances ?? 0
  const declines  = data.declines ?? 0
  const unchanged = data.unchanged ?? 0
  const total     = advances + declines + unchanged || 1

  // Group assets
  const indices   = data.assets.filter(a => ["S&P 500","NASDAQ","DOW","FTSE","DAX","NIKKEI","HANG SENG","SGX NIFTY"].includes(a.name))
  const commodities = data.assets.filter(a => ["GOLD","CRUDE OIL","SILVER","NATURAL GAS"].includes(a.name))
  const forex     = data.assets.filter(a => ["USD/INR","EUR/INR","GBP/INR"].includes(a.name))

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Advances/Declines bar */}
      {(advances > 0 || declines > 0) && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 8, padding: "10px 14px", marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
            alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.gray,
              textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Market Breadth — NSE
            </span>
            <span style={{ fontSize: 10, color: C.gray }}>
              {advances + declines + unchanged} stocks
            </span>
          </div>
          {/* Progress bar */}
          <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", marginBottom: 6 }}>
            <div style={{ width: `${(advances/total)*100}%`, background: C.green }} />
            <div style={{ width: `${(unchanged/total)*100}%`, background: "#D1D5DB" }} />
            <div style={{ width: `${(declines/total)*100}%`, background: C.red }} />
          </div>
          <div style={{ display: "flex", gap: 16 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: C.green }}>
              ▲ {advances} Advances
            </span>
            <span style={{ fontSize: 12, color: C.gray }}>
              — {unchanged} Unchanged
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: C.red }}>
              ▼ {declines} Declines
            </span>
          </div>
        </div>
      )}

      {/* Global Indices */}
      {indices.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.gray,
            textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 6, paddingLeft: 2 }}>
            Global Indices
          </div>
          <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
            {indices.map(a => <AssetTile key={a.symbol} asset={a} />)}
          </div>
        </div>
      )}

      {/* Commodities + Forex */}
      {(commodities.length > 0 || forex.length > 0) && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.gray,
            textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 6, paddingLeft: 2 }}>
            Commodities & Forex
          </div>
          <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
            {[...commodities, ...forex].map(a => <AssetTile key={a.symbol} asset={a} />)}
          </div>
        </div>
      )}
    </div>
  )
}
