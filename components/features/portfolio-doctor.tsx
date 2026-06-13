"use client"
// components/features/portfolio-doctor.tsx
// PORTFOLIO DOCTOR — Transform portfolio from data display into decision engine
// V10: Answers "What should I do with my holdings?" with ADD/TRIM/EXIT/WATCH
// Shows opportunity cost: "If you move ₹X from A→B, CAGR goes 18%→24%"

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, TrendingUp, TrendingDown, AlertTriangle, ArrowRight, ChevronDown, ChevronUp } from "lucide-react"

const C = {
  green:  "#16A34A", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  blue:   "#2563EB", blueBg:   "#EFF6FF", blueBd:  "#BFDBFE",
  amber:  "#D97706", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:    "#DC2626", redBg:    "#FEF2F2", redBd:   "#FECACA",
  purple: "#7C3AED", purpleBg: "#F5F3FF",
  gray:   "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:   "#111827", textSub:  "#6B7280", surface:  "#FFFFFF", bg: "#FAFAF8", border: "#E5E7EB",
}

const ACTION_CFG: Record<string, { color: string; bg: string; bd: string; label: string; simple: string }> = {
  ADD:   { color: C.green,  bg: C.greenBg,  bd: C.greenBd,  label: "Add more",  simple: "Add more of this"    },
  TRIM:  { color: C.amber,  bg: C.amberBg,  bd: C.amberBd,  label: "Trim",      simple: "Sell some of this"   },
  EXIT:  { color: C.red,    bg: C.redBg,    bd: C.redBd,    label: "Exit",      simple: "Sell all of this"    },
  WATCH: { color: C.gray,   bg: C.grayBg,   bd: C.grayBd,   label: "Watch",     simple: "Hold and monitor"    },
}

const URGENCY_CFG: Record<string, { color: string; label: string }> = {
  IMMEDIATE:  { color: C.red,   label: "Act now"     },
  THIS_WEEK:  { color: C.amber, label: "This week"   },
  MONITOR:    { color: C.gray,  label: "Monitor"     },
}

const n = (v: unknown) => parseFloat(String(v || 0)) || 0
const fmtInr = (v: number) => `₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`
const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`

interface HoldingAlert {
  symbol: string
  company_name?: string
  action: "ADD" | "TRIM" | "EXIT" | "WATCH"
  urgency: "IMMEDIATE" | "THIS_WEEK" | "MONITOR"
  current_value?: number
  pnl_pct?: number
  reasons: string[]
  risk_flags?: string[]
  confidence?: string
  // Opportunity cost
  opp_symbol?: string
  opp_name?: string
  current_cagr?: number
  potential_cagr?: number
  opp_amount?: number
}

// ─── Summary cards ────────────────────────────────────────────────────────────
function SummaryBar({ alerts }: { alerts: HoldingAlert[] }) {
  const counts = { ADD: 0, TRIM: 0, EXIT: 0, WATCH: 0 }
  alerts.forEach(a => { counts[a.action] = (counts[a.action] || 0) + 1 })

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 16 }}>
      {(["ADD","TRIM","EXIT","WATCH"] as const).map(action => {
        const ac = ACTION_CFG[action]
        return (
          <div key={action} style={{ background: ac.bg, border: `1px solid ${ac.bd}`, borderRadius: 10, padding: "10px 12px", textAlign: "center" }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: ac.color }}>{counts[action]}</div>
            <div style={{ fontSize: 10, color: ac.color, fontWeight: 600 }}>{ac.label}</div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Opportunity cost panel ───────────────────────────────────────────────────
function OpportunityCost({ alert, simple }: { alert: HoldingAlert; simple: boolean }) {
  if (!alert.opp_symbol || !alert.current_cagr || !alert.potential_cagr) return null
  const gain = alert.potential_cagr - alert.current_cagr
  if (gain < 2) return null

  const yearsOut = 5
  const amount = alert.opp_amount || 100000
  const currentWealth = amount * Math.pow(1 + alert.current_cagr / 100, yearsOut)
  const potentialWealth = amount * Math.pow(1 + alert.potential_cagr / 100, yearsOut)

  return (
    <div style={{ background: C.purpleBg, border: `1px solid #E9D5FF`, borderRadius: 8, padding: "10px 12px", marginTop: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: C.purple, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 6 }}>
        {simple ? "What if you switched?" : "Opportunity cost"}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: C.textSub }}>{alert.symbol}</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.text }}>{alert.current_cagr}% CAGR</div>
        </div>
        <ArrowRight size={16} color={C.purple} />
        <div style={{ flex: 1, textAlign: "right" as const }}>
          <div style={{ fontSize: 11, color: C.textSub }}>{alert.opp_symbol}</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.green }}>{alert.potential_cagr}% CAGR</div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: C.textSub }}>
        {simple
          ? `In 5 years: ${fmtInr(currentWealth)} → ${fmtInr(potentialWealth)} (+${fmtInr(potentialWealth - currentWealth)})`
          : `${fmtInr(amount)} over ${yearsOut}yr: ${fmtInr(currentWealth)} → ${fmtInr(potentialWealth)} (Δ${fmtInr(potentialWealth - currentWealth)})`
        }
      </div>
    </div>
  )
}

