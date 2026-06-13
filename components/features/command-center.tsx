"use client"
// components/features/command-center.tsx
// TAB 1: Command Center — Daily decision cockpit
// Replaces Markets as homepage. Answers "what matters today" in 30 seconds.

import { useState, useEffect, useCallback } from "react"
import { colors } from "@/lib/design/tokens"
import { useMarketData } from "@/lib/hooks/useMarketData"
import { PortfolioAlertsSection } from "./portfolio-alerts-section"
import { GlobalMarketsStrip } from "./global-markets-strip"
import { ZerodhaStatusBanner } from "./zerodha-status-banner"


// ── Types ─────────────────────────────────────────────────────────────────────
interface MarketData {
  regime?: string
  nifty_close?: number
  banknifty_close?: number
  vix?: number
  fii_net?: number
  dii_net?: number
  pcr?: number
  created_at?: string
}

interface GlobalAsset {
  symbol: string
  name: string
  price: number
  change_pct: number
}

interface SectorRow {
  industry_group: string
  rotation_score: number
  rotation_signal: string
  return_3m: number
  return_6m: number
  avg_roce: number
}

interface OpportunityRow {
  nse_symbol: string
  name: string
  business_dna_score: number
  business_dna_grade: string
  earnings_score: number
  smart_money_score: number
  smart_money_signal: string
  convergence_score: number
  industry: string
  return_6m?: number
}

