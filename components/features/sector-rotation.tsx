"use client"
// components/features/sector-rotation.tsx
// Sector Rotation Engine — where is institutional money flowing?

import { useState, useEffect, useCallback } from "react"
import { colors } from "@/lib/design/tokens"

interface SectorRow {
  industry_group: string
  stock_count: number
  return_3m: number
  return_6m: number
  avg_roce: number
  avg_sales_growth_3y: number
  avg_pat_growth: number
  avg_pe: number
  total_mcap_cr: number
  rotation_score: number
  rotation_signal: string
  rotation_trend: string
  top_stocks: string[]
  best_stocks?: { nse_symbol: string; name: string; business_dna_score: number; business_dna_grade: string }[]
  sector_net_flow_3m?: number
  sector_tier1_deals?: number
}

interface SectorStock {
  nse_symbol: string
  name: string
  current_price: number
  market_cap: number
  business_dna_score: number
  business_dna_grade: string
  earnings_score: number
  earnings_category: string
  return_3m: number
  return_6m: number
  roce: number
  smart_money_signal: string
}

const TREND_CONFIG: Record<string, { color: string; bg: string; emoji: string }> = {
  "Hot":       { color: "#DC2626", bg: "#FEF2F2", emoji: "🔥" },
  "Rising":    { color: "#16A34A", bg: "#F0FDF4", emoji: "📈" },
  "Stable":    { color: "#D97706", bg: "#FEF3C7", emoji: "➡️" },
  "Weakening": { color: "#6b7280", bg: "#F9FAFB", emoji: "📉" },
  "Cold":      { color: "#2563EB", bg: "#EFF6FF", emoji: "❄️" },
}

function inrCr(n: number) {
  if (!n) return "—"
  if (n >= 100000) return `₹${(n/100000).toFixed(1)}L Cr`
  if (n >= 1000)   return `₹${(n/1000).toFixed(0)}K Cr`
  return `₹${n.toFixed(0)} Cr`
}

