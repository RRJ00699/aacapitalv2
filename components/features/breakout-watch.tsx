"use client"
// components/features/breakout-watch.tsx
// SESSION 9 — Breakout Watch screen.
// Surfaces stocks like ABCAPITAL BEFORE they break out, not after.
// The existing Multibagger engine rewards momentum (already moving).
// This screen rewards anticipation: coiled under 52W high + building volume.

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, ChevronDown, ChevronUp, Zap, TrendingUp } from "lucide-react"

const C = {
  text:     "#111827",
  textSub:  "#6B7280",
  surface:  "#FFFFFF",
  bg:       "#FAFAF8",
  border:   "#E5E7EB",
  green:    "#16A34A", greenBg: "#F0FDF4", greenBd: "#BBF7D0",
  blue:     "#2563EB", blueBg:  "#EFF6FF", blueBd:  "#BFDBFE",
  amber:    "#D97706", amberBg: "#FFFBEB", amberBd: "#FDE68A",
  orange:   "#EA580C", orangeBg:"#FFF7ED", orangeBd:"#FED7AA",
  red:      "#DC2626", redBg:   "#FEF2F2",
  purple:   "#7C3AED", purpleBg:"#F5F3FF", purpleBd:"#E9D5FF",
  gray:     "#6B7280", grayBg:  "#F9FAFB", grayBd:  "#E5E7EB",
}

interface BreakoutCandidate {
  symbol: string
  company_name?: string
  sector?: string
  close?: number
  breakout_watch_score: number
  breakout_watch_tier?: string
  pct_below_high?: number
  is_nr7?: boolean
  nr7?: boolean
  above_ema200?: boolean
  volume_ratio_20?: number
  vol_compression?: number
  momentum_6m?: number
  stage?: string
  stage_label?: string
  mb_score?: number
}

const TIER_CFG: Record<string, { color: string; bg: string; bd: string; label: string; desc: string }> = {
  COILED:   { color: C.orange, bg: C.orangeBg, bd: C.orangeBd, label: "🔥 COILED",   desc: "All signals aligned — breakout imminent" },
  BUILDING: { color: C.amber,  bg: C.amberBg,  bd: C.amberBd,  label: "⚡ BUILDING", desc: "Setup forming — watch closely" },
  EARLY:    { color: C.blue,   bg: C.blueBg,   bd: C.blueBd,   label: "👁 EARLY",    desc: "Early accumulation — start monitoring" },
}

function n(v: unknown) { return parseFloat(String(v || 0)) || 0 }
function pct(v: unknown) { return `${n(v).toFixed(1)}%` }

// ─── Proximity bar ───────────────────────────────────────────────────────────
function ProximityBar({ pctBelow }: { pctBelow: number }) {
  const capped = Math.max(0, Math.min(20, pctBelow))
  const filled = 100 - (capped / 20 * 100)
  const color   = pctBelow <= 1 ? C.orange : pctBelow <= 3 ? C.amber : C.blue
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textSub, marginBottom: 3 }}>
        <span>52W High proximity</span>
        <span style={{ fontWeight: 700, color }}>{pctBelow <= 0 ? "AT/ABOVE HIGH" : `${pctBelow.toFixed(1)}% below`}</span>
      </div>
      <div style={{ height: 5, background: C.grayBd, borderRadius: 3 }}>
        <div style={{ width: `${filled}%`, height: "100%", background: color, borderRadius: 3, transition: "width .4s" }} />
      </div>
    </div>
  )
}

// ─── Signal pill ─────────────────────────────────────────────────────────────
function Pill({ label, active, color = C.green }: { label: string; active: boolean; color?: string }) {
  if (!active) return null
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "2px 7px", borderRadius: 20,
      background: color + "1a", color, border: `1px solid ${color}30`,
    }}>{label}</span>
  )
}

// ─── Score ring ───────────────────────────────────────────────────────────────
function ScoreRing({ score, size = 48 }: { score: number; size?: number }) {
  const color = score >= 80 ? C.orange : score >= 60 ? C.amber : C.blue
  const r     = (size - 6) / 2
  const circ  = 2 * Math.PI * r
  const dash  = (Math.min(100, score) / 100) * circ
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={C.grayBd} strokeWidth={4} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} />
      <text x={size/2} y={size/2 + 1} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: 12, fontWeight: 800, fill: color }}>{score}</text>
    </svg>
  )
}

