"use client"
// components/features/multibagger-discovery.tsx
// MULTIBAGGER DISCOVERY — The flagship screen.
// Shows stocks where ALL engines align:
// Earnings accelerating + Commentary bullish + AMFI risk-on + Technical above EMA200
// V10: Highest signal screen in the platform.

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, ChevronDown, ChevronUp, Star, TrendingUp } from "lucide-react"

const C = {
  green:  "#16A34A", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  blue:   "#2563EB", blueBg:   "#EFF6FF", blueBd:  "#BFDBFE",
  amber:  "#D97706", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:    "#DC2626", redBg:    "#FEF2F2",
  purple: "#7C3AED", purpleBg: "#F5F3FF", purpleBd:"#E9D5FF",
  gray:   "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:   "#111827", textSub:  "#6B7280", surface:  "#FFFFFF", bg: "#FAFAF8", border: "#E5E7EB",
}

const n = (v: unknown) => parseFloat(String(v || 0)) || 0

// Engine status badge
type EngineStatus = "STRONG" | "OK" | "WEAK" | "MISSING"
const ENGINE_CFG: Record<EngineStatus, { color: string; bg: string; label: string }> = {
  STRONG:  { color: C.green,  bg: C.greenBg,  label: "Strong"  },
  OK:      { color: C.blue,   bg: C.blueBg,   label: "OK"      },
  WEAK:    { color: C.amber,  bg: C.amberBg,  label: "Weak"    },
  MISSING: { color: C.gray,   bg: C.grayBg,   label: "No data" },
}

interface MultibaggerCandidate {
  symbol: string
  company_name?: string
  conviction_score: number
  // Engine signals
  earnings_status: string
  earnings_score: number
  commentary_status: string
  commentary_score: number
  amfi_status: string
  technical_signal?: string // above/below EMA200
  // Why this is a candidate
  reasons: string[]
  // Sector
  sector?: string
  // Price
  close?: number
  change_pct?: number
}

function engineStatus(score: number, goodThreshold = 60, okThreshold = 40): EngineStatus {
  if (score >= goodThreshold) return "STRONG"
  if (score >= okThreshold) return "OK"
  if (score > 0) return "WEAK"
  return "MISSING"
}

// ─── Engine indicator ─────────────────────────────────────────────────────────
function EngineIndicator({ label, status, simple }: { label: string; status: EngineStatus; simple: boolean }) {
  const cfg = ENGINE_CFG[status]
  return (
    <div style={{ display: "flex", flexDirection: "column" as const, alignItems: "center", gap: 3 }}>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: cfg.color }} />
      {!simple && <div style={{ fontSize: 9, color: C.textSub, textAlign: "center" as const, lineHeight: 1.2 }}>{label}</div>}
    </div>
  )
}

// ─── Conviction ring ──────────────────────────────────────────────────────────
function ConvictionRing({ score, size = 48 }: { score: number; size?: number }) {
  const color = score >= 75 ? C.purple : score >= 60 ? C.green : score >= 45 ? C.amber : C.gray
  const pct = Math.min(100, Math.round(score))
  const r = (size - 6) / 2
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={C.grayBd} strokeWidth={4} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} />
      <text x={size/2} y={size/2 + 1} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: size < 44 ? 11 : 13, fontWeight: 700, fill: color }}>{pct}</text>
    </svg>
  )
}

