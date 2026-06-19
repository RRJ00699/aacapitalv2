"use client"
// components/MobileApp.tsx
// Dedicated iPhone layout — bottom nav, card-based Today/IPO/Watchlist/Portfolio
// Rendered when window.innerWidth < 768

import { useState, useEffect } from "react"
import { WatchlistScreen } from "./features/watchlist-screen"
import { IpoCalendar } from "./features/ipo-calendar"
import { StockResearchWorkspace } from "./features/stock-research-workspace"

const T = {
  bg:"#F7F9FC", surface:"#FFFFFF", border:"#E5E7EB",
  text:"#0F172A", textSub:"#64748B", textMeta:"#94A3B8",
  green:"#16A34A", greenBg:"#F0FDF4",
  blue:"#2563EB", blueBg:"#EFF6FF",
  amber:"#D97706", amberBg:"#FFFBEB",
  red:"#DC2626",
  teal:"#0D9488", tealBg:"#F0FDFA",
  purple:"#7C3AED",
}
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0

// ── Reusable card ─────────────────────────────────────────────────────────────
function MCard({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 16, padding: "14px 16px", marginBottom: 10, ...style }}>
      {children}
    </div>
  )
}

function MLabel({ children }: { children: string }) {
  return <div style={{ fontSize: 9, fontWeight: 600, color: T.textMeta,
    textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>{children}</div>
}

// ── Today screen (mobile) ─────────────────────────────────────────────────────
function MobileToday({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [snap,    setSnap]    = useState<any>(null)
  const [global,  setGlobal]  = useState<any>(null)
  const [signals, setSignals] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch("/api/market/snapshot").then(r => r.json()).catch(() => null),
      fetch("/api/market/global").then(r => r.json()).catch(() => null),
      fetch("/api/technical/screener?limit=5", { cache: "no-store" }).then(r => r.json()).catch(() => null),
    ]).then(([s, g, t]) => {
      setSnap(s?.data ?? s)
      setGlobal(g?.data ?? [])
      setSignals((t?.data ?? []).filter((x: any) => !/^(ANTELOP|ACUTAAS)/i.test(x.symbol || "")))
      setLoading(false)
    })
  }, [])

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "60vh", flexDirection: "column", gap: 12, color: T.textMeta }}>
      <div style={{ fontSize: 32 }}>⚡</div>
      <div style={{ fontSize: 13 }}>Loading market data…</div>
    </div>
  )

  const regime = snap?.regime ?? snap?.active_regime ?? "NORMAL"
  const regimeColor = regime === "HOT" ? T.red : regime === "NORMAL" ? T.teal : T.amber
  const nifty  = n(snap?.nifty_price ?? snap?.index_price)
  const vix    = n(snap?.vix)
  const pcr    = n(snap?.pcr)
  const fiiNet = n(snap?.fii_net ?? snap?.fii_buy_value)
  const diiNet = n(snap?.dii_net ?? snap?.dii_buy_value)
  const bankNifty = n(snap?.banknifty_price)

  return (
    <div style={{ padding: "12px 14px", paddingBottom: 80 }}>

      {/* Regime hero */}
      <MCard style={{ background: `${regimeColor}12`, border: `1px solid ${regimeColor}30`, padding: "16px" }}>
        <MLabel>Macro regime</MLabel>
        <div style={{ fontSize: 28, fontWeight: 800, color: regimeColor, marginBottom: 2 }}>{regime}</div>
        <div style={{ fontSize: 12, color: T.textSub }}>
          {regime === "HOT" ? "Risk-on · Deploy 80–100%" :
           regime === "NORMAL" ? "Deploy selectively · 50–70%" :
           "Be cautious · 20–40%"}
        </div>
      </MCard>

      {/* Market indices */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
        {[
          { label: "NIFTY 50",   value: nifty > 0 ? nifty.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—", color: T.text },
          { label: "BANK NIFTY", value: bankNifty > 0 ? bankNifty.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—", color: T.text },
          { label: "VIX",        value: vix > 0 ? vix.toFixed(2) : "—",  color: vix > 20 ? T.red : T.green },
          { label: "PCR",        value: pcr > 0 ? pcr.toFixed(2) : "—",  color: pcr > 1 ? T.green : T.red },
        ].map(c => (
          <MCard key={c.label} style={{ padding: "10px 12px", marginBottom: 0 }}>
            <MLabel>{c.label}</MLabel>
            <div style={{ fontSize: 20, fontWeight: 700, color: c.color }}>{c.value}</div>
          </MCard>
        ))}
      </div>

      {/* FII/DII flows */}
      <MCard>
        <MLabel>Institutional flows (today)</MLabel>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, color: T.textSub, marginBottom: 2 }}>FII</div>
            <div style={{ fontSize: 18, fontWeight: 700,
              color: fiiNet >= 0 ? T.green : T.red }}>
              {fiiNet >= 0 ? "+" : ""}₹{Math.abs(fiiNet).toLocaleString("en-IN", { maximumFractionDigits: 0 })}Cr
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: T.textSub, marginBottom: 2 }}>DII</div>
            <div style={{ fontSize: 18, fontWeight: 700,
              color: diiNet >= 0 ? T.green : T.red }}>
              {diiNet >= 0 ? "+" : ""}₹{Math.abs(diiNet).toLocaleString("en-IN", { maximumFractionDigits: 0 })}Cr
            </div>
          </div>
        </div>
      </MCard>

      {/* Top signals */}
      {signals.length > 0 && (
        <MCard>
          <MLabel>Top signals today</MLabel>
          {signals.slice(0, 5).map((s: any) => (
            <div key={s.symbol} onClick={() => onStockSelect(s.symbol)}
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 0", borderBottom: `1px solid ${T.border}`, cursor: "pointer" }}>
              <div>
                <span style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{s.symbol}</span>
                {(s.is_nr7 || s.daily_nr7) && (
                  <span style={{ fontSize: 9, background: "#F5F3FF", color: T.purple,
                    padding: "1px 6px", borderRadius: 20, marginLeft: 6, fontWeight: 600 }}>NR7</span>
                )}
                <div style={{ fontSize: 11, color: T.textSub }}>{s.company_name || s.symbol}</div>
              </div>
              <div style={{ fontSize: 20, fontWeight: 800,
                color: n(s.buy_zone_score) >= 70 ? T.green : n(s.buy_zone_score) >= 55 ? T.amber : T.textSub }}>
                {Math.round(n(s.buy_zone_score || s.convergence_score || 0))}
              </div>
            </div>
          ))}
        </MCard>
      )}

      {/* Global markets */}
      {Array.isArray(global) && global.length > 0 && (
        <MCard>
          <MLabel>Global markets</MLabel>
          {global.slice(0, 4).map((g: any) => (
            <div key={g.symbol || g.name} style={{ display: "flex", justifyContent: "space-between",
              padding: "6px 0", borderBottom: `1px solid ${T.border}`, fontSize: 12 }}>
              <span style={{ color: T.textSub }}>{g.name || g.symbol}</span>
              <span style={{ fontWeight: 600,
                color: n(g.change_pct ?? g.changePercent) >= 0 ? T.green : T.red }}>
                {n(g.change_pct ?? g.changePercent) >= 0 ? "+" : ""}{n(g.change_pct ?? g.changePercent).toFixed(2)}%
              </span>
            </div>
          ))}
        </MCard>
      )}
    </div>
  )
}

