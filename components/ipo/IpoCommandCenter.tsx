"use client"
// components/ipo/IpoCommandCenter.tsx
// IPO COMMAND CENTER — V10 redesign
// STRONG APPLY / APPLY / SMALL APPLY / WATCH / AVOID
// Sections: Open Now · Upcoming · Watch · Listing Day · Post Listing

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, ChevronDown, ChevronUp, Zap, TrendingUp, Eye, Shield, AlertTriangle } from "lucide-react"

const C = {
  green:  "#15803D", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  blue:   "#1D4ED8", blueBg:   "#EFF6FF", blueBd:  "#BFDBFE",
  amber:  "#B45309", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:    "#B91C1C", redBg:    "#FEF2F2", redBd:   "#FECACA",
  purple: "#7C3AED", purpleBg: "#F5F3FF", purpleBd:"#E9D5FF",
  cyan:   "#0891B2", cyanBg:   "#ECFEFF",
  gray:   "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:   "#111827", textSub:  "#6B7280", surface:  "#FFFFFF", bg: "#FAFAF8", border: "#E5E7EB",
}

// Recommendation → visual config
const REC_CFG: Record<string, { color: string; bg: string; bd: string; label: string; icon: string }> = {
  "Apply Aggressively":                        { color: C.green,  bg: C.greenBg,  bd: C.greenBd,  label: "Strong apply",     icon: "🟢" },
  "Apply — Long-Term Hold":                    { color: C.blue,   bg: C.blueBg,   bd: C.blueBd,   label: "Apply",            icon: "🔵" },
  "Apply — Listing Trade Only":                { color: C.cyan,   bg: C.cyanBg,   bd: "#A5F3FC",  label: "Small apply",      icon: "💧" },
  "Apply Retail Only":                         { color: C.blue,   bg: C.blueBg,   bd: C.blueBd,   label: "Apply",            icon: "🔵" },
  "Long-Term Compounder — Buy on Listing Dip": { color: C.purple, bg: C.purpleBg, bd: C.purpleBd, label: "Watch post-listing",icon: "👀" },
  "Watch — Selective Apply":                   { color: C.amber,  bg: C.amberBg,  bd: C.amberBd,  label: "Watch",            icon: "🟡" },
  "Avoid":                                     { color: C.red,    bg: C.redBg,    bd: C.redBd,    label: "Avoid",            icon: "🔴" },
}

function getRecCfg(rec: string) {
  return REC_CFG[rec] || { color: C.gray, bg: C.grayBg, bd: C.grayBd, label: rec, icon: "⚪" }
}

const TABS = [
  { id: "open",     label: "Open now",    icon: <Zap size={11} />        },
  { id: "upcoming", label: "Upcoming",    icon: <TrendingUp size={11} />  },
  { id: "watch",    label: "Watch list",  icon: <Eye size={11} />         },
  { id: "listing",  label: "Listing day", icon: <TrendingUp size={11} />  },
]

const n = (v: unknown) => parseFloat(String(v || 0)) || 0