// ─── Candidate card ───────────────────────────────────────────────────────────
function CandidateCard({
  c, expanded, onToggle, onSelect,
}: {
  c: BreakoutCandidate; expanded: boolean;
  onToggle: () => void; onSelect?: (s: string) => void;
}) {
  const tier   = c.breakout_watch_tier
  const tierCfg = tier ? TIER_CFG[tier] : null
  const isNR7  = c.is_nr7 || c.nr7
  const vr     = n(c.volume_ratio_20)

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${tierCfg ? tierCfg.bd : C.border}`,
      borderLeft: `3px solid ${tierCfg ? tierCfg.color : C.grayBd}`,
      borderRadius: 12, marginBottom: 8, overflow: "hidden",
    }}>

      {/* Header row */}
      <div onClick={onToggle} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>

        {/* Score ring */}
        <div onClick={e => { e.stopPropagation(); onSelect?.(c.symbol) }}>
          <ScoreRing score={c.breakout_watch_score} size={44} />
        </div>

        {/* Symbol + tier */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: C.text }}>{c.symbol}</span>
            {tierCfg && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
                background: tierCfg.bg, color: tierCfg.color, border: `1px solid ${tierCfg.bd}` }}>
                {tierCfg.label}
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: C.textSub }}>
            {tierCfg?.desc ?? "Monitoring"}
          </div>
        </div>

        {/* Quick pills */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end", maxWidth: 120 }}>
          <Pill label="NR7" active={!!isNR7} color={C.orange} />
          <Pill label="EMA200" active={!!c.above_ema200} color={C.green} />
          {vr >= 1.3 && <Pill label={`${vr.toFixed(1)}x vol`} active color={C.purple} />}
        </div>

        {/* Price */}
        {c.close && (
          <div style={{ textAlign: "right", flexShrink: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>₹{n(c.close).toLocaleString("en-IN")}</div>
          </div>
        )}

        {expanded ? <ChevronUp size={14} color={C.textSub} /> : <ChevronDown size={14} color={C.textSub} />}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}`, background: "#FAFAF8", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Proximity bar */}
          <ProximityBar pctBelow={n(c.pct_below_high)} />

          {/* Signal grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            {[
              { label: "Stage",      value: c.stage_label ?? (c.stage ? `Stage ${c.stage}` : "—") },
              { label: "6M momentum", value: `${n(c.momentum_6m) > 0 ? "+" : ""}${n(c.momentum_6m).toFixed(1)}%` },
              { label: "Vol ratio",  value: vr > 0 ? `${vr.toFixed(1)}x avg` : "—"          },
            ].map(item => (
              <div key={item.label} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "9px 11px" }}>
                <div style={{ fontSize: 9, color: C.textSub, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.text }}>{item.value}</div>
              </div>
            ))}
          </div>

          {/* What to do */}
          <div style={{ background: tierCfg?.bg ?? C.grayBg, border: `1px solid ${tierCfg?.bd ?? C.grayBd}`, borderRadius: 8, padding: "10px 12px" }}>
            <div style={{ fontSize: 11, color: tierCfg?.color ?? C.textSub, fontWeight: 600, marginBottom: 4 }}>
              {tier === "COILED"   ? "Action: Buy on breakout confirmation above 52W high with 1.5× volume" :
               tier === "BUILDING" ? "Action: Set price alert at 52W high. Buy on volume breakout above the level" :
               "Action: Add to watchlist. Wait for NR7 + volume setup to develop"}
            </div>
            <div style={{ fontSize: 10, color: C.textSub }}>
              {c.sector && `${c.sector} · `}Breakout Watch Score {c.breakout_watch_score}/100
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main screen ─────────────────────────────────────────────────────────────
export function BreakoutWatchScreen({ simple = false, onStockSelect }: {
  simple?: boolean; onStockSelect?: (s: string) => void;
}) {
  const [candidates, setCandidates] = useState<BreakoutCandidate[]>([])
  const [loading, setLoading]       = useState(true)
  const [expanded, setExpanded]     = useState<string | null>(null)
  const [filterTier, setFilterTier] = useState<string>("ALL")
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/breakout-watch", { cache: "no-store" })
      const json = await res.json()
      const data: BreakoutCandidate[] = (json.data ?? [])
        .filter((r: any) => r.breakout_watch_tier != null)
        .sort((a: any, b: any) => Number(b.breakout_watch_score) - Number(a.breakout_watch_score))
      setCandidates(data)
      setLastUpdate(new Date())
    } catch (e) { console.error("BreakoutWatch fetch error", e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const tierOrder: Record<string, number> = { COILED: 0, BUILDING: 1, EARLY: 2 }
  const visible = candidates
    .filter(c => filterTier === "ALL" || c.breakout_watch_tier === filterTier)
    .sort((a, b) => {
      const td = (tierOrder[a.breakout_watch_tier ?? ""] ?? 9) - (tierOrder[b.breakout_watch_tier ?? ""] ?? 9)
      if (td !== 0) return td
      return n(b.breakout_watch_score) - n(a.breakout_watch_score)
    })

  const tierCounts = candidates.reduce<Record<string, number>>((acc, c) => {
    if (c.breakout_watch_tier) acc[c.breakout_watch_tier] = (acc[c.breakout_watch_tier] || 0) + 1
    return acc
  }, {})

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Zap size={18} color={C.orange} fill={C.orange} />
              <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>
                {simple ? "About to break out" : "Breakout Watch"}
              </div>
            </div>
            <div style={{ fontSize: 11, color: C.textSub, marginTop: 2 }}>
              {simple ? "Stocks coiled before the move — BEFORE they break out" : "Stocks setting up below 52W highs — catch the coil, not the chase"}
              {lastUpdate ? ` · ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : ""}
            </div>
          </div>
          <button onClick={() => load()} style={{
            display: "flex", alignItems: "center", gap: 5, padding: "7px 12px",
            borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface,
            fontSize: 12, color: C.textSub, cursor: "pointer",
          }}>
            <RefreshCw size={12} /> Refresh
          </button>
        </div>

        {/* Tier filter */}
        <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
          {[
            { key: "ALL",      label: `All (${candidates.length})` },
            { key: "COILED",   label: `🔥 Coiled (${tierCounts.COILED ?? 0})` },
            { key: "BUILDING", label: `⚡ Building (${tierCounts.BUILDING ?? 0})` },
            { key: "EARLY",    label: `👁 Early (${tierCounts.EARLY ?? 0})` },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => setFilterTier(key)} style={{
              padding: "5px 12px", borderRadius: 20, fontSize: 11, cursor: "pointer",
              border: `1px solid ${filterTier === key ? C.orange : C.border}`,
              background: filterTier === key ? C.orangeBg : C.surface,
              color: filterTier === key ? C.orange : C.textSub,
              fontWeight: filterTier === key ? 700 : 400,
            }}>{label}</button>
          ))}
        </div>

        {/* Legend */}
        {!simple && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px", marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.text, marginBottom: 8 }}>How to read this screen</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
              {Object.entries(TIER_CFG).map(([key, cfg]) => (
                <div key={key} style={{ background: cfg.bg, border: `1px solid ${cfg.bd}`, borderRadius: 7, padding: "8px 10px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: cfg.color, marginBottom: 2 }}>{cfg.label}</div>
                  <div style={{ fontSize: 10, color: C.textSub, lineHeight: 1.4 }}>{cfg.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results */}
        {loading ? (
          [1, 2, 3].map(i => (
            <div key={i} style={{ background: C.grayBg, borderRadius: 12, height: 72, marginBottom: 8, opacity: 0.6 + i * 0.1 }} />
          ))
        ) : visible.length === 0 ? (
          <div style={{ padding: "48px 0", textAlign: "center", color: C.textSub }}>
            <TrendingUp size={32} color={C.grayBd} style={{ margin: "0 auto 12px", display: "block" }} />
            <div style={{ fontSize: 14, marginBottom: 6 }}>
              {filterTier === "ALL" ? "No breakout setups detected right now" : `No ${filterTier.toLowerCase()} tier setups`}
            </div>
            <div style={{ fontSize: 12 }}>
              {filterTier === "ALL"
                ? "Run python _scripts/generate_signals.py to refresh signals"
                : `Try the 'All' filter to see earlier-stage setups`}
            </div>
          </div>
        ) : (
          visible.map(c => (
            <CandidateCard key={c.symbol} c={c}
              expanded={expanded === c.symbol}
              onToggle={() => setExpanded(expanded === c.symbol ? null : c.symbol)}
              onSelect={onStockSelect} />
          ))
        )}

        {!simple && visible.length > 0 && (
          <div style={{ fontSize: 10, color: "#D1D5DB", textAlign: "center", marginTop: 8, lineHeight: 1.6 }}>
            Score weights: 52W-high proximity 32 · Range compression (NR7 + vol) 26 · Trend (EMA200/30) 18 · Volume building 16 · Stage 8
            <br />Not a buy signal. Confirm breakout with candle close above 52W high on 1.5× volume.
          </div>
        )}
      </div>
    </div>
  )
}