// ── Bottom nav ────────────────────────────────────────────────────────────────
const NAV_TABS = [
  { id: "today",     icon: "⚡", label: "Today"     },
  { id: "ipo",       icon: "⭐", label: "IPO"       },
  { id: "watchlist", icon: "👁", label: "Watch"     },
  { id: "portfolio", icon: "💼", label: "Portfolio" },
]

// ── Mobile App root ───────────────────────────────────────────────────────────
export function MobileApp() {
  const [tab,       setTab]       = useState("today")
  const [workspace, setWorkspace] = useState<string | null>(null)

  if (workspace) return (
    <StockResearchWorkspace symbol={workspace} onClose={() => setWorkspace(null)}/>
  )

  return (
    <div style={{ background: T.bg, minHeight: "100vh", maxWidth: 480, margin: "0 auto" }}>

      {/* Top header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "12px 16px", display: "flex", alignItems: "center",
        justifyContent: "space-between", position: "sticky", top: 0, zIndex: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, background: T.blue, borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, fontWeight: 700, color: "#fff" }}>AA</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>AACapital</div>
            <div style={{ fontSize: 9, color: T.textMeta }}>NSE/BSE Research</div>
          </div>
        </div>
        {/* Quick search */}
        <div onClick={() => {
          const sym = prompt("Enter symbol to look up:")
          if (sym) setWorkspace(sym.toUpperCase().trim())
        }} style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 20,
          padding: "6px 14px", fontSize: 12, color: T.textSub, cursor: "pointer" }}>
          🔍 Search…
        </div>
      </div>

      {/* Content */}
      <div style={{ paddingBottom: 70 }}>
        {tab === "today"     && <MobileToday onStockSelect={setWorkspace}/>}
        {tab === "ipo"       && <IpoCalendar/>}
        {tab === "watchlist" && <WatchlistScreen onStockSelect={setWorkspace}/>}
        {tab === "portfolio" && (
          <div style={{ padding: "20px 16px", textAlign: "center" as const, color: T.textSub }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>💼</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 6 }}>Portfolio</div>
            <div style={{ fontSize: 13 }}>Open on desktop for full portfolio view with P&L and convergence alerts</div>
          </div>
        )}
      </div>

      {/* Bottom nav */}
      <div style={{ position: "fixed", bottom: 0, left: "50%", transform: "translateX(-50%)",
        width: "100%", maxWidth: 480, background: T.surface,
        borderTop: `1px solid ${T.border}`, display: "flex",
        paddingBottom: "env(safe-area-inset-bottom, 8px)" }}>
        {NAV_TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ flex: 1, padding: "10px 0 8px", border: "none", background: "transparent",
              cursor: "pointer", display: "flex", flexDirection: "column",
              alignItems: "center", gap: 3 }}>
            <div style={{ fontSize: 20 }}>{t.icon}</div>
            <div style={{ fontSize: 10, fontWeight: tab === t.id ? 700 : 400,
              color: tab === t.id ? T.blue : T.textMeta }}>{t.label}</div>
            {tab === t.id && (
              <div style={{ width: 20, height: 2, background: T.blue, borderRadius: 1, marginTop: 1 }}/>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