// ─── Score bar ────────────────────────────────────────────────────────────────
function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
        <span style={{ fontSize: 11, color: C.textSub }}>{label}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color }}>{Math.round(score)}</span>
      </div>
      <div style={{ height: 3, background: C.grayBd, borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.min(100, score)}%`, background: color, borderRadius: 2 }} />
      </div>
    </div>
  )
}

// ─── IPO hero card ────────────────────────────────────────────────────────────
function IpoCard({ ipo, simple, expanded, onToggle }: {
  ipo: any; simple: boolean; expanded: boolean; onToggle: () => void
}) {
  const s = ipo.score || {}
  const rec = s.recommendation || "Watch — Selective Apply"
  const cfg = getRecCfg(rec)
  const gmp = n(ipo.gmpPrice)
  const issue = n(ipo.priceBandHigh || ipo.priceBandLow)
  const gmpPct = issue > 0 ? (gmp / issue * 100).toFixed(0) : null
  const listingScore = n(s.listingScore)
  const businessScore = n(s.businessScore)
  const anchorScore = n(s.anchorScore)

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${cfg.bd}`,
      borderLeft: `4px solid ${cfg.color}`,
      borderRadius: 14, marginBottom: 10, overflow: "hidden",
    }}>
      {/* Header */}
      <div onClick={onToggle} style={{ padding: "14px 16px", cursor: "pointer" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1 }}>
            {/* Recommendation badge */}
            <div style={{ marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 6, background: cfg.bg, color: cfg.color }}>
                {cfg.icon} {simple ? cfg.label : rec}
              </span>
            </div>
            <div style={{ fontSize: 17, fontWeight: 800, color: C.text, marginBottom: 2 }}>{ipo.name}</div>
            <div style={{ fontSize: 11, color: C.textSub }}>
              {ipo.sector} · ₹{ipo.priceBandLow}–₹{issue} · ₹{ipo.issueSize}Cr
              {ipo.lotSize ? ` · Lot ${ipo.lotSize}` : ""}
            </div>
          </div>

          {/* Score ring */}
          <div style={{ textAlign: "center" as const, flexShrink: 0 }}>
            <div style={{ fontSize: 26, fontWeight: 800, color: listingScore >= 70 ? C.green : listingScore >= 50 ? C.amber : C.red }}>
              {Math.round(listingScore)}
            </div>
            <div style={{ fontSize: 9, color: C.textSub }}>conviction</div>
          </div>
        </div>

        {/* Key metrics row */}
        <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap" as const }}>
          {gmp > 0 && (
            <div>
              <div style={{ fontSize: 9, color: C.textSub }}>GMP</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: gmp > 0 ? C.green : C.red }}>
                ₹{gmp} ({gmpPct}%)
              </div>
            </div>
          )}
          {ipo.openDate && (
            <div>
              <div style={{ fontSize: 9, color: C.textSub }}>Opens</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{ipo.openDate}</div>
            </div>
          )}
          {ipo.closeDate && (
            <div>
              <div style={{ fontSize: 9, color: C.textSub }}>Closes</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{ipo.closeDate}</div>
            </div>
          )}
          {s.confidence && (
            <div>
              <div style={{ fontSize: 9, color: C.textSub }}>Confidence</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{s.confidence}</div>
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
          {expanded ? <ChevronUp size={14} color={C.textSub} /> : <ChevronDown size={14} color={C.textSub} />}
        </div>
      </div>

      {/* Expanded */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}`, background: "#FAFAF8", padding: "14px 16px" }}>

          {/* Score breakdown */}
          {!simple && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 8 }}>
                Score breakdown
              </div>
              <ScoreBar label="Listing potential" score={listingScore} color={cfg.color} />
              <ScoreBar label="Business quality" score={businessScore} color={C.blue} />
              {anchorScore > 0 && <ScoreBar label="Anchor quality" score={anchorScore} color={C.purple} />}
            </div>
          )}

          {/* Broker note */}
          {ipo.brokerNote && (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", marginBottom: 10 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, marginBottom: 4 }}>
                {ipo.brokerReco ? `Broker: ${ipo.brokerReco}` : "Broker view"}
              </div>
              <div style={{ fontSize: 12, color: C.text, lineHeight: 1.5 }}>{ipo.brokerNote}</div>
            </div>
          )}

          {/* Fresh vs OFS */}
          {ipo.freshIssue && ipo.issueSize && (
            <div style={{ display: "flex", gap: 16, marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 10, color: C.textSub }}>Fresh issue</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.green }}>₹{ipo.freshIssue}Cr ({Math.round(ipo.freshIssue/ipo.issueSize*100)}%)</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: C.textSub }}>OFS</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: ipo.freshIssue/ipo.issueSize > 0.5 ? C.green : C.amber }}>
                  ₹{(ipo.issueSize - ipo.freshIssue).toFixed(0)}Cr ({Math.round((1-ipo.freshIssue/ipo.issueSize)*100)}%)
                </div>
              </div>
            </div>
          )}

          {/* Apply guidance */}
          <div style={{ background: cfg.bg, border: `1px solid ${cfg.bd}`, borderRadius: 8, padding: "10px 12px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: cfg.color, marginBottom: 3 }}>
              {simple ? "What to do:" : "Recommended action"}
            </div>
            <div style={{ fontSize: 12, color: cfg.color }}>
              {rec.includes("Aggressively") && "Apply in all categories. Strong listing expected."}
              {rec.includes("Long-Term") && "Apply and hold for 12+ months. Not a listing trade."}
              {rec.includes("Listing Trade") && "Apply for listing gains only. Exit on listing day if GMP holds."}
              {rec.includes("Retail Only") && "Apply in retail category only. Small allotment play."}
              {rec.includes("Listing Dip") && "Skip IPO. Buy on listing day dip if fundamentals confirm."}
              {rec.includes("Selective") && "Watch GMP trend. Apply only if subscription stays strong."}
              {rec === "Avoid" && "Skip this IPO. Risk/reward not favourable at current price."}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export function IpoCommandCenter({ simple = false }: { simple?: boolean }) {
  const [loading, setLoading] = useState(true)
  const [ipos, setIpos] = useState<any[]>([])
  const [activeTab, setActiveTab] = useState("open")
  const [expandedIpo, setExpandedIpo] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/ipo?limit=20").then(r => r.json()).catch(() => null)
      if (res?.ipos) {
        setIpos(res.ipos)
        setLastUpdate(new Date())
      }
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = ipos.filter(ipo => {
    const status = (ipo.status || "").toUpperCase()
    if (activeTab === "open") return status === "OPEN"
    if (activeTab === "upcoming") return status === "UPCOMING" || status === "COMING_SOON"
    if (activeTab === "watch") return status === "CLOSED" && !status.includes("LIST")
    if (activeTab === "listing") return status === "LISTING" || status === "LISTED"
    return true
  })

  // Sort: high conviction first
  const sorted = [...filtered].sort((a, b) => n(b.score?.listingScore) - n(a.score?.listingScore))

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ padding: "16px 16px 0", marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Zap size={18} color={C.purple} />
                <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>
                  {simple ? "IPO decisions" : "IPO command center"}
                </div>
              </div>
              <div style={{ fontSize: 11, color: C.textSub, marginTop: 2 }}>
                {lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : "Loading…"}
              </div>
            </div>
            <button onClick={load}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "7px 12px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, fontSize: 12, color: C.textSub, cursor: "pointer" }}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div style={{ borderBottom: `1px solid ${C.border}`, padding: "0 16px", display: "flex", gap: 0, marginBottom: 16 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "10px 14px", border: "none", fontSize: 12, fontWeight: activeTab === t.id ? 700 : 500, color: activeTab === t.id ? C.purple : C.textSub, background: "transparent", cursor: "pointer", borderBottom: activeTab === t.id ? `2px solid ${C.purple}` : "2px solid transparent" }}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        <div style={{ padding: "0 16px" }}>
          {loading ? (
            [1,2].map(i => <div key={i} style={{ background: C.grayBg, borderRadius: 14, height: 120, marginBottom: 10 }} />)
          ) : sorted.length === 0 ? (
            <div style={{ padding: "48px 0", textAlign: "center", color: C.textSub }}>
              <Zap size={32} color={C.grayBd} style={{ margin: "0 auto 12px", display: "block" }} />
              <div style={{ fontSize: 14 }}>No IPOs in this category right now</div>
            </div>
          ) : sorted.map(ipo => (
            <IpoCard key={ipo.id || ipo.name} ipo={ipo} simple={simple}
              expanded={expandedIpo === (ipo.id || ipo.name)}
              onToggle={() => setExpandedIpo(expandedIpo === (ipo.id || ipo.name) ? null : (ipo.id || ipo.name))} />
          ))}
        </div>
      </div>
    </div>
  )
}
