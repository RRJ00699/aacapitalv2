"use client"
// components/features/sprint8-features.tsx
// Sprint 8: Multibagger Discovery Engine + Trade Journal + Capital Deployment Optimizer
// Three panels, one import

import { useState, useEffect, useCallback } from "react"
import { colors } from "@/lib/design/tokens"

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────
interface DiscoveryCandidate {
  tradingsymbol: string
  current_price: number
  dna_score: number
  predicted_tier: string
  base_months: number
  vol_compression: number
  momentum_6m: number
  momentum_12m: number
  pct_below_high: number
  is_nr7: boolean
  signals: string[]
  warnings: string[]
  latest_date: string
}

interface ConvergenceResult {
  tradingsymbol: string
  convergence_score: number
  engines_triggered: number
  alert_tier: string
  engine_scores: Record<string, number>
  signals: string[]
  current_price: number
}

interface BehavioralAnalysis {
  win_rate: number
  avg_hold_days: number
  biggest_bias: string
  pattern_summary: string
  top_mistakes: string[]
  strengths: string[]
  recommendations: string[]
  risk_score: number
  behavior_type: string
  consistency_score: number
}

interface DeploymentAllocation {
  category: string
  pct_of_available: number
  amount: number
  reasoning: string
  specific_action: string
}

interface DeploymentPlan {
  regime_assessment: string
  deployment_mode: string
  cash_to_deploy_pct: number
  cash_to_hold_pct: number
  allocations: DeploymentAllocation[]
  top_action: string
  risk_warning: string | null
  expected_cagr_range: string
  review_trigger: string
}

// ─────────────────────────────────────────────────────────────────────────────
// SHARED HELPERS
// ─────────────────────────────────────────────────────────────────────────────
const TIER_COLOR: Record<string, string> = {
  "10x_candidate": "#7c3aed",
  "5x_candidate":  "#2563EB",
  "3x_candidate":  "#16A34A",
  "2x_candidate":  "#D97706",
  "1x_candidate":  "#6b7280",
  "watch":         "#9CA3AF",
}

const TIER_LABEL: Record<string, string> = {
  "10x_candidate": "10x",
  "5x_candidate":  "5x",
  "3x_candidate":  "3x",
  "2x_candidate":  "2x",
  "1x_candidate":  "1x",
  "watch":         "Watch",
}

function Card({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: 14,
      padding: "16px", boxShadow: "0 1px 6px rgba(0,0,0,0.04)", ...style }}>
      {children}
    </div>
  )
}