export function SectorRotationScreen() {
  const [sectors, setSectors]       = useState<SectorRow[]>([])
  const [flowMap, setFlowMap]       = useState<SectorRow[]>([])
  const [loading, setLoading]       = useState(true)
  const [view, setView]             = useState<"rankings"|"flow"|"hot">("rankings")
  const [selected, setSelected]     = useState<string | null>(null)
  const [sectorStocks, setSectorStocks] = useState<SectorStock[]>([])
  const [stocksLoading, setStocksLoading] = useState(false)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [rankRes, flowRes] = await Promise.all([
        fetch("/api/sector-rotation?view=rankings").then(r => r.json()),
        fetch("/api/sector-rotation?view=flow_map").then(r => r.json()),
      ])
      if (rankRes.ok) setSectors(rankRes.sectors ?? [])
      if (flowRes.ok) setFlowMap(flowRes.flow_map ?? [])
    } catch {}
    setLoading(false)
  }, [])

  const loadSectorStocks = async (sector: string) => {
    setSelected(sector); setStocksLoading(true)
    try {
      const r = await fetch(`/api/sector-rotation?sector=${encodeURIComponent(sector)}`)
      const d = await r.json()
      if (d.ok) setSectorStocks(d.stocks ?? [])
    } catch {}
    setStocksLoading(false)
  }

  useEffect(() => { fetchAll() }, [fetchAll])

  const hot  = sectors.filter(s => s.rotation_score >= 60)
  const neutral = sectors.filter(s => s.rotation_score >= 40 && s.rotation_score < 60)
  const cold = sectors.filter(s => s.rotation_score < 40)

  return (
    <div style={{ background: colors.background, minHeight: "100vh", paddingBottom: 80 }}>
      {/* Header */}
      <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB",
        padding: "20px 20px 0", position: "sticky", top: 0, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between",
          alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: colors.textPrimary,
              letterSpacing: "-0.4px" }}>Sector Rotation</div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
              {sectors.length} sectors · {hot.length} hot · {cold.length} cold
            </div>
          </div>
          <button onClick={fetchAll}
            style={{ background: "#EFF6FF", color: colors.blue, border: "1px solid #BFDBFE",
              borderRadius: 10, padding: "8px 14px", fontSize: 12, fontWeight: 600,
              cursor: "pointer" }}>↻</button>
        </div>

        {/* Summary pills */}
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          {[
            { label: `🔥 ${hot.length} Hot`,      color: "#DC2626", active: true },
            { label: `➡️ ${neutral.length} Neutral`, color: "#D97706", active: false },
            { label: `❄️ ${cold.length} Cold`,     color: "#2563EB", active: false },
          ].map(({ label, color }) => (
            <div key={label} style={{ background: color + "15",
              border: `1px solid ${color}30`, borderRadius: 8,
              padding: "4px 10px", fontSize: 12, fontWeight: 600, color }}>
              {label}
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderTop: "1px solid #E5E7EB" }}>
          {[
            { key: "rankings", label: "📊 Rankings" },
            { key: "flow",     label: "💰 Capital Flow" },
            { key: "hot",      label: "🔥 Hot Sectors" },
          ].map(t => (
            <button key={t.key} onClick={() => { setView(t.key as typeof view); setSelected(null) }}
              style={{ flex: 1, padding: "11px 4px", fontSize: 12,
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
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#9CA3AF" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🔄</div>
            <div>Loading sector data…</div>
          </div>
        ) : selected ? (
          <SectorDrilldown
            sector={selected}
            stocks={sectorStocks}
            loading={stocksLoading}
            onBack={() => setSelected(null)}
          />
        ) : view === "rankings" ? (
          <RankingsView sectors={sectors} onSelect={loadSectorStocks} />
        ) : view === "flow" ? (
          <FlowMapView sectors={flowMap} onSelect={loadSectorStocks} />
        ) : (
          <HotSectorsView sectors={hot} onSelect={loadSectorStocks} />
        )}
      </div>
    </div>
  )
}

// ── Rankings View ─────────────────────────────────────────────────────────────
function RankingsView({ sectors, onSelect }: { sectors: SectorRow[]; onSelect: (s: string) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {sectors.map((s, i) => {
        const tc = TREND_CONFIG[s.rotation_trend] ?? TREND_CONFIG["Stable"]
        return (
          <div key={s.industry_group} onClick={() => onSelect(s.industry_group)}
            style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12,
              padding: "12px 14px", cursor: "pointer",
              boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between",
              alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 36, height: 36, borderRadius: 8,
                  background: tc.bg, display: "flex", alignItems: "center",
                  justifyContent: "center", fontSize: 16, flexShrink: 0 }}>
                  {tc.emoji}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700,
                    color: colors.textPrimary }}>{s.industry_group}</div>
                  <div style={{ fontSize: 10, color: "#9CA3AF" }}>
                    {s.stock_count} stocks · MCap {inrCr(s.total_mcap_cr)}
                  </div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 800,
                  color: tc.color }}>{s.rotation_score}</div>
                <div style={{ fontSize: 9, color: "#9CA3AF" }}>score</div>
              </div>
            </div>

            {/* Score bar */}
            <div style={{ marginTop: 8, height: 4, background: "#F3F4F6",
              borderRadius: 2, overflow: "hidden" }}>
              <div style={{ width: `${s.rotation_score}%`, height: "100%",
                background: tc.color, borderRadius: 2 }} />
            </div>

            {/* Stats */}
            <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
              <Stat label="3M" value={`${Number(s.return_3m) > 0 ? "+" : ""}${Number(s.return_3m).toFixed(1) ?? "—"}%`}
                color={Number(s.return_3m) >= 0 ? "#16A34A" : "#DC2626"} />
              <Stat label="6M" value={`${Number(s.return_6m) > 0 ? "+" : ""}${Number(s.return_6m).toFixed(1) ?? "—"}%`}
                color={Number(s.return_6m) >= 0 ? "#16A34A" : "#DC2626"} />
              <Stat label="ROCE" value={`${Number(s.avg_roce).toFixed(0) ?? "—"}%`} />
              <Stat label="Rev CAGR" value={`${Number(s.avg_sales_growth_3y).toFixed(0) ?? "—"}%`} />
              <div style={{ marginLeft: "auto" }}>
                <span style={{ fontSize: 10, fontWeight: 600,
                  color: tc.color, background: tc.bg,
                  padding: "2px 8px", borderRadius: 5 }}>{s.rotation_signal}</span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Capital Flow Map ──────────────────────────────────────────────────────────
function FlowMapView({ sectors, onSelect }: { sectors: SectorRow[]; onSelect: (s: string) => void }) {
  const sorted = [...sectors].sort((a, b) =>
    (Number(b.sector_net_flow_3m) || 0) - (Number(a.sector_net_flow_3m) || 0)
  )
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE",
        borderRadius: 12, padding: "12px 14px", fontSize: 12,
        color: "#1E40AF", marginBottom: 4 }}>
        💰 <strong>Capital Flow Map</strong> — net institutional buying in last 3 months
        (bulk + block deals). Positive = more buying than selling.
      </div>
      {sorted.map(s => {
        const flow = Number(s.sector_net_flow_3m) || 0
        const isPositive = flow >= 0
        const tc = TREND_CONFIG[s.rotation_trend] ?? TREND_CONFIG["Stable"]
        return (
          <div key={s.industry_group} onClick={() => onSelect(s.industry_group)}
            style={{ background: "#fff", border: "1px solid #E5E7EB",
              borderRadius: 12, padding: "12px 14px", cursor: "pointer" }}>
            <div style={{ display: "flex", justifyContent: "space-between",
              alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700,
                  color: colors.textPrimary }}>{s.industry_group}</div>
                <div style={{ fontSize: 10, color: "#9CA3AF" }}>
                  {s.stock_count} stocks · Score {s.rotation_score}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 15, fontWeight: 800,
                  color: isPositive ? "#16A34A" : "#DC2626" }}>
                  {isPositive ? "+" : ""}{(flow / 10000000).toFixed(1)}Cr
                </div>
                <div style={{ fontSize: 9, color: "#9CA3AF" }}>3M net flow</div>
              </div>
            </div>
            <div style={{ marginTop: 6, height: 5, background: "#F3F4F6",
              borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                width: `${Math.min(100, Math.abs(flow) / 50000000 * 100)}%`,
                height: "100%",
                background: isPositive ? "#16A34A" : "#DC2626",
                borderRadius: 3,
                marginLeft: isPositive ? 0 : "auto"
              }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between",
              marginTop: 6 }}>
              <span style={{ fontSize: 10, color: "#9CA3AF" }}>
                T1 deals: {s.sector_tier1_deals ?? 0}
              </span>
              <span style={{ fontSize: 10, fontWeight: 600, color: tc.color }}>
                {tc.emoji} {s.rotation_signal}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Hot Sectors View ──────────────────────────────────────────────────────────
function HotSectorsView({ sectors, onSelect }: { sectors: SectorRow[]; onSelect: (s: string) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ background: "#FFF7ED", border: "1px solid #FED7AA",
        borderRadius: 12, padding: "12px 14px", fontSize: 12, color: "#92400E" }}>
        🔥 <strong>Hot sectors</strong> — strong 3M+6M momentum + ROCE quality + earnings growth.
        Deploy capital here first, then find best stocks within sector.
      </div>
      {sectors.map(s => {
        const tc = TREND_CONFIG[s.rotation_trend] ?? TREND_CONFIG["Hot"]
        return (
          <div key={s.industry_group} onClick={() => onSelect(s.industry_group)}
            style={{ background: "#fff", border: `2px solid ${tc.color}40`,
              borderRadius: 14, padding: "16px", cursor: "pointer",
              boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }}>
            <div style={{ display: "flex", justifyContent: "space-between",
              alignItems: "flex-start", marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 800,
                  color: colors.textPrimary }}>{s.industry_group}</div>
                <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                  {s.stock_count} stocks · {inrCr(s.total_mcap_cr)}
                </div>
              </div>
              <div style={{ background: tc.bg, color: tc.color,
                fontSize: 20, fontWeight: 900, padding: "4px 12px",
                borderRadius: 10 }}>{s.rotation_score}</div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)",
              gap: 8, marginBottom: 12 }}>
              <StatBox label="3M Return" value={`+${Number(s.return_3m).toFixed(1)}%`} color="#16A34A" />
              <StatBox label="6M Return" value={`+${Number(s.return_6m).toFixed(1)}%`} color="#16A34A" />
              <StatBox label="ROCE"      value={`${Number(s.avg_roce).toFixed(0)}%`} />
              <StatBox label="Rev CAGR"  value={`${Number(s.avg_sales_growth_3y).toFixed(0)}%`} />
            </div>

            {s.top_stocks?.length > 0 && (
              <div>
                <div style={{ fontSize: 10, color: "#9CA3AF", marginBottom: 5 }}>
                  Top stocks by ROCE:
                </div>
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap" as const }}>
                  {s.top_stocks.slice(0, 5).map(sym => (
                    <span key={sym} style={{ background: tc.bg, color: tc.color,
                      fontSize: 11, fontWeight: 700, padding: "3px 8px",
                      borderRadius: 6 }}>{sym}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Sector Drilldown ──────────────────────────────────────────────────────────
function SectorDrilldown({ sector, stocks, loading, onBack }: {
  sector: string; stocks: SectorStock[]; loading: boolean; onBack: () => void
}) {
  return (
    <div>
      <button onClick={onBack}
        style={{ background: "#F3F4F6", border: "none", borderRadius: 8,
          padding: "8px 14px", fontSize: 12, fontWeight: 600,
          color: "#374151", cursor: "pointer", marginBottom: 12 }}>
        ← Back to sectors
      </button>
      <div style={{ fontSize: 16, fontWeight: 800, color: colors.textPrimary,
        marginBottom: 12 }}>{sector}</div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "#9CA3AF" }}>Loading…</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {stocks.map(s => (
            <div key={s.nse_symbol} style={{ background: "#fff",
              border: "1px solid #E5E7EB", borderRadius: 12, padding: "12px 14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 800,
                      color: colors.textPrimary }}>{s.nse_symbol}</span>
                    <span style={{ background: "#EFF6FF", color: "#2563EB",
                      fontSize: 10, fontWeight: 700, padding: "2px 6px",
                      borderRadius: 4 }}>{s.business_dna_grade}</span>
                    <span style={{ fontSize: 10, color: "#6b7280" }}>{s.earnings_category}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "#9CA3AF" }}>{s.name}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>₹{Number(s.current_price).toFixed(0)}</div>
                  <div style={{ fontSize: 10,
                    color: (Number(s.return_6m) ?? 0) >= 0 ? "#16A34A" : "#DC2626" }}>
                    {(Number(s.return_6m) ?? 0) >= 0 ? "+" : ""}{Number(s.return_6m).toFixed(1)}% 6M
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                <Stat label="DNA" value={String(s.business_dna_score)} />
                <Stat label="ROCE" value={`${Number(s.roce).toFixed(0)}%`} />
                <Stat label="Earn" value={String(s.earnings_score)} />
                <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 600,
                  color: s.smart_money_signal?.includes("Accum") ? "#16A34A" : "#6b7280" }}>
                  {s.smart_money_signal}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <span style={{ fontSize: 10, color: "#9CA3AF" }}>{label}: </span>
      <span style={{ fontSize: 11, fontWeight: 700, color: color ?? colors.textPrimary }}>{value}</span>
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB",
      borderRadius: 8, padding: "6px 8px", textAlign: "center" }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: color ?? colors.textPrimary }}>{value}</div>
      <div style={{ fontSize: 9, color: "#9CA3AF" }}>{label}</div>
    </div>
  )
}



