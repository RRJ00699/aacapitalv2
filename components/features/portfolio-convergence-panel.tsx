"use client"
// components/features/portfolio-convergence-panel.tsx
// Shows convergence alerts for each holding — EXIT/TRIM/ADD/HOLD
// Wired to /api/portfolio-alerts which reads Zerodha holdings + scores each against 6 engines

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Minus, Plus } from "lucide-react"

const T = {
  bg:"#F7F9FC", surface:"#FFFFFF", border:"#E5E7EB", border2:"#F1F5F9",
  text:"#0F172A", textSub:"#64748B", textMeta:"#94A3B8",
  green:"#16A34A", greenBg:"#F0FDF4", greenBd:"#BBF7D0",
  blue:"#2563EB",  blueBg:"#EFF6FF",  blueBd:"#BFDBFE",
  amber:"#D97706", amberBg:"#FFFBEB", amberBd:"#FDE68A",
  red:"#DC2626",   redBg:"#FEF2F2",   redBd:"#FECACA",
  purple:"#7C3AED",purpleBg:"#F5F3FF",
}

const ACTION_CFG = {
  EXIT:  { color: T.red,    bg: T.redBg,    bd: T.redBd,    icon: <TrendingDown size={14}/>, label: "Exit position"   },
  TRIM:  { color: T.amber,  bg: T.amberBg,  bd: T.amberBd,  icon: <Minus size={14}/>,        label: "Trim position"   },
  ADD:   { color: T.green,  bg: T.greenBg,  bd: T.greenBd,  icon: <Plus size={14}/>,          label: "Add to position" },
  HOLD:  { color: T.textSub,bg: T.bg,       bd: T.border,   icon: <Minus size={14}/>,         label: "Hold & monitor"  },
} as const

const URGENCY_CFG = {
  IMMEDIATE: { color: T.red,    label: "Act now"   },
  THIS_WEEK: { color: T.amber,  label: "This week" },
  MONITOR:   { color: T.textSub, label: "Monitor"  },
} as const

