"use client"
// components/features/today-screen.tsx
// TODAY — The 30-second decision screen. V10 North Star.
// Answers: What matters right now?
// Decision first, scores second. Simple/Advanced aware.

import React, { useState, useEffect, useCallback } from "react"
// CommandCenter imported dynamically to avoid circular deps
import { RefreshCw, TrendingUp, AlertTriangle, ChevronRight, Droplets, Zap, Shield } from "lucide-react"

// ─── Design tokens ────────────────────────────────────────────────────────────
const C = {
  green:  "#16A34A", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  blue:   "#2563EB", blueBg:   "#EFF6FF", blueBd:  "#BFDBFE",
  amber:  "#D97706", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:    "#DC2626", redBg:    "#FEF2F2", redBd:   "#FECACA",
  purple: "#7C3AED", purpleBg: "#F5F3FF", purpleBd:"#E9D5FF",
  gray:   "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:   "#111827", textSub:  "#6B7280", surface:  "#FFFFFF",
  bg:     "#FAFAF8", border:   "#E5E7EB",
}

const REGIME: Record<string, { label: string; color: string; bg: string; bd: string; deploy: string; simple: string; pct: number }> = {
  HOT:     { label: "Hot market",    color: C.green,  bg: C.greenBg,  bd: C.greenBd,  deploy: "Deploy aggressively — all engines green",         simple: "Great time to invest",                       pct: 90 },
  NORMAL:  { label: "Normal market", color: C.blue,   bg: C.blueBg,   bd: C.blueBd,   deploy: "Deploy selectively — conviction ≥75 only",        simple: "Good time to invest selectively",             pct: 70 },
  CAUTION: { label: "Caution",       color: C.amber,  bg: C.amberBg,  bd: C.amberBd,  deploy: "Reduce size — conviction ≥80 required",           simple: "Be careful — only your strongest ideas",     pct: 40 },
  COLD:    { label: "Cold market",   color: C.blue,   bg: C.blueBg,   bd: C.blueBd,   deploy: "Max 40% deployment — wait for clarity",           simple: "Hold most cash, wait for better conditions",  pct: 20 },
  FROZEN:  { label: "Frozen market", color: C.gray,   bg: C.grayBg,   bd: C.grayBd,   deploy: "Hold cash — no new positions",                    simple: "Stay in cash — market not favourable",       pct: 0  },
}

const ACTION_CFG: Record<string, { color: string; bg: string; label: string }> = {
  ACCUMULATE: { color: C.green,  bg: C.greenBg,  label: "Accumulate" },
  TURNAROUND: { color: C.blue,   bg: C.blueBg,   label: "Turnaround" },
  WATCH:      { color: C.amber,  bg: C.amberBg,  label: "Watch"      },
  TRIM:       { color: C.amber,  bg: C.amberBg,  label: "Trim"       },
  AVOID:      { color: C.red,    bg: C.redBg,    label: "Avoid"      },
}

const AMFI_CFG: Record<string, { label: string; color: string; bg: string; deploy: string }> = {
  RISK_ON:           { label: "Risk On",    color: C.green,  bg: C.greenBg,  deploy: "Liquidity strong — deploy with confidence"     },
  SELECTIVE_RISK_ON: { label: "Selective",  color: C.blue,   bg: C.blueBg,   deploy: "Deploy selectively in high-conviction ideas"   },
  NEUTRAL:           { label: "Neutral",    color: C.gray,   bg: C.grayBg,   deploy: "Hold positions — wait for clearer direction"   },
  RISK_OFF:          { label: "Risk Off",   color: C.amber,  bg: C.amberBg,  deploy: "Reduce equity exposure — protect capital"      },
  OVERHEATED:        { label: "Overheated", color: C.red,    bg: C.redBg,    deploy: "Book partial profits — correction may follow"  },
}

const MONTH = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
const n = (v: unknown) => parseFloat(String(v || 0)) || 0