// ─── Holding card ─────────────────────────────────────────────────────────────
function HoldingCard({ alert, simple, expanded, onToggle, onSelect }: {
  alert: HoldingAlert; simple: boolean; expanded: boolean;
  onToggle: () => void; onSelect?: (s: string) => void
}) {
  const ac = ACTION_CFG[alert.action]
  const ug = URGENCY_CFG[alert.urgency]
  const pnl = n(alert.pnl_pct)

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderLeft: `3px solid ${ac.color}`, borderRadius: 12, marginBottom: 8, overflow: "hidden" }}>

      {/* Header */}
      <div onClick={onToggle} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>

        {/* Action */}
        <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 4, background: ac.bg, color: ac.color, whiteSpace: "nowrap" as const, flexShrink: 0 }}>
          {simple ? ac.simple : ac.label}
        </span>

        {/* Symbol */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{alert.symbol}</div>
          {!simple && alert.company_name && (
            <div style={{ fontSize: 11, color: C.textSub }}>{alert.company_name}</div>
          )}
        </div>

        {/* P&L + urgency */}
        <div style={{ textAlign: "right" as const, flexShrink: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: pnl >= 0 ? C.green : C.red }}>{fmtPct(pnl)}</div>
          {!simple && (
            <div style={{ fontSize: 9, color: ug.color, fontWeight: 600 }}>{ug.label}</div>
          )}
        </div>

        {expanded ? <ChevronUp size={14} color={C.textSub} /> : <ChevronDown size={14} color={C.textSub} />}
      </div>

      {/* Expanded */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}`, background: "#FAFAF8", padding: "12px 14px" }}>

          {/* Reasons */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 6 }}>
              {simple ? "Why?" : "Reason"}
            </div>
            {alert.reasons.map((r, i) => (
              <div key={i} style={{ fontSize: 12, color: C.text, display: "flex", gap: 6, marginBottom: 3 }}>
                <span style={{ color: ac.color }}>•</span> {r}
              </div>
            ))}
          </div>

          {/* Risk flags */}
          {alert.risk_flags && alert.risk_flags.length > 0 && (
            <div style={{ background: C.redBg, borderRadius: 6, padding: "6px 10px", marginBottom: 8 }}>
              {alert.risk_flags.map((f, i) => (
                <div key={i} style={{ fontSize: 11, color: C.red, display: "flex", gap: 5 }}>
                  <AlertTriangle size={11} style={{ flexShrink: 0, marginTop: 1 }} /> {f}
                </div>
              ))}
            </div>
          )}

          {/* Confidence */}
          {!simple && alert.confidence && (
            <div style={{ fontSize: 11, color: C.textSub, marginBottom: 8 }}>
              Confidence: <span style={{ fontWeight: 600, color: C.text }}>{alert.confidence}</span>
            </div>
          )}

          {/* Opportunity cost */}
          <OpportunityCost alert={alert} simple={simple} />

          {/* Current value */}
          {alert.current_value && (
            <div style={{ fontSize: 11, color: C.textSub, marginTop: 8 }}>
              Position value: <span style={{ fontWeight: 600, color: C.text }}>{fmtInr(alert.current_value)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── No broker state ──────────────────────────────────────────────────────────
function NoBroker() {
  return (
    <div style={{ maxWidth: 400, margin: "60px auto", textAlign: "center", padding: 16 }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>🔌</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: C.red, marginBottom: 8 }}>Portfolio not connected</div>
      <div style={{ fontSize: 12, color: C.textSub, marginBottom: 20, lineHeight: 1.6 }}>
        Connect Zerodha to see ADD / TRIM / EXIT / WATCH recommendations for your actual holdings.
      </div>
      <a href="/api/auth/zerodha"
        style={{ display: "inline-block", padding: "10px 24px", background: "#FF6600", borderRadius: 8, color: "#fff", fontSize: 13, fontWeight: 700, textDecoration: "none" }}>
        Connect Zerodha →
      </a>
      <div style={{ marginTop: 16, fontSize: 11, color: C.textSub }}>
        Or view sample analysis below ↓
      </div>
    </div>
  )
}

// ─── Sample data (when no broker connected) ───────────────────────────────────
function getSampleAlerts(): HoldingAlert[] {
  return [
    {
      symbol: "WABAG", company_name: "VA Tech Wabag",
      action: "ADD", urgency: "THIS_WEEK",
      current_value: 250000, pnl_pct: 34,
      reasons: ["Earnings accelerating for 3 consecutive quarters", "Order book coverage strong at 2.4x revenue", "Management confidence high — bullish commentary"],
      confidence: "High",
      opp_symbol: undefined, current_cagr: 22, potential_cagr: 22,
    },
    {
      symbol: "KAYNES", company_name: "Kaynes Technology",
      action: "TRIM", urgency: "THIS_WEEK",
      current_value: 180000, pnl_pct: 68,
      reasons: ["Position now 18% of portfolio — overweight", "Valuation stretched at current levels", "Take partial profits — retain core position"],
      risk_flags: ["Concentration risk — largest position"],
      confidence: "High",
      opp_symbol: "NETWEB", opp_name: "Netweb Technologies",
      current_cagr: 18, potential_cagr: 24, opp_amount: 90000,
    },
    {
      symbol: "MTARTECH", company_name: "MTAR Technologies",
      action: "EXIT", urgency: "IMMEDIATE",
      current_value: 95000, pnl_pct: -12,
      reasons: ["Earnings decelerating for 2 quarters", "Management guidance cut in latest concall", "Stop loss level breached"],
      risk_flags: ["Revenue declining QoQ", "Guidance revised downward"],
      confidence: "High",
    },
    {
      symbol: "DIXON", company_name: "Dixon Technologies",
      action: "WATCH", urgency: "MONITOR",
      current_value: 120000, pnl_pct: 14,
      reasons: ["Earnings stable — not accelerating strongly", "Commentary neutral — no strong catalysts", "Hold current position, monitor next quarter results"],
      confidence: "Medium",
    },
  ]
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export function PortfolioDoctor({ simple = false, onStockSelect }: { simple?: boolean; onStockSelect?: (s: string) => void }) {
  const [loading, setLoading] = useState(true)
  const [alerts, setAlerts] = useState<HoldingAlert[]>([])
  const [brokerConnected, setBrokerConnected] = useState(false)
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)
  const [filterAction, setFilterAction] = useState<string>("all")
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [usingSample, setUsingSample] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // Try portfolio alerts API first
      const res = await fetch("/api/portfolio-alerts").then(r => r.json()).catch(() => null)

      if (res?.ok && Array.isArray(res.alerts) && res.alerts.length > 0) {
        setBrokerConnected(true)
        setAlerts(res.alerts.map((a: any) => ({
          symbol: a.symbol,
          company_name: a.company_name,
          action: a.action,
          urgency: a.urgency || "MONITOR",
          current_value: a.current_value,
          pnl_pct: a.pnl_pct,
          reasons: Array.isArray(a.reasons) ? a.reasons : [a.suggested_action || "Review position"],
          risk_flags: a.risk_flags || [],
          confidence: a.confidence_level || "Medium",
        })))
        setUsingSample(false)
      } else {
        // Use intelligence-derived alerts + sample
        const dashRes = await fetch("/api/intelligence/dashboard").then(r => r.json()).catch(() => null)
        if (dashRes?.success) {
          const warnings = dashRes.data?.warning_earnings || []
          const cautious = dashRes.data?.cautious_commentary || []
          const derived: HoldingAlert[] = [
            ...warnings.slice(0,3).map((w: any) => ({
              symbol: w.symbol, company_name: w.company_name,
              action: w.acceleration_status === "WARNING" ? "EXIT" as const : "TRIM" as const,
              urgency: w.acceleration_status === "WARNING" ? "IMMEDIATE" as const : "THIS_WEEK" as const,
              pnl_pct: 0,
              reasons: [`Earnings ${w.acceleration_status.toLowerCase()}`, "Review your position in this stock"],
              confidence: "Medium",
            })),
            ...cautious.slice(0,2).map((c: any) => ({
              symbol: c.symbol, company_name: c.company_name,
              action: "TRIM" as const, urgency: "THIS_WEEK" as const,
              pnl_pct: 0,
              reasons: [`Management commentary ${c.commentary_status.toLowerCase()}`, "Consider reducing position size"],
              confidence: "Medium",
            })),
          ]
          if (derived.length > 0) {
            setAlerts(derived)
            setUsingSample(false)
          } else {
            setAlerts(getSampleAlerts())
            setUsingSample(true)
          }
        } else {
          setAlerts(getSampleAlerts())
          setUsingSample(true)
        }
      }
      setLastUpdate(new Date())
    } catch {
      setAlerts(getSampleAlerts())
      setUsingSample(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = alerts.filter(a => filterAction === "all" || a.action === filterAction)
  const sortOrder = { EXIT: 0, TRIM: 1, ADD: 2, WATCH: 3 }
  const sorted = [...filtered].sort((a, b) => (sortOrder[a.action] || 0) - (sortOrder[b.action] || 0))

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>
              {simple ? "My portfolio check" : "Portfolio doctor"}
            </div>
            <div style={{ fontSize: 11, color: C.textSub }}>
              {usingSample ? "Sample analysis — connect Zerodha for your actual portfolio" :
                lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : "Loading…"}
            </div>
          </div>
          <button onClick={() => load()}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "7px 12px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, fontSize: 12, color: C.textSub, cursor: "pointer" }}>
            <RefreshCw size={12} /> Refresh
          </button>
        </div>

        {usingSample && (
          <div style={{ background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: 8, padding: "8px 12px", marginBottom: 12, fontSize: 12, color: C.amber }}>
            Showing sample analysis. {" "}
            <a href="/api/auth/zerodha" style={{ color: C.amber, fontWeight: 600 }}>Connect Zerodha</a>
            {" "}for real recommendations on your actual holdings.
          </div>
        )}

        {loading ? (
          [1,2,3,4].map(i => <div key={i} style={{ background: C.grayBg, borderRadius: 12, height: 72, marginBottom: 8 }} />)
        ) : (
          <>
            <SummaryBar alerts={alerts} />

            {/* Filter pills */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              {["all","EXIT","TRIM","ADD","WATCH"].map(f => {
                const ac = f === "all" ? { color: C.gray, bg: C.grayBg } : ACTION_CFG[f]
                const label = f === "all" ? "All" : simple ? ACTION_CFG[f]?.simple || f : ACTION_CFG[f]?.label || f
                return (
                  <button key={f} onClick={() => setFilterAction(f)}
                    style={{ fontSize: 11, padding: "4px 12px", borderRadius: 16,
                      border: filterAction === f ? `1.5px solid ${ac.color}` : `0.5px solid ${C.border}`,
                      background: filterAction === f ? ac.bg : "transparent",
                      color: filterAction === f ? ac.color : C.textSub, cursor: "pointer" }}>
                    {label}
                  </button>
                )
              })}
            </div>

            {sorted.length === 0 ? (
              <div style={{ padding: "32px 0", textAlign: "center", color: C.textSub, fontSize: 14 }}>
                No alerts in this category
              </div>
            ) : sorted.map(alert => (
              <HoldingCard
                key={alert.symbol} alert={alert} simple={simple}
                expanded={expandedSymbol === alert.symbol}
                onToggle={() => setExpandedSymbol(expandedSymbol === alert.symbol ? null : alert.symbol)}
                onSelect={onStockSelect}
              />
            ))}
          </>
        )}
      </div>
    </div>
  )
}