interface PortfolioAlert {
  symbol: string
  name: string
  action: "EXIT" | "TRIM" | "ADD" | "HOLD"
  reason: string
  conv_score: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const REGIME_CONFIG: Record<string, { color: string; bg: string; label: string; action: string }> = {
  HOT:     { color: "#DC2626", bg: "#FEF2F2", label: "🔥 HOT",     action: "Deploy aggressively. IPO mode ON. All engines green." },
  NORMAL:  { color: "#16A34A", bg: "#F0FDF4", label: "📈 NORMAL",  action: "Deploy selectively. Conviction ≥75 for IPOs." },
  CAUTION: { color: "#D97706", bg: "#FEF3C7", label: "⚠️ CAUTION", action: "Reduce size. Conviction ≥80 only. Watch stops." },
  COLD:    { color: "#2563EB", bg: "#EFF6FF", label: "❄️ COLD",    action: "Deploy max 40% cash. IPO mode OFF. Stage 2 stocks only." },
  FROZEN:  { color: "#6b7280", bg: "#F9FAFB", label: "🧊 FROZEN",  action: "Hold cash. Wait for regime to improve. No new positions." },
}

function inr(n: number) {
  if (!n) return "—"
  const abs = Math.abs(n)
  const sign = n < 0 ? "−" : "+"
  if (abs >= 10000000) return `${sign}₹${(abs/10000000).toFixed(1)}Cr`
  if (abs >= 100000)   return `${sign}₹${(abs/100000).toFixed(0)}L`
  return `${sign}₹${abs.toFixed(0)}`
}

function pctColor(v: number) {
  return v > 0 ? "#16A34A" : v < 0 ? "#DC2626" : "#6b7280"
}

function convColor(s: number) {
  return s >= 75 ? "#7c3aed" : s >= 60 ? "#2563EB" : s >= 45 ? "#D97706" : "#6b7280"
}

// ── Main Component ─────────────────────────────────────────────────────────────
export function CommandCenter({ onStockSelect }: { onStockSelect?: (sym: string) => void }) {
  const { snapshot, loading: marketLoading, refresh, refreshing, autoRefreshed } = useMarketData()
  const [global, setGlobal]       = useState<GlobalAsset[]>([])
  const [sectors, setSectors]     = useState<SectorRow[]>([])
  const [opps, setOpps]           = useState<OpportunityRow[]>([])
  const [alerts, setAlerts]       = useState<PortfolioAlert[]>([])
  const [loading, setLoading]     = useState(true)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [globalRes, sectorRes, oppRes] = await Promise.all([
        fetch("/api/market/global").then(r => r.json()).catch(() => ({ assets: [] })),
        fetch("/api/sector-rotation?view=rankings").then(r => r.json()).catch(() => ({ sectors: [] })),
        fetch("/api/investment-command-center?view=top&limit=10").then(r => r.json()).catch(() => ({ data: [] })),
      ])

      if (globalRes?.assets) setGlobal(globalRes.assets)
      if (sectorRes?.sectors) setSectors(sectorRes.sectors.slice(0, 8))
      if (oppRes?.data) setOpps(oppRes.data.slice(0, 8))

      // Generate portfolio alerts from holdings
      const holdRes = await fetch("/api/broker/holdings").then(r => r.json()).catch(() => null)
      if (holdRes?.data) {
        const generatedAlerts: PortfolioAlert[] = []
        for (const h of (holdRes.data || []).slice(0, 10)) {
          const sym = h.tradingsymbol
          const fundRes = await fetch(`/api/investment-command-center?symbol=${sym}`)
            .then(r => r.json()).catch(() => null)
          if (!fundRes?.ok) continue
          const conv = fundRes.scores?.convergence ?? 0
          const pnl = h.pnl ?? 0
          if (conv < 35) generatedAlerts.push({ symbol: sym, name: h.tradingsymbol, action: "EXIT", reason: `Convergence ${conv}/100 — all engines weak`, conv_score: conv })
          else if (conv < 50 && pnl > 0) generatedAlerts.push({ symbol: sym, name: h.tradingsymbol, action: "TRIM", reason: `Convergence ${conv}/100 — consider reducing`, conv_score: conv })
          else if (conv >= 75) generatedAlerts.push({ symbol: sym, name: h.tradingsymbol, action: "ADD", reason: `Convergence ${conv}/100 — high conviction, add on dips`, conv_score: conv })
        }
        setAlerts(generatedAlerts.slice(0, 5))
      }

      setLastUpdate(new Date())
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const regime = snapshot?.market_regime ?? "NORMAL"
  const rc = REGIME_CONFIG[regime] ?? REGIME_CONFIG["NORMAL"]
  const now = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", timeZone: "Asia/Kolkata" })

  return (
    <div style={{ background: colors.background, minHeight: "100vh", paddingBottom: 80 }}>
      {/* Sticky regime bar */}
      <div style={{ background: rc.bg, borderBottom: `2px solid ${rc.color}30`,
        padding: "10px 16px", position: "sticky", top: 56, zIndex: 9 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: rc.color }}>{rc.label}</span>
            <span style={{ fontSize: 11, color: rc.color, opacity: 0.8 }}>{rc.action}</span>
          </div>
          <div style={{ display: "flex", gap: 12, fontSize: 11, color: rc.color }}>
            <span>Nifty {snapshot?.nifty_price ? Number(snapshot.nifty_price).toFixed(0) : "—"}</span>
            <span>VIX {snapshot?.vix ? Number(snapshot.vix).toFixed(1) : "—"}</span>
            <span>FII {inr(Number(snapshot?.fii_flow ?? 0))}</span>
          </div>
        </div>
      </div>

      <div style={{ padding: "16px 16px 0" }}>
        {/* Zerodha reconnect banner */}
        <ZerodhaStatusBanner />

        {/* Date + refresh */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: colors.textPrimary }}>{now}</div>
            <div style={{ fontSize: 11, color: "#9CA3AF" }}>
              {snapshot?.last_updated
                ? `Updated ${new Date(snapshot.last_updated).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}`
                : lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : "Loading…"}
            </div>
          </div>
          <button onClick={refresh} disabled={refreshing || marketLoading}
            style={{ background: "#EFF6FF", color: colors.blue, border: "1px solid #BFDBFE",
              borderRadius: 10, padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            {refreshing ? "Refreshing…" : autoRefreshed ? "✓ Live" : "↻ Refresh"}
          </button>
        </div>

        {/* Market dashboard */}
        <Section title="📊 Market Dashboard">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
            {[
              { label: "Nifty",     value: snapshot?.nifty_price ? Number(snapshot.nifty_price).toFixed(0) : "—", sub: "" },
              { label: "BankNifty", value: snapshot?.banknifty_price ? Number(snapshot.banknifty_price).toFixed(0) : "—", sub: "" },
              { label: "India VIX", value: snapshot?.vix ? Number(snapshot.vix).toFixed(1) : "—", sub: "" },
              { label: "FII Net",   value: inr(Number(snapshot?.fii_flow ?? 0)), sub: "today", color: pctColor(Number(snapshot?.fii_flow ?? 0)) },
              { label: "DII Net",   value: inr(Number(snapshot?.dii_flow ?? 0)), sub: "today", color: pctColor(Number(snapshot?.dii_flow ?? 0)) },
              { label: "PCR",       value: snapshot?.pcr ? Number(snapshot.pcr).toFixed(2) : "—", sub: "" },
            ].map(({ label, value, sub, color }) => (
              <div key={label} style={{ background: "#fff", border: "1px solid #E5E7EB",
                borderRadius: 10, padding: "10px 12px", textAlign: "center" }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: color ?? colors.textPrimary }}>{value}</div>
                <div style={{ fontSize: 9, color: "#9CA3AF" }}>{label}{sub ? ` · ${sub}` : ""}</div>
              </div>
            ))}
          </div>
        </Section>

        {/* Global markets + advances/declines */}
        <Section title="🌍 Global Markets">
          <GlobalMarketsStrip />
        </Section>

        {/* Sector leadership */}
        <Section title="🏭 Sector Leadership">
          {sectors.length === 0 ? (
            <EmptyState msg="Run: node scripts/sector-rotation-import.mjs" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {sectors.slice(0, 6).map(s => {
                const hot = s.rotation_score >= 60
                return (
                  <div key={s.industry_group} style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", background: "#fff", border: "1px solid #E5E7EB",
                    borderRadius: 10, padding: "8px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ width: 6, height: 6, borderRadius: "50%",
                        background: hot ? "#16A34A" : "#6b7280" }} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: colors.textPrimary }}>
                        {s.industry_group}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 11, color: pctColor(Number(s.return_3m)) }}>
                       {Number(s.return_3m) > 0 ? "+" : ""}{Number(s.return_3m).toFixed(0)}% 3M                      </span>
                      <div style={{ background: hot ? "#7c3aed" : "#6b7280",
                        color: "#fff", fontSize: 10, fontWeight: 700,
                        padding: "2px 7px", borderRadius: 5 }}>
                        {s.rotation_score}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        {/* Opportunity board */}
        <Section title="⚡ Opportunity Board">
          {opps.length === 0 ? (
            <EmptyState msg="Run: node scripts/fundamentals-import.mjs" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {opps.map((o, i) => {
                const cs = o.convergence_score ?? 0
                const cc = convColor(cs)
                return (
                  <div key={o.nse_symbol}
                    onClick={() => onStockSelect?.(o.nse_symbol)}
                    style={{ background: "#fff", border: "1px solid #E5E7EB",
                      borderRadius: 12, padding: "12px 14px", cursor: "pointer",
                      boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{ width: 36, height: 36, borderRadius: "50%",
                          background: `conic-gradient(${cc} ${cs}%, #F3F4F6 0%)`,
                          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <div style={{ width: 26, height: 26, borderRadius: "50%", background: "#fff",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 10, fontWeight: 800, color: cc }}>{cs}</div>
                        </div>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{ fontSize: 14, fontWeight: 800, color: colors.textPrimary }}>
                              {o.nse_symbol}
                            </span>
                            <span style={{ background: cc + "18", color: cc, fontSize: 9,
                              fontWeight: 700, padding: "2px 6px", borderRadius: 4 }}>
                              {o.business_dna_grade}
                            </span>
                          </div>
                          <div style={{ fontSize: 10, color: "#9CA3AF" }}>{o.industry}</div>
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: o.smart_money_signal?.includes("Accum") ? "#16A34A" : "#6b7280" }}>
                          {o.smart_money_signal}
                        </div>
                        <div style={{ fontSize: 10, color: "#9CA3AF" }}>DNA {o.business_dna_score} · Earn {o.earnings_score}</div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        <PortfolioAlertsSection />
        {alerts.length > 0 && (
          <Section title="🚨 Portfolio Alerts">
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {alerts.map(a => {
                const colors2 = { EXIT: "#DC2626", TRIM: "#D97706", ADD: "#16A34A", HOLD: "#6b7280" }
                const ac = colors2[a.action]
                return (
                  <div key={a.symbol}
                    onClick={() => onStockSelect?.(a.symbol)}
                    style={{ background: ac + "10", border: `1px solid ${ac}30`,
                      borderRadius: 10, padding: "10px 14px", cursor: "pointer",
                      display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 800, color: ac,
                          background: ac + "18", padding: "2px 8px", borderRadius: 5 }}>
                          {a.action}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary }}>
                          {a.symbol}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 3 }}>{a.reason}</div>
                    </div>
                    <span style={{ fontSize: 18, color: "#9CA3AF" }}>›</span>
                  </div>
                )
              })}
            </div>
          </Section>
        )}

        {/* Alert history log */}
        <AlertHistoryLog onStockSelect={onStockSelect} />

        {lastUpdate && (
          <div style={{ textAlign: "center", fontSize: 10, color: "#D1D5DB", margin: "16px 0" }}>
            Data refreshes every 5 minutes · Pre-market brief sent daily at 6:30 AM IST
          </div>
        )}
      </div>
    </div>
  )
}

// ── Alert History Log ─────────────────────────────────────────────────────────
function AlertHistoryLog({ onStockSelect }: { onStockSelect?: (sym: string) => void }) {
  const [alerts, setAlerts] = useState<Record<string, unknown>[]>([])

  useEffect(() => {
    fetch("/api/alert-history?limit=5").then(r => r.json())
      .then(d => { if (d.ok) setAlerts(d.alerts ?? []) })
      .catch(() => {})
  }, [])

  if (!alerts.length) return null

  return (
    <Section title="📋 Recent Convergence Alerts">
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {alerts.map((a: Record<string, unknown>, i) => (
          <div key={i} onClick={() => onStockSelect?.(a.symbol as string)}
            style={{ background: "#fff", border: "1px solid #E5E7EB",
              borderRadius: 10, padding: "8px 12px", cursor: "pointer",
              display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <span style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary }}>
                {a.symbol as string}
              </span>
              <span style={{ fontSize: 11, color: "#9CA3AF", marginLeft: 8 }}>
                {a.alert_tier as string}
              </span>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#7c3aed" }}>
                Score {a.convergence_score as number}/100
              </div>
              <div style={{ fontSize: 10, color: "#9CA3AF" }}>
                {new Date(a.created_at as string).toLocaleDateString("en-IN")}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#9CA3AF",
        letterSpacing: "0.5px", marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}

function EmptyState({ msg }: { msg: string }) {
  return (
    <div style={{ background: "#F9FAFB", borderRadius: 10, padding: "14px",
      fontSize: 11, color: "#9CA3AF", textAlign: "center" }}>
      {msg}
    </div>
  )
}