const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`
const fmtInr = (v: number) => `₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`

export function PortfolioConvergencePanel({ onStockSelect }: { onStockSelect?: (s: string) => void }) {
  const [alerts,  setAlerts]  = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await fetch("/api/portfolio-alerts", { cache: "no-store" })
      const d = await r.json()
      if (!r.ok) { setError(d.error ?? "Failed to load"); return }
      setAlerts(d.alerts ?? [])
      setSummary(d.summary ?? null)
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return (
    <div style={{ padding: "40px 0", textAlign: "center" as const, color: T.textMeta }}>
      <div style={{ fontSize: 24, marginBottom: 8 }}>💼</div>
      <div style={{ fontSize: 13 }}>Scoring your holdings against 6 engines…</div>
    </div>
  )

  if (error) return (
    <div style={{ padding: 16, background: T.redBg, borderRadius: 12,
      border: `1px solid ${T.redBd}`, fontSize: 13, color: T.red }}>
      {error.includes("Broker") || error.includes("401") || error.includes("connected")
        ? "🔗 Connect Zerodha in Settings → Portfolio to see convergence alerts for your holdings"
        : error}
    </div>
  )

  if (!alerts.length) return (
    <div style={{ padding: "40px 0", textAlign: "center" as const, color: T.textMeta }}>
      <div style={{ fontSize: 24, marginBottom: 8 }}>✅</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>No alerts — all holdings healthy</div>
      <div style={{ fontSize: 12, marginTop: 4 }}>Connect Zerodha in Settings to score your actual holdings</div>
    </div>
  )

  const exitCount = alerts.filter(a => a.action === "EXIT").length
  const trimCount = alerts.filter(a => a.action === "TRIM").length
  const addCount  = alerts.filter(a => a.action === "ADD").length

  return (
    <div>
      {/* Summary strip */}
      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 14 }}>
          {[
            { label: "Exit",  value: summary.exit  ?? exitCount,  color: T.red,    bg: T.redBg    },
            { label: "Trim",  value: summary.trim  ?? trimCount,  color: T.amber,  bg: T.amberBg  },
            { label: "Add",   value: summary.add   ?? addCount,   color: T.green,  bg: T.greenBg  },
            { label: "Hold",  value: summary.hold  ?? (alerts.length - exitCount - trimCount - addCount), color: T.textSub, bg: T.bg },
          ].map(c => (
            <div key={c.label} style={{ background: c.bg, borderRadius: 10,
              padding: "10px 12px", textAlign: "center" as const, border: `1px solid ${c.color}20` }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: c.color }}>{c.value}</div>
              <div style={{ fontSize: 10, color: T.textSub, fontWeight: 600, textTransform: "uppercase" as const }}>{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Alert cards */}
      {alerts.map((a: any) => {
        const cfg     = ACTION_CFG[a.action as keyof typeof ACTION_CFG] ?? ACTION_CFG.HOLD
        const urgCfg  = URGENCY_CFG[a.urgency as keyof typeof URGENCY_CFG] ?? URGENCY_CFG.MONITOR
        const isOpen  = expanded === a.symbol
        const conv    = n(a.convergence_score)
        const pnlPct  = n(a.pnl_pct)

        return (
          <div key={a.symbol} style={{ background: T.surface,
            border: `1px solid ${a.action === "EXIT" ? T.redBd : a.action === "TRIM" ? T.amberBd : T.border}`,
            borderLeft: `3px solid ${cfg.color}`,
            borderRadius: 14, marginBottom: 8, overflow: "hidden" }}>

            {/* Main row */}
            <div style={{ padding: "12px 14px", display: "flex", alignItems: "center", gap: 10,
              cursor: "pointer" }} onClick={() => setExpanded(isOpen ? null : a.symbol)}>

              {/* Action badge */}
              <div style={{ background: cfg.bg, border: `1px solid ${cfg.bd}`,
                color: cfg.color, borderRadius: 8, padding: "5px 10px",
                fontSize: 11, fontWeight: 800, display: "flex", alignItems: "center",
                gap: 5, flexShrink: 0 }}>
                {cfg.icon} {a.action}
              </div>

              {/* Stock info */}
              <div style={{ flex: 1, minWidth: 0, cursor: "pointer" }}
                onClick={(e) => { e.stopPropagation(); onStockSelect?.(a.symbol) }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: T.text }}>{a.symbol}</span>
                  <span style={{ fontSize: 10, color: urgCfg.color, fontWeight: 600 }}>
                    {urgCfg.label}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: T.textSub }}>
                  Conv {Math.round(conv)}/100 · P&L {fmtPct(pnlPct)}
                  {a.current_price > 0 && ` · ₹${n(a.current_price).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                </div>
              </div>

              {/* Convergence ring simple */}
              <div style={{ width: 36, height: 36, borderRadius: "50%",
                background: conv >= 70 ? T.greenBg : conv >= 50 ? T.amberBg : T.redBg,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0, border: `2px solid ${conv >= 70 ? T.green : conv >= 50 ? T.amber : T.red}` }}>
                <span style={{ fontSize: 10, fontWeight: 800,
                  color: conv >= 70 ? T.green : conv >= 50 ? T.amber : T.red }}>
                  {Math.round(conv)}
                </span>
              </div>
            </div>

            {/* Expanded reasons */}
            {isOpen && (
              <div style={{ padding: "0 14px 12px", borderTop: `1px solid ${T.border2}` }}>
                <div style={{ paddingTop: 10, marginBottom: 8 }}>
                  {(a.reasons ?? []).map((r: string, i: number) => (
                    <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5,
                      fontSize: 12, color: T.textSub }}>
                      <span style={{ color: cfg.color, flexShrink: 0 }}>→</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
                {(a.risk_flags ?? []).length > 0 && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" as const, marginTop: 6 }}>
                    {a.risk_flags.map((f: string) => (
                      <span key={f} style={{ fontSize: 10, padding: "2px 8px",
                        background: T.redBg, color: T.red, borderRadius: 20, fontWeight: 600 }}>
                        {f}
                      </span>
                    ))}
                  </div>
                )}
                {a.suggested_action && (
                  <div style={{ marginTop: 10, padding: "8px 12px",
                    background: cfg.bg, borderRadius: 8, fontSize: 12,
                    color: cfg.color, fontWeight: 600 }}>
                    💡 {a.suggested_action}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}

      <button onClick={load} style={{ display: "flex", alignItems: "center", gap: 6,
        margin: "4px auto 0", padding: "8px 16px", borderRadius: 8,
        border: `1px solid ${T.border}`, background: T.surface,
        fontSize: 12, color: T.textSub, cursor: "pointer" }}>
        <RefreshCw size={12}/> Refresh alerts
      </button>
    </div>
  )
}