// ─── Candidate card ───────────────────────────────────────────────────────────
function CandidateCard({ c, simple, expanded, onToggle, onSelect }: {
  c: MultibaggerCandidate; simple: boolean; expanded: boolean;
  onToggle: () => void; onSelect?: (s: string) => void;
}) {
  const chg = n(c.change_pct)
  const amfiStrong = ["RISK_ON","SELECTIVE_RISK_ON"].includes(c.amfi_status)

  const engStatus = {
    earnings:    engineStatus(c.earnings_score, 60, 30),
    commentary:  engineStatus(c.commentary_score, 60, 30),
    amfi:        amfiStrong ? "STRONG" as EngineStatus : "OK" as EngineStatus,
    technical:   c.technical_signal === "above" ? "STRONG" as EngineStatus : c.technical_signal === "below" ? "WEAK" as EngineStatus : "MISSING" as EngineStatus,
  }

  const allStrong = Object.values(engStatus).every(s => ["STRONG","OK"].includes(s))

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${allStrong ? C.purpleBd : C.border}`,
      borderLeft: `3px solid ${allStrong ? C.purple : C.amber}`,
      borderRadius: 12, marginBottom: 8, overflow: "hidden",
    }}>

      {/* Header */}
      <div onClick={onToggle} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>

        {/* Conviction ring */}
        <div onClick={e => { e.stopPropagation(); onSelect?.(c.symbol) }}>
          <ConvictionRing score={c.conviction_score} size={44} />
        </div>

        {/* Symbol + info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
            {allStrong && <Star size={12} color={C.purple} fill={C.purple} />}
            <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{c.symbol}</span>
            {!simple && c.sector && <span style={{ fontSize: 10, color: C.textSub }}>{c.sector}</span>}
          </div>
          {simple ? (
            <div style={{ fontSize: 11, color: C.textSub }}>{c.reasons[0]}</div>
          ) : (
            <div style={{ fontSize: 11, color: C.textSub }}>{c.company_name}</div>
          )}
        </div>

        {/* Engine indicators */}
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
          {Object.entries(engStatus).map(([key, status]) => (
            <EngineIndicator key={key}
              label={key === "earnings" ? "Earn" : key === "commentary" ? "Mgmt" : key === "amfi" ? "AMFI" : "Tech"}
              status={status} simple={simple} />
          ))}
        </div>

        {/* Price */}
        {c.close && (
          <div style={{ textAlign: "right" as const, flexShrink: 0, minWidth: 56 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>₹{c.close.toLocaleString("en-IN")}</div>
            <div style={{ fontSize: 11, color: chg >= 0 ? C.green : C.red }}>{chg > 0 ? "+" : ""}{chg.toFixed(1)}%</div>
          </div>
        )}

        {expanded ? <ChevronUp size={14} color={C.textSub} /> : <ChevronDown size={14} color={C.textSub} />}
      </div>

      {/* Expanded */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}`, background: "#FAFAF8", padding: "12px 14px" }}>

          {/* Engine breakdown */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 12 }}>
            {[
              { label: simple ? "Earnings" : "Earnings engine", score: c.earnings_score, status: engStatus.earnings },
              { label: simple ? "Management" : "Commentary engine", score: c.commentary_score, status: engStatus.commentary },
              { label: "AMFI", score: amfiStrong ? 80 : 50, status: engStatus.amfi },
              { label: simple ? "Technical" : "Technical engine", score: c.technical_signal === "above" ? 75 : 40, status: engStatus.technical },
            ].map(({ label, score, status }) => {
              const cfg = ENGINE_CFG[status]
              return (
                <div key={label} style={{ background: cfg.bg, border: `1px solid ${cfg.color}30`, borderRadius: 8, padding: "8px 10px", textAlign: "center" as const }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: cfg.color }}>{Math.round(score)}</div>
                  <div style={{ fontSize: 10, color: cfg.color }}>{label}</div>
                </div>
              )
            })}
          </div>

          {/* Why */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 6 }}>
              {simple ? "Why this stock?" : "Alignment signals"}
            </div>
            {c.reasons.map((r, i) => (
              <div key={i} style={{ fontSize: 12, color: C.text, display: "flex", gap: 6, marginBottom: 4 }}>
                <span style={{ color: C.purple }}>✓</span> {r}
              </div>
            ))}
          </div>

          {/* Statuses */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" as const }}>
            <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: C.greenBg, color: C.green }}>{c.earnings_status}</span>
            <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: C.blueBg, color: C.blue }}>{c.commentary_status}</span>
            {c.amfi_status && <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: C.amberBg, color: C.amber }}>AMFI {c.amfi_status.replace("_"," ")}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export function MultibaggerDiscovery({ simple = false, onStockSelect }: { simple?: boolean; onStockSelect?: (s: string) => void }) {
  const [loading, setLoading] = useState(true)
  const [candidates, setCandidates] = useState<MultibaggerCandidate[]>([])
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)
  const [minEngines, setMinEngines] = useState(2)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // Primary: technical screener + management commentary (always has data)
      // Secondary: intelligence dashboard (has data when earnings pipeline runs)
      const [techRes, commRes, dashRes, amfiRes] = await Promise.all([
        fetch("/api/technical/screener?timeframe=daily&limit=50", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/intelligence/commentary?limit=50").then(r => r.json()).catch(() => null),
        fetch("/api/intelligence/dashboard").then(r => r.json()).catch(() => null),
        fetch("/api/intelligence/amfi").then(r => r.json()).catch(() => null),
      ])

      const amfiStatus   = amfiRes?.data?.score?.liquidity_status || "NEUTRAL"
      const amfiPositive = ["RISK_ON","SELECTIVE_RISK_ON"].includes(amfiStatus)
      const SUPPRESS     = /^(ANTELOP|ACUTAAS|BMWVENTURE)/i

      // Build commentary map from management_commentary table
      const commList = (commRes?.data ?? commRes ?? []) as any[]
      const commArr  = Array.isArray(commList) ? commList : []
      const cMap = new Map(commArr.map((c: any) => [c.symbol ?? c.nse_symbol, c]))

      // Build earnings map from dashboard (if available)
      const earningsArr = (dashRes?.data?.top_earnings ?? []) as any[]
      const eMap = new Map(earningsArr.map((e: any) => [e.symbol, e]))

      // Primary source: technical signals (always populated for recommended stocks)
      const techList = (techRes?.data ?? []) as any[]
      const filtered = techList.filter((x: any) => !SUPPRESS.test(String(x.symbol ?? "")))

      const candidates: MultibaggerCandidate[] = filtered.map((t: any) => {
        const sym  = t.symbol ?? t.nse_symbol
        const c    = cMap.get(sym) as any
        const e    = eMap.get(sym) as any

        const techScore    = n(t.buy_zone_score ?? t.convergence_score ?? t.score ?? 55)
        const commScore    = n(c?.total_score ?? c?.mgmt_quality_score ?? 0)
        const earningsScore= n(e?.total_score ?? 0)

        const techGood     = techScore >= 60
        const commGood     = c && ["BULLISH","CAUTIOUSLY_OPTIMISTIC","IMPROVING"].includes(c.management_tone ?? c.commentary_status ?? "")
        const earningsGood = e && ["ACCELERATING","TURNAROUND"].includes(e.acceleration_status ?? "")

        let enginesAligned = 0
        if (techGood)     enginesAligned++
        if (commGood)     enginesAligned++
        if (earningsGood) enginesAligned++
        if (amfiPositive) enginesAligned++

        const reasons: string[] = []
        if (techScore >= 70)  reasons.push(`Technical score ${Math.round(techScore)}/100`)
        if (t.nr7)            reasons.push("NR7 compression — breakout imminent")
        if (t.volume_expansion) reasons.push("Volume expansion detected")
        if (commGood)         reasons.push(`Management ${(c?.management_tone ?? "").toLowerCase()} — ${c?.guidance_direction ?? "stable"}`)
        if (earningsGood)     reasons.push("Earnings accelerating")
        if (amfiPositive)     reasons.push("Market liquidity supports positions")
        if (c?.revenue_guidance) reasons.push(`Revenue guidance: ${c.revenue_guidance}`)

        const conviction = Math.min(100,
          techScore * 0.45 +
          (commScore > 0 ? commScore * 0.25 : 0) +
          (earningsScore > 0 ? earningsScore * 0.20 : 0) +
          (amfiPositive ? 10 : 0)
        )

        return {
          symbol: sym,
          company_name: t.company_name ?? c?.company_name ?? sym,
          conviction_score: Math.round(conviction),
          earnings_status:  e?.acceleration_status ?? "STABLE",
          earnings_score:   earningsScore,
          commentary_status: c?.management_tone ?? c?.commentary_status ?? "NEUTRAL",
          commentary_score:  commScore,
          amfi_status: amfiStatus,
          enginesAligned,
          reasons,
        } as MultibaggerCandidate & { enginesAligned: number }
      })
      .filter((c: any) => c.enginesAligned >= minEngines)
      .sort((a: any, b: any) => b.conviction_score - a.conviction_score)
      .slice(0, 30)

      setCandidates(candidates)
      setLastUpdate(new Date())
    } catch (err) { console.error("MultibaggerDiscovery error:", err) }
    finally { setLoading(false) }
  }, [minEngines])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Star size={18} color={C.purple} fill={C.purple} />
              <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>
                {simple ? "Potential multibaggers" : "Multibagger discovery"}
              </div>
            </div>
            <div style={{ fontSize: 11, color: C.textSub, marginTop: 2 }}>
              {simple ? "Stocks where everything lines up" : "Stocks with all intelligence engines aligned"}
              {lastUpdate ? ` · ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : ""}
            </div>
          </div>
          <button onClick={() => load()}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "7px 12px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, fontSize: 12, color: C.textSub, cursor: "pointer" }}>
            <RefreshCw size={12} /> Refresh
          </button>
        </div>

        {/* Engine count filter */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px", marginBottom: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 6 }}>
            {simple ? "Show stocks with at least…" : "Minimum engines aligned"}: <span style={{ color: C.purple }}>{minEngines}</span>
          </div>
          <input type="range" min={1} max={3} step={1} value={minEngines}
            onChange={e => setMinEngines(Number(e.target.value))} style={{ width: "100%" }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textSub, marginTop: 4 }}>
            <span>1 engine (broad)</span>
            <span>2 engines</span>
            <span>3 engines (strongest)</span>
          </div>
        </div>

        {/* Engine legend */}
        {!simple && (
          <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" as const }}>
            {[
              { dot: C.green, label: "Strong signal" },
              { dot: C.blue, label: "OK signal" },
              { dot: C.amber, label: "Weak signal" },
              { dot: C.gray, label: "No data" },
            ].map(({ dot, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: C.textSub }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: dot }} /> {label}
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        {loading ? (
          [1,2,3].map(i => <div key={i} style={{ background: C.grayBg, borderRadius: 12, height: 72, marginBottom: 8 }} />)
        ) : candidates.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: C.textSub }}>
            <Star size={32} color={C.grayBd} style={{ margin: "0 auto 12px", display: "block" }} />
            <div style={{ fontSize: 14, marginBottom: 6 }}>No stocks match all engines right now</div>
            <div style={{ fontSize: 12 }}>Try reducing the engine count to 1 or 2</div>
          </div>
        ) : candidates.map(c => (
          <CandidateCard key={c.symbol} c={c} simple={simple}
            expanded={expandedSymbol === c.symbol}
            onToggle={() => setExpandedSymbol(expandedSymbol === c.symbol ? null : c.symbol)}
            onSelect={onStockSelect} />
        ))}

        {!simple && candidates.length > 0 && (
          <div style={{ fontSize: 10, color: "#D1D5DB", textAlign: "center", marginTop: 8 }}>
            Conviction score = weighted average of Earnings (50%) + Commentary (30%) + AMFI bonus (20%)
          </div>
        )}
      </div>
    </div>
  )
}