function deriveAction(eStatus: string, cStatus: string): string {
  if (["DECELERATING","WARNING"].includes(eStatus) || cStatus === "DETERIORATING") return "AVOID"
  if (eStatus === "TURNAROUND") return "TURNAROUND"
  if (eStatus === "ACCELERATING" && ["BULLISH","IMPROVING"].includes(cStatus)) return "ACCUMULATE"
  if (cStatus === "CAUTIOUS") return "TRIM"
  return "WATCH"
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface Idea { symbol: string; company_name: string; action: string; conviction: number; whyBuy: string[]; period?: string }
interface Alert { symbol: string; action: "EXIT"|"TRIM"|"ADD"|"HOLD"; reason: string }
interface AmfiData { liquidity_status: string; report_month: number; report_year: number; total_score: unknown }
interface IpoAlert { name: string; recommendation: string; score?: number }

// ─── Section wrapper ──────────────────────────────────────────────────────────
function Section({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        {icon}
        <span style={{ fontSize: 10, fontWeight: 700, color: C.textSub, textTransform: "uppercase" as const, letterSpacing: ".07em" }}>{title}</span>
      </div>
      {children}
    </div>
  )
}

function Bone({ h = 72 }: { h?: number }) {
  return <div style={{ background: C.grayBg, borderRadius: 12, height: h, marginBottom: 8 }} />
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export function TodayScreen({ simple = false, onStockSelect, commandCenter }: { simple?: boolean; onStockSelect?: (s: string) => void; commandCenter?: React.ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [regime, setRegime] = useState("NORMAL")
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [amfi, setAmfi] = useState<AmfiData | null>(null)
  const [ipos, setIpos] = useState<IpoAlert[]>([])
  const [ts, setTs] = useState<Date | null>(null)

  const load = useCallback(async (quiet = false) => {
    quiet ? setRefreshing(true) : setLoading(true)
    try {
      const [dash, amfiR, ipoR, mktR] = await Promise.all([
        fetch("/api/intelligence/dashboard").then(r => r.json()).catch(() => null),
        fetch("/api/intelligence/amfi").then(r => r.json()).catch(() => null),
        fetch("/api/ipo?limit=3").then(r => r.json()).catch(() => null),
        fetch("/api/market/snapshot").then(r => r.json()).catch(() => null),
      ])

      if (mktR?.ok || mktR?.data) setRegime(mktR?.data?.regime || "NORMAL")

      if (dash?.success) {
        const earnings = (dash.data?.top_earnings || []) as any[]
        const commentary = (dash.data?.top_commentary || []) as any[]
        const cMap = new Map(commentary.map((c: any) => [c.symbol, c]))

        const merged: Idea[] = earnings.map((e: any) => {
          const c = cMap.get(e.symbol) as any
          const action = deriveAction(e.acceleration_status, c?.commentary_status || "NEUTRAL")
          const whyBuy: string[] = []
          if (n(e.revenue_acceleration_score) > 20) whyBuy.push("Revenue accelerating")
          if (n(e.pat_acceleration_score) > 20) whyBuy.push("Profit momentum strong")
          if (n(e.margin_expansion_score) > 10) whyBuy.push("Margins expanding")
          if (n(e.consistency_score) > 20) whyBuy.push("Consistent execution")
          if (c && ["BULLISH","IMPROVING"].includes(c.commentary_status)) whyBuy.push("Management confident")
          if (c && n(c.order_book_score) > 20) whyBuy.push("Strong order book")
          const es = n(e.total_score); const cs = n(c?.total_score)
          const conviction = c ? (es + cs) / 2 : es
          return {
            symbol: e.symbol, company_name: e.company_name, action, conviction, whyBuy,
            period: e.fiscal_quarter ? `${e.fiscal_quarter} FY${String(e.fiscal_year).slice(-2)}` : undefined,
          }
        }).filter((s: Idea) => ["ACCUMULATE","TURNAROUND"].includes(s.action))
          .sort((a: Idea, b: Idea) => b.conviction - a.conviction).slice(0, 5)

        setIdeas(merged)

        const alertMap = new Map<string, Alert>()
        ;(dash.data?.warning_earnings || []).slice(0, 3).forEach((w: any) => {
          alertMap.set(w.symbol, { symbol: w.symbol, action: w.acceleration_status === "WARNING" ? "EXIT" : "TRIM", reason: `Earnings ${w.acceleration_status.toLowerCase()} — review position` })
        })
        ;(dash.data?.cautious_commentary || []).slice(0, 2).forEach((c: any) => {
          if (!alertMap.has(c.symbol)) alertMap.set(c.symbol, { symbol: c.symbol, action: "TRIM", reason: `Management tone ${c.commentary_status.toLowerCase()} — consider reducing` })
        })
        setAlerts(Array.from(alertMap.values()).slice(0, 4))
      }

      if (amfiR?.success) setAmfi(amfiR.data?.score || null)

      if (ipoR?.ipos) {
        setIpos((ipoR.ipos as any[]).filter((i: any) => ["OPEN","UPCOMING"].includes(i.status)).slice(0, 2).map((i: any) => ({
          name: i.name, recommendation: i.score?.recommendation || "Watch", score: i.score?.listingScore,
        })))
      }

      setTs(new Date())
    } catch { /* silent */ }
    finally { setLoading(false); setRefreshing(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const rc = REGIME[regime] || REGIME.NORMAL
  const now = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", timeZone: "Asia/Kolkata" })

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>{now}</div>
            <div style={{ fontSize: 11, color: C.textSub }}>{ts ? `Updated ${ts.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : "Loading…"}</div>
          </div>
          <button onClick={() => load(true)} disabled={refreshing}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "7px 12px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, fontSize: 12, color: C.textSub, cursor: "pointer" }}>
            <RefreshCw size={12} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {/* Regime */}
        <Section title="Market regime" icon={<Shield size={12} color={C.textSub} />}>
          {loading ? <Bone /> : (
            <div style={{ background: rc.bg, border: `1px solid ${rc.bd}`, borderRadius: 14, padding: "14px 16px", marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: rc.color, textTransform: "uppercase" as const, letterSpacing: ".06em", marginBottom: 3 }}>Market regime</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: rc.color, marginBottom: 4 }}>{rc.label}</div>
                  <div style={{ fontSize: 12, color: rc.color, opacity: .85 }}>{simple ? rc.simple : rc.deploy}</div>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 16 }}>
                  <div style={{ fontSize: 10, color: rc.color, opacity: .7, marginBottom: 2 }}>Deploy</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: rc.color }}>{rc.pct}%</div>
                  <div style={{ fontSize: 10, color: rc.color, opacity: .7 }}>of capital</div>
                </div>
              </div>
            </div>
          )}
        </Section>

        {/* AMFI */}
        {(amfi || loading) && (
          <Section title="Liquidity signal" icon={<Droplets size={12} color={C.textSub} />}>
            {loading ? <Bone h={44} /> : amfi ? (() => {
              const a = AMFI_CFG[amfi.liquidity_status] || AMFI_CFG.NEUTRAL
              return (
                <div style={{ background: a.bg, border: `1px solid ${a.color}30`, borderRadius: 10, padding: "10px 14px", display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <Droplets size={14} color={a.color} />
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: a.color }}>AMFI {a.label}</span>
                    <span style={{ fontSize: 11, color: a.color, opacity: .7, marginLeft: 6 }}>{MONTH[amfi.report_month]} {amfi.report_year}</span>
                    {simple && <div style={{ fontSize: 11, color: a.color, opacity: .8, marginTop: 2 }}>{a.deploy}</div>}
                  </div>
                  {!simple && <div style={{ fontSize: 11, color: a.color, opacity: .8 }}>Score: {Math.round(n(amfi.total_score))}</div>}
                </div>
              )
            })() : null}
          </Section>
        )}

        {/* Top ideas */}
        <Section title={simple ? "Best stocks right now" : "Top conviction ideas"} icon={<TrendingUp size={12} color={C.textSub} />}>
          {loading ? [1,2,3].map(i => <Bone key={i} />) :
            ideas.length === 0 ? (
              <div style={{ background: C.grayBg, borderRadius: 10, padding: "20px", textAlign: "center", fontSize: 12, color: C.textSub }}>
                No high-conviction ideas at the moment — intelligence scoring runs daily at 6:30 AM IST
              </div>
            ) : ideas.map(idea => {
              const ac = ACTION_CFG[idea.action] || ACTION_CFG.WATCH
              return (
                <div key={idea.symbol} onClick={() => onStockSelect?.(idea.symbol)}
                  style={{ background: C.surface, border: `1px solid ${C.border}`, borderLeft: `3px solid ${ac.color}`, borderRadius: 12, padding: "12px 14px", marginBottom: 8, cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: ac.bg, color: ac.color }}>{ac.label}</span>
                      <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{idea.symbol}</span>
                      {!simple && idea.period && <span style={{ fontSize: 10, color: C.textSub }}>{idea.period}</span>}
                    </div>
                    <div style={{ fontSize: 11, color: C.textSub }}>
                      {simple ? idea.whyBuy.slice(0,2).join(" · ") || idea.company_name : idea.company_name}
                    </div>
                    {!simple && idea.whyBuy.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        {idea.whyBuy.slice(0,2).map(r => (
                          <div key={r} style={{ fontSize: 11, color: C.green, display: "flex", gap: 4 }}>
                            <span>✓</span> {r}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: ac.color }}>{Math.round(idea.conviction)}</div>
                    <div style={{ fontSize: 9, color: C.textSub }}>conviction</div>
                  </div>
                  <ChevronRight size={14} color={C.textSub} />
                </div>
              )
            })
          }
        </Section>

        {/* Portfolio alerts */}
        {alerts.length > 0 && (
          <Section title={simple ? "Holdings needing attention" : "Portfolio alerts"} icon={<AlertTriangle size={12} color={C.amber} />}>
            {alerts.map(a => {
              const colors2: Record<string,string> = { EXIT: C.red, TRIM: C.amber, ADD: C.green, HOLD: C.gray }
              const bgs: Record<string,string> = { EXIT: C.redBg, TRIM: C.amberBg, ADD: C.greenBg, HOLD: C.grayBg }
              const ac = colors2[a.action] || C.gray
              return (
                <div key={a.symbol} onClick={() => onStockSelect?.(a.symbol)}
                  style={{ background: bgs[a.action] || C.grayBg, border: `1px solid ${ac}30`, borderRadius: 10, padding: "10px 14px", marginBottom: 6, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: ac, background: ac + "20", padding: "2px 8px", borderRadius: 4 }}>{a.action}</span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{a.symbol}</span>
                    </div>
                    <div style={{ fontSize: 11, color: C.textSub, marginTop: 2 }}>{a.reason}</div>
                  </div>
                  <ChevronRight size={14} color={C.textSub} />
                </div>
              )
            })}
          </Section>
        )}

        {/* IPO */}
        <Section title="IPO this week" icon={<Zap size={12} color={C.purple} />}>
          {loading ? <Bone h={44} /> :
            ipos.length === 0 ? (
              <div style={{ background: C.grayBg, borderRadius: 10, padding: "12px 14px", fontSize: 12, color: C.textSub }}>
                No open IPO this week — check back next week
              </div>
            ) : ipos.map(ipo => {
              const isApply = ipo.recommendation?.toLowerCase().includes("apply")
              const isAvoid = ipo.recommendation?.toLowerCase().includes("avoid")
              const color = isApply ? C.purple : isAvoid ? C.red : C.amber
              const bg = isApply ? C.purpleBg : isAvoid ? C.redBg : C.amberBg
              return (
                <div key={ipo.name} style={{ background: bg, border: `1px solid ${color}30`, borderRadius: 10, padding: "10px 14px", marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Zap size={12} color={color} />
                      <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{ipo.name}</span>
                    </div>
                    <div style={{ fontSize: 11, color, marginTop: 2 }}>{ipo.recommendation}</div>
                  </div>
                  {ipo.score && <div style={{ fontSize: 18, fontWeight: 800, color }}>{ipo.score}</div>}
                </div>
              )
            })
          }
        </Section>

        <div style={{ textAlign: "center", fontSize: 10, color: "#D1D5DB", margin: "8px 0 16px" }}>
          Intelligence refreshes daily at 6:30 AM IST · AMFI updates monthly
        </div>
      </div>
    </div>
  )
}