function LoadingState({ label }: { label: string }) {
  return (
    <div style={{ textAlign: "center", padding: "60px 0", color: "#9CA3AF" }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
      <div style={{ fontSize: 14 }}>{label}</div>
    </div>
  )
}

function ScoreRing({ score, color }: { score: number; color: string }) {
  return (
    <div style={{ width: 52, height: 52, borderRadius: "50%",
      background: `conic-gradient(${color} ${score}%, #F3F4F6 0%)`,
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
      <div style={{ width: 38, height: 38, borderRadius: "50%", background: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 12, fontWeight: 800, color }}>
        {score}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. MULTIBAGGER DISCOVERY ENGINE
// ─────────────────────────────────────────────────────────────────────────────
export function MultibaggerDiscoveryEngine() {
  const [candidates, setCandidates]   = useState<DiscoveryCandidate[]>([])
  const [convergence, setConvergence] = useState<ConvergenceResult[]>([])
  const [summary, setSummary]         = useState<Record<string, number> | null>(null)
  const [loading, setLoading]         = useState(true)
  const [convLoading, setConvLoading] = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [view, setView]               = useState<"discovery" | "convergence">("discovery")

  const fetchDiscovery = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await fetch("/api/multibagger-discovery?limit=30&min_score=40")
      const d = await r.json()
      if (!d.ok) throw new Error(d.error)
      setCandidates(d.data)
      setSummary(d.summary)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed")
    } finally { setLoading(false) }
  }, [])

  const runConvergence = useCallback(async () => {
    setConvLoading(true)
    try {
      const r = await fetch("/api/convergence-score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ top_n: 15 }),
      })
      const d = await r.json()
      if (!d.ok) throw new Error(d.error)
      setConvergence(d.data ?? [])
    } catch { /* silent */ }
    finally { setConvLoading(false) }
  }, [])

  useEffect(() => { fetchDiscovery() }, [fetchDiscovery])

  return (
    <div style={{ background: colors.background, minHeight: "100vh", paddingBottom: 80 }}>
      {/* Header */}
      <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB",
        padding: "20px 20px 0", position: "sticky", top: 0, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start",
          marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: colors.textPrimary,
              letterSpacing: "-0.4px" }}>Multibagger Discovery</div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
              Stocks matching historical 2x–10x DNA patterns
            </div>
          </div>
          <button onClick={fetchDiscovery} disabled={loading}
            style={{ background: "#EFF6FF", color: colors.blue, border: "1px solid #BFDBFE",
              borderRadius: 10, padding: "8px 14px", fontSize: 12, fontWeight: 600,
              cursor: "pointer" }}>
            {loading ? "…" : "↻"}
          </button>
        </div>

        {/* Summary pills */}
        {summary && (
          <div style={{ display: "flex", gap: 6, overflowX: "auto",
            paddingBottom: 4, scrollbarWidth: "none" as const, marginBottom: 10 }}>
            {[
              { label: "10x", key: "tier_10x", color: "#7c3aed" },
              { label: "5x",  key: "tier_5x",  color: "#2563EB" },
              { label: "3x",  key: "tier_3x",  color: "#16A34A" },
              { label: "2x",  key: "tier_2x",  color: "#D97706" },
              { label: "1x",  key: "tier_1x",  color: "#6b7280" },
            ].map(({ label, key, color }) => (
              <div key={key} style={{ background: color + "12", border: `1px solid ${color}30`,
                borderRadius: 8, padding: "4px 10px", whiteSpace: "nowrap" as const }}>
                <span style={{ fontSize: 12, fontWeight: 700, color }}>{summary[key] ?? 0}</span>
                <span style={{ fontSize: 10, color, marginLeft: 3 }}>{label}</span>
              </div>
            ))}
          </div>
        )}

        {/* View tabs */}
        <div style={{ display: "flex", borderTop: "1px solid #E5E7EB" }}>
          {[
            { key: "discovery",   label: "DNA Candidates" },
            { key: "convergence", label: "⚡ Convergence Score" },
          ].map(t => (
            <button key={t.key} onClick={() => {
              setView(t.key as "discovery" | "convergence")
              if (t.key === "convergence" && !convergence.length) runConvergence()
            }}
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

      <div style={{ padding: "16px" }}>
        {error && (
          <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 12,
            padding: 14, color: "#DC2626", fontSize: 13, marginBottom: 12 }}>
            {error.includes("does not exist") ? "Run the multibagger scan script first to populate data." : error}
          </div>
        )}

        {view === "discovery" && (
          loading ? <LoadingState label="Scoring stocks against DNA patterns…" /> :
          <DiscoveryList candidates={candidates} />
        )}

        {view === "convergence" && (
          convLoading ? <LoadingState label="Running all 6 engines…" /> :
          convergence.length ? <ConvergenceList results={convergence} /> :
          <div style={{ textAlign: "center", padding: "40px 0", color: "#9CA3AF", fontSize: 13 }}>
            Click to run convergence scan across all engines
            <br />
            <button onClick={runConvergence}
              style={{ marginTop: 12, background: colors.blue, color: "#fff",
                border: "none", borderRadius: 10, padding: "10px 20px",
                fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              Run Convergence Scan
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function DiscoveryList({ candidates }: { candidates: DiscoveryCandidate[] }) {
  if (!candidates.length) return (
    <div style={{ textAlign: "center", padding: "60px 0", color: "#9CA3AF" }}>
      <div style={{ fontSize: 32 }}>🧬</div>
      <div style={{ marginTop: 12, fontSize: 14 }}>No candidates found. Scan data may be incomplete.</div>
    </div>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {candidates.map((c, i) => {
        const tierColor = TIER_COLOR[c.predicted_tier] ?? "#6b7280"
        const tierLabel = TIER_LABEL[c.predicted_tier] ?? "Watch"
        return (
          <Card key={c.tradingsymbol}>
            <div style={{ display: "flex", justifyContent: "space-between",
              alignItems: "flex-start" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <ScoreRing score={c.dna_score} color={tierColor} />
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 15, fontWeight: 800,
                      color: colors.textPrimary }}>{c.tradingsymbol}</span>
                    <span style={{ background: tierColor + "18", color: tierColor,
                      fontSize: 10, fontWeight: 700, padding: "2px 7px",
                      borderRadius: 5 }}>{tierLabel}</span>
                    {c.is_nr7 && (
                      <span style={{ background: "#f3e8ff", color: "#7c3aed",
                        fontSize: 10, fontWeight: 700, padding: "2px 6px",
                        borderRadius: 5 }}>NR7</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 2 }}>
                    #{i+1} · Base {c.base_months}M · {Number(c.pct_below_high).toFixed(1)}% below high
                  </div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 14, fontWeight: 700,
                  color: colors.textPrimary }}>₹{Number(c.current_price).toFixed(2)}</div>
                <div style={{ fontSize: 11, color: c.momentum_6m >= 0 ? "#16A34A" : "#DC2626" }}>
                  {c.momentum_6m >= 0 ? "+" : ""}{Number(c.momentum_6m).toFixed(1)}% 6M
                </div>
              </div>
            </div>

            {/* Signals */}
            {c.signals.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 10 }}>
                {c.signals.map(s => (
                  <span key={s} style={{ background: "#F0FDF4", color: "#16A34A",
                    fontSize: 10, fontWeight: 600, padding: "3px 8px",
                    borderRadius: 5, border: "1px solid #BBF7D0" }}>{s}</span>
                ))}
              </div>
            )}

            {c.warnings.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 6 }}>
                {c.warnings.map(w => (
                  <span key={w} style={{ background: "#FEF3C7", color: "#D97706",
                    fontSize: 10, fontWeight: 600, padding: "3px 8px",
                    borderRadius: 5 }}>⚠ {w}</span>
                ))}
              </div>
            )}

            {/* DNA bar */}
            <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
              {[
                { label: "Base", val: Math.min(100, c.base_months / 24 * 100), color: "#2563EB" },
                { label: "VolComp", val: Math.min(100, (1 - c.vol_compression) * 150 + 30), color: "#16A34A" },
                { label: "Momentum", val: Math.min(100, Math.max(0, c.momentum_6m + 20) / 40 * 100), color: "#D97706" },
              ].map(({ label, val, color }) => (
                <div key={label} style={{ flex: 1 }}>
                  <div style={{ fontSize: 9, color: "#9CA3AF", marginBottom: 2 }}>{label}</div>
                  <div style={{ height: 4, background: "#F3F4F6", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${Math.round(val)}%`, height: "100%",
                      background: color, borderRadius: 2 }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )
      })}
    </div>
  )
}

function ConvergenceList({ results }: { results: ConvergenceResult[] }) {
  const sixSigma = results.filter(r => r.engines_triggered >= 5)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {sixSigma.length > 0 && (
        <div style={{ background: "#FEF2F2", border: "1px solid #FECACA",
          borderRadius: 12, padding: "12px 16px", marginBottom: 4 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#991B1B" }}>
            🚨 {sixSigma.length} 6-Sigma Setup{sixSigma.length > 1 ? "s" : ""} Found
          </div>
          <div style={{ fontSize: 11, color: "#DC2626", marginTop: 4 }}>
            These stocks are passing 5+ engines simultaneously. Rare setup.
          </div>
        </div>
      )}

      {results.map(r => {
        const alertColors: Record<string, string> = {
          "🔴 6-SIGMA ALERT": "#DC2626",
          "🟠 HIGH CONVICTION": "#D97706",
          "🟡 WATCH CLOSELY": "#ca8a04",
          "⚪ MONITOR": "#6b7280",
        }
        const ac = alertColors[r.alert_tier] ?? "#6b7280"
        const engineNames = ["DNA", "Momentum", "Institutional", "Supercycle", "Order Book", "Mgmt"]
        const maxScores = [25, 20, 20, 15, 10, 10]
        const scoreVals = Object.values(r.engine_scores)

        return (
          <Card key={r.tradingsymbol}>
            <div style={{ display: "flex", justifyContent: "space-between",
              alignItems: "flex-start" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 15, fontWeight: 800,
                    color: colors.textPrimary }}>{r.tradingsymbol}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: ac,
                    background: ac + "15", padding: "2px 8px",
                    borderRadius: 5 }}>{r.alert_tier}</span>
                </div>
                <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 2 }}>
                  {r.engines_triggered}/6 engines · ₹{Number(r.current_price).toFixed(2)}
                </div>
              </div>
              <ScoreRing score={r.convergence_score} color={ac} />
            </div>

            {/* Engine breakdown */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
              gap: 6, marginTop: 12 }}>
              {engineNames.map((name, i) => {
                const val = scoreVals[i] ?? 0
                const max = maxScores[i]
                const pct = Math.round(val / max * 100)
                const fired = pct >= 60
                return (
                  <div key={name} style={{ background: fired ? "#F0FDF4" : "#F9FAFB",
                    border: `1px solid ${fired ? "#BBF7D0" : "#E5E7EB"}`,
                    borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 9, color: fired ? "#16A34A" : "#9CA3AF",
                      fontWeight: 600 }}>{name}</div>
                    <div style={{ fontSize: 12, fontWeight: 700,
                      color: fired ? "#16A34A" : "#374151" }}>{val}/{max}</div>
                  </div>
                )
              })}
            </div>

            {r.signals.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 11, color: "#6b7280" }}>
                {r.signals.slice(0, 3).join(" · ")}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. TRADE JOURNAL + BEHAVIORAL MIRROR
// ─────────────────────────────────────────────────────────────────────────────
export function TradeJournalScreen() {
  const [trades, setTrades]             = useState<Record<string, unknown>[]>([])
  const [analysis, setAnalysis]         = useState<BehavioralAnalysis | null>(null)
  const [loading, setLoading]           = useState(true)
  const [syncing, setSyncing]           = useState(false)
  const [activeTab, setActiveTab]       = useState<"mirror" | "trades">("mirror")

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch("/api/trade-journal")
      const d = await r.json()
      if (d.ok) {
        setTrades(d.trades ?? [])
        if (d.behavioral_analysis) setAnalysis(d.behavioral_analysis)
      }
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [])

  const syncAndAnalyse = async () => {
    setSyncing(true)
    try {
      const r = await fetch("/api/trade-journal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ai: true }),
      })
      const d = await r.json()
      if (d.ok) {
        if (d.behavioral_analysis) setAnalysis(d.behavioral_analysis)
        await fetchData()
      }
    } catch { /* silent */ }
    finally { setSyncing(false) }
  }

  useEffect(() => { fetchData() }, [fetchData])

  return (
    <div style={{ background: colors.background, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB",
        padding: "20px 20px 0", position: "sticky", top: 0, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between",
          alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: colors.textPrimary,
              letterSpacing: "-0.4px" }}>Trade Journal</div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
              {trades.length} trades · AI Behavioral Mirror
            </div>
          </div>
          <button onClick={syncAndAnalyse} disabled={syncing}
            style={{ background: syncing ? "#F3F4F6" : colors.blue,
              color: syncing ? "#9CA3AF" : "#fff",
              border: "none", borderRadius: 10, padding: "8px 14px",
              fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            {syncing ? "Syncing…" : "Sync + Analyse"}
          </button>
        </div>
        <div style={{ display: "flex", borderTop: "1px solid #E5E7EB" }}>
          {[{ key: "mirror", label: "🧠 Behavioral Mirror" },
            { key: "trades", label: "📋 Trade Log" }].map(t => (
            <button key={t.key} onClick={() => setActiveTab(t.key as "mirror" | "trades")}
              style={{ flex: 1, padding: "11px 4px", fontSize: 12,
                fontWeight: activeTab === t.key ? 700 : 500,
                color: activeTab === t.key ? colors.blue : "#6b7280",
                background: "transparent", border: "none", cursor: "pointer",
                borderBottom: activeTab === t.key ? `2px solid ${colors.blue}` : "2px solid transparent" }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: 16 }}>
        {loading ? <LoadingState label="Loading trade data…" /> :
         activeTab === "mirror" ? <BehavioralMirrorView analysis={analysis} onSync={syncAndAnalyse} syncing={syncing} /> :
         <TradeLogView trades={trades} />}
      </div>
    </div>
  )
}

function BehavioralMirrorView({ analysis, onSync, syncing }: {
  analysis: BehavioralAnalysis | null
  onSync: () => void
  syncing: boolean
}) {
  if (!analysis) return (
    <div style={{ textAlign: "center", padding: "60px 20px" }}>
      <div style={{ fontSize: 40, marginBottom: 16 }}>🧠</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: colors.textPrimary,
        marginBottom: 8 }}>No behavioral analysis yet</div>
      <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 24 }}>
        Sync your Zerodha trades to generate your personal trading mirror
      </div>
      <button onClick={onSync} disabled={syncing}
        style={{ background: colors.blue, color: "#fff", border: "none",
          borderRadius: 12, padding: "12px 28px", fontSize: 14,
          fontWeight: 700, cursor: "pointer" }}>
        {syncing ? "Analysing…" : "Sync & Generate Mirror"}
      </button>
    </div>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Behavior type + scores */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: colors.textPrimary }}>
              {analysis.behavior_type}
            </div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
              {analysis.pattern_summary}
            </div>
          </div>
          <ScoreRing score={analysis.consistency_score} color={colors.blue} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)",
          gap: 8, marginTop: 14 }}>
          <StatBox label="Win Rate" value={`${Math.round(analysis.win_rate * 100)}%`}
            color={analysis.win_rate >= 0.6 ? "#16A34A" : "#DC2626"} />
          <StatBox label="Avg Hold" value={`${analysis.avg_hold_days}d`} />
          <StatBox label="Risk Score" value={`${analysis.risk_score}/100`}
            color={analysis.risk_score <= 40 ? "#16A34A" :
                   analysis.risk_score <= 65 ? "#D97706" : "#DC2626"} />
        </div>
      </Card>

      {/* Biggest bias */}
      <Card style={{ background: "#FEF3C7", border: "1px solid #FDE68A" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#92400E",
          marginBottom: 4 }}>⚠ BIGGEST BEHAVIORAL BIAS</div>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#78350F" }}>
          {analysis.biggest_bias}
        </div>
      </Card>

      {/* Mistakes */}
      <Card>
        <div style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary,
          marginBottom: 10 }}>Top Mistakes</div>
        {analysis.top_mistakes?.map((m, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
            <span style={{ color: "#DC2626", fontWeight: 700, marginTop: 1 }}>✗</span>
            <span style={{ fontSize: 13, color: "#374151" }}>{m}</span>
          </div>
        ))}
      </Card>

      {/* Strengths */}
      <Card>
        <div style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary,
          marginBottom: 10 }}>Strengths</div>
        {analysis.strengths?.map((s, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
            <span style={{ color: "#16A34A", fontWeight: 700 }}>✓</span>
            <span style={{ fontSize: 13, color: "#374151" }}>{s}</span>
          </div>
        ))}
      </Card>

      {/* Recommendations */}
      <Card style={{ background: "#EFF6FF", border: "1px solid #BFDBFE" }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#1E40AF",
          marginBottom: 10 }}>AI Recommendations</div>
        {analysis.recommendations?.map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
            <span style={{ color: colors.blue, fontWeight: 700, minWidth: 16 }}>{i+1}.</span>
            <span style={{ fontSize: 13, color: "#1E40AF" }}>{r}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB",
      borderRadius: 10, padding: "10px", textAlign: "center" }}>
      <div style={{ fontSize: 16, fontWeight: 800, color: color ?? colors.textPrimary }}>{value}</div>
      <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 2 }}>{label}</div>
    </div>
  )
}

function TradeLogView({ trades }: { trades: Record<string, unknown>[] }) {
  if (!trades.length) return (
    <div style={{ textAlign: "center", padding: "40px 0", color: "#9CA3AF", fontSize: 13 }}>
      No trades synced yet
    </div>
  )
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {trades.map((t, i) => {
        const isBuy = t.transaction_type === "BUY"
        return (
          <div key={i} style={{ background: "#fff", border: "1px solid #E5E7EB",
            borderRadius: 12, padding: "12px 14px",
            display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 700,
                  color: colors.textPrimary }}>{t.tradingsymbol as string}</span>
                <span style={{ fontSize: 10, fontWeight: 700,
                  color: isBuy ? "#16A34A" : "#DC2626",
                  background: isBuy ? "#F0FDF4" : "#FEF2F2",
                  padding: "2px 6px", borderRadius: 4 }}>
                  {t.transaction_type as string}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 2 }}>
                {String(t.trade_date ?? "").split("T")[0]} · {t.product as string}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 14, fontWeight: 700,
                color: colors.textPrimary }}>₹{parseFloat(t.price as string)?.toFixed(2)}</div>
              <div style={{ fontSize: 11, color: "#9CA3AF" }}>
                Qty: {t.quantity as number}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. CAPITAL DEPLOYMENT OPTIMIZER
// ─────────────────────────────────────────────────────────────────────────────
export function CapitalDeploymentOptimizer() {
  const [plan, setPlan]           = useState<DeploymentPlan | null>(null)
  const [loading, setLoading]     = useState(false)
  const [cash, setCash]           = useState("")
  const [portfolio, setPortfolio] = useState("")
  const [risk, setRisk]           = useState<"conservative" | "moderate" | "aggressive">("moderate")
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)

  // Load cached plan on mount
  useEffect(() => {
    fetch("/api/capital-deployment").then(r => r.json()).then(d => {
      if (d.ok && d.plan) { setPlan(d.plan); setGeneratedAt(d.generated_at) }
    }).catch(() => {})
  }, [])

  const generate = async () => {
    if (!cash) return
    setLoading(true)
    try {
      const r = await fetch("/api/capital-deployment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          available_cash: parseFloat(cash.replace(/,/g, "")),
          total_portfolio: parseFloat((portfolio || cash).replace(/,/g, "")),
          risk_appetite: risk,
        }),
      })
      const d = await r.json()
      if (d.ok && d.plan) { setPlan(d.plan); setGeneratedAt(new Date().toISOString()) }
    } catch { /* silent */ }
    finally { setLoading(false) }
  }

  const modeColors: Record<string, string> = {
    AGGRESSIVE: "#DC2626", MODERATE: "#D97706",
    DEFENSIVE: "#2563EB",  HOLD_CASH: "#6b7280"
  }

  return (
    <div style={{ background: colors.background, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB",
        padding: "20px", position: "sticky", top: 0, zIndex: 10 }}>
        <div style={{ fontSize: 20, fontWeight: 800, color: colors.textPrimary,
          letterSpacing: "-0.4px" }}>Capital Deployment</div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
          AI-powered allocation plan based on regime + opportunities
        </div>
      </div>

      <div style={{ padding: 16 }}>
        {/* Input form */}
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary,
            marginBottom: 12 }}>Your Capital Situation</div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>
                Available Cash (₹)
              </div>
              <input value={cash} onChange={e => setCash(e.target.value)}
                placeholder="e.g. 500000"
                style={{ width: "100%", border: "1px solid #E5E7EB", borderRadius: 10,
                  padding: "10px 12px", fontSize: 14, color: colors.textPrimary,
                  background: "#F9FAFB", boxSizing: "border-box" as const }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>
                Total Portfolio Value (₹) — optional
              </div>
              <input value={portfolio} onChange={e => setPortfolio(e.target.value)}
                placeholder="e.g. 2000000"
                style={{ width: "100%", border: "1px solid #E5E7EB", borderRadius: 10,
                  padding: "10px 12px", fontSize: 14, color: colors.textPrimary,
                  background: "#F9FAFB", boxSizing: "border-box" as const }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6 }}>Risk Appetite</div>
              <div style={{ display: "flex", gap: 6 }}>
                {(["conservative", "moderate", "aggressive"] as const).map(r => (
                  <button key={r} onClick={() => setRisk(r)}
                    style={{ flex: 1, padding: "8px 4px", fontSize: 11, fontWeight: 600,
                      borderRadius: 8, cursor: "pointer", textTransform: "capitalize" as const,
                      background: risk === r ? colors.blue : "#F9FAFB",
                      color: risk === r ? "#fff" : "#6b7280",
                      border: `1px solid ${risk === r ? colors.blue : "#E5E7EB"}` }}>
                    {r}
                  </button>
                ))}
              </div>
            </div>
            <button onClick={generate} disabled={loading || !cash}
              style={{ background: (!cash || loading) ? "#F3F4F6" : colors.blue,
                color: (!cash || loading) ? "#9CA3AF" : "#fff",
                border: "none", borderRadius: 12, padding: "13px",
                fontSize: 14, fontWeight: 700, cursor: "pointer",
                marginTop: 4 }}>
              {loading ? "Generating plan…" : "Generate Deployment Plan"}
            </button>
          </div>
        </Card>

        {/* Plan output */}
        {plan && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Mode badge */}
            <Card style={{ background: (modeColors[plan.deployment_mode] ?? "#6b7280") + "12",
              border: `1px solid ${modeColors[plan.deployment_mode] ?? "#6b7280"}30` }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 800,
                    color: modeColors[plan.deployment_mode] ?? "#6b7280" }}>
                    {plan.deployment_mode}
                  </div>
                  <div style={{ fontSize: 12, color: "#374151", marginTop: 4 }}>
                    {plan.regime_assessment}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 14, fontWeight: 700,
                    color: "#16A34A" }}>{plan.expected_cagr_range}</div>
                  <div style={{ fontSize: 10, color: "#9CA3AF" }}>expected CAGR</div>
                </div>
              </div>
            </Card>

            {/* Top action */}
            <Card style={{ background: "#F0FDF4", border: "1px solid #BBF7D0" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#16A34A",
                marginBottom: 4 }}>⚡ TOP ACTION RIGHT NOW</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#14532D" }}>
                {plan.top_action}
              </div>
            </Card>

            {/* Allocations */}
            <Card>
              <div style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary,
                marginBottom: 12 }}>Deployment Breakdown</div>
              {plan.allocations?.map((a, i) => {
                const catColors: Record<string, string> = {
                  IPO: "#2563EB", Multibagger: "#7c3aed",
                  "Existing Position": "#16A34A", "Cash Reserve": "#6b7280"
                }
                const cc = catColors[a.category] ?? "#6b7280"
                return (
                  <div key={i} style={{ marginBottom: 12, paddingBottom: 12,
                    borderBottom: i < (plan.allocations?.length ?? 0) - 1
                      ? "1px solid #F3F4F6" : "none" }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: cc }}>
                        {a.category}
                      </span>
                      <span style={{ fontSize: 14, fontWeight: 800,
                        color: colors.textPrimary }}>
                        {a.pct_of_available}%
                        {a.amount > 0 && (
                          <span style={{ fontSize: 11, color: "#6b7280", marginLeft: 4 }}>
                            (₹{a.amount.toLocaleString("en-IN")})
                          </span>
                        )}
                      </span>
                    </div>
                    <div style={{ height: 5, background: "#F3F4F6", borderRadius: 3,
                      marginBottom: 6, overflow: "hidden" }}>
                      <div style={{ width: `${a.pct_of_available}%`, height: "100%",
                        background: cc, borderRadius: 3 }} />
                    </div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>{a.reasoning}</div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: cc,
                      marginTop: 3 }}>→ {a.specific_action}</div>
                  </div>
                )
              })}
            </Card>

            {/* Risk warning */}
            {plan.risk_warning && (
              <Card style={{ background: "#FEF3C7", border: "1px solid #FDE68A" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#92400E",
                  marginBottom: 4 }}>⚠ RISK WARNING</div>
                <div style={{ fontSize: 13, color: "#78350F" }}>{plan.risk_warning}</div>
              </Card>
            )}

            {/* Review trigger */}
            <Card>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280",
                marginBottom: 4 }}>When to review this plan</div>
              <div style={{ fontSize: 13, color: "#374151" }}>{plan.review_trigger}</div>
            </Card>

            {generatedAt && (
              <div style={{ textAlign: "center", fontSize: 11, color: "#D1D5DB" }}>
                Generated {new Date(generatedAt).toLocaleString("en-IN",
                  { timeZone: "Asia/Kolkata" })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

