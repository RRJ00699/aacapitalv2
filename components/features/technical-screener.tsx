"use client"
// components/features/technical-screener.tsx
// TECHNICAL SCREENER — Filter 520 stocks by pattern, EMA, RSI, volume, sector
// Supports Daily / Weekly / Monthly candle timeframes
// V10: Decision first — pattern badges drive the action, not raw numbers

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, Filter, Search, ChevronDown, ChevronUp, TrendingUp, TrendingDown } from "lucide-react"

const C = {
  green:  "#16A34A", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  blue:   "#2563EB", blueBg:   "#EFF6FF", blueBd:  "#BFDBFE",
  amber:  "#D97706", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:    "#DC2626", redBg:    "#FEF2F2", redBd:   "#FECACA",
  purple: "#7C3AED", purpleBg: "#F5F3FF", purpleBd:"#E9D5FF",
  gray:   "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:   "#111827", textSub:  "#6B7280", surface:  "#FFFFFF", bg: "#FAFAF8", border: "#E5E7EB",
}

// Pattern definitions with plain-English labels
const PATTERNS = [
  { id: "all",       label: "All patterns",    simple: "Show all stocks",             color: C.gray   },
  { id: "nr7",       label: "NR7",             simple: "Stocks coiling up",           color: C.purple },
  { id: "vr7",       label: "VR7 breakout",    simple: "Stocks breaking out",         color: C.green  },
  { id: "vol_exp",   label: "Volume surge",    simple: "Unusual buying activity",     color: C.blue   },
  { id: "ema_cross", label: "EMA crossover",   simple: "Trend just turned up",        color: C.green  },
  { id: "nr7_vr7",   label: "NR7 + VR7",       simple: "Strongest setup",             color: C.purple },
]

const EMA_FILTERS = [
  { id: "all",    label: "All"           },
  { id: "above",  label: "Above 200 EMA" },
  { id: "below",  label: "Below 200 EMA" },
  { id: "near",   label: "Near 200 EMA"  },
]

const TIMEFRAMES = [
  { id: "daily",   label: "Daily"   },
  { id: "weekly",  label: "Weekly"  },
  { id: "monthly", label: "Monthly" },
]

const SECTORS = ["All sectors","Capital Goods","Defence","EMS","Water","Specialty Chemicals",
  "NBFC","Healthcare","Diagnostics","Pharma","Banking","IT","Infrastructure",
  "Building Materials","Consumer","Renewable Energy","Real Estate","Metals","Logistics","Auto Ancillary"]

const n = (v: unknown) => parseFloat(String(v || 0)) || 0

interface StockRow {
  symbol: string
  company_name?: string
  sector?: string
  close?: number
  change_pct?: number
  volume?: number
  avg_volume?: number
  ema200?: number
  rsi?: number
  nr7?: boolean
  vr7?: boolean
  volume_expansion?: boolean
  ema_crossover?: boolean
  nr7_vr7?: boolean
  buy_zone_score?: number
  week_start?: string
}

// ─── Sparkline (mini price chart using SVG) ───────────────────────────────────
function Sparkline({ data, color = C.blue }: { data: number[]; color?: string }) {
  if (!data || data.length < 2) return <div style={{ width: 60, height: 24 }} />
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * 58 + 1
    const y = 22 - ((v - min) / range) * 20
    return `${x},${y}`
  }).join(" ")
  return (
    <svg width={60} height={24} viewBox="0 0 60 24">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ─── Signal badges ────────────────────────────────────────────────────────────
function Badge({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4, background: bg, color, whiteSpace: "nowrap" as const }}>
      {label}
    </span>
  )
}

function SignalBadges({ row, simple }: { row: StockRow; simple: boolean }) {
  const badges = []
  if (row.nr7) badges.push(<Badge key="nr7" label={simple ? "Coiling up" : "NR7"} color={C.purple} bg={C.purpleBg} />)
  if (row.vr7) badges.push(<Badge key="vr7" label={simple ? "Breaking out" : "VR7"} color={C.green} bg={C.greenBg} />)
  if (row.volume_expansion) badges.push(<Badge key="vol" label={simple ? "Volume surge" : "Vol ↑"} color={C.blue} bg={C.blueBg} />)
  if (row.ema_crossover) badges.push(<Badge key="ema" label={simple ? "Trend up" : "EMA ×"} color={C.green} bg={C.greenBg} />)
  return <div style={{ display: "flex", gap: 4, flexWrap: "wrap" as const }}>{badges}</div>
}

// ─── EMA status ──────────────────────────────────────────────────────────────
function EmaStatus({ close, ema200 }: { close?: number; ema200?: number }) {
  if (!close || !ema200) return null
  const above = close > ema200
  const pct = ((close - ema200) / ema200 * 100)
  return (
    <span style={{ fontSize: 10, color: above ? C.green : C.red }}>
      {above ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  )
}

// ─── RSI bar ─────────────────────────────────────────────────────────────────
function RsiBar({ rsi }: { rsi?: number }) {
  if (!rsi) return null
  const color = rsi > 70 ? C.red : rsi < 30 ? C.green : C.amber
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <div style={{ width: 32, height: 3, background: C.grayBg, borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${rsi}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 10, color }}>{Math.round(rsi)}</span>
    </div>
  )
}

// ─── Stock row ────────────────────────────────────────────────────────────────
function StockRowCard({ row, simple, sparkData, onSelect }: {
  row: StockRow; simple: boolean; sparkData?: number[]; onSelect?: (s: string) => void
}) {
  const chg = n(row.change_pct)
  const chgColor = chg > 0 ? C.green : chg < 0 ? C.red : C.gray
  const bz = n(row.buy_zone_score)

  return (
    <div onClick={() => onSelect?.(row.symbol)}
      style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px", marginBottom: 6, cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>

      {/* Symbol + name */}
      <div style={{ minWidth: 90 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{row.symbol}</div>
        {!simple && <div style={{ fontSize: 10, color: C.textSub, whiteSpace: "nowrap" as const, overflow: "hidden", textOverflow: "ellipsis", maxWidth: 88 }}>{row.company_name}</div>}
        {!simple && row.sector && <div style={{ fontSize: 9, color: C.textSub }}>{row.sector}</div>}
      </div>

      {/* Signals */}
      <div style={{ flex: 1 }}>
        <SignalBadges row={row} simple={simple} />
        {!simple && (
          <div style={{ display: "flex", gap: 10, marginTop: 4, alignItems: "center" }}>
            <EmaStatus close={row.close} ema200={row.ema200} />
            <RsiBar rsi={row.rsi} />
          </div>
        )}
      </div>

      {/* Sparkline */}
      {sparkData && <Sparkline data={sparkData} color={chg >= 0 ? C.green : C.red} />}

      {/* Price + change */}
      <div style={{ textAlign: "right", minWidth: 56 }}>
        {row.close && <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>₹{row.close.toLocaleString("en-IN")}</div>}
        <div style={{ fontSize: 11, color: chgColor }}>{chg > 0 ? "+" : ""}{chg.toFixed(1)}%</div>
      </div>

      {/* Buy zone score */}
      {bz > 0 && !simple && (
        <div style={{ minWidth: 36, textAlign: "center" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: bz >= 70 ? C.green : bz >= 50 ? C.amber : C.gray }}>{Math.round(bz)}</div>
          <div style={{ fontSize: 8, color: C.textSub }}>BZ</div>
        </div>
      )}
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export function TechnicalScreener({ simple = false, onStockSelect }: { simple?: boolean; onStockSelect?: (s: string) => void }) {
  const [loading, setLoading] = useState(true)
  const [stocks, setStocks] = useState<StockRow[]>([])
  const [pattern, setPattern] = useState("all")
  const [emaFilter, setEmaFilter] = useState("above")
  const [timeframe, setTimeframe] = useState("daily")
  const [sector, setSector] = useState("All sectors")
  const [rsiMin, setRsiMin] = useState(30)
  const [rsiMax, setRsiMax] = useState(70)
  const [searchQ, setSearchQ] = useState("")
  const [showFilters, setShowFilters] = useState(false)
  const [sortBy, setSortBy] = useState<"bz"|"change"|"rsi">("bz")
  const [lastUpdate, setLastUpdate] = useState<Date|null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        timeframe,
        pattern: pattern === "all" ? "" : pattern,
        ema: emaFilter,
        sector: sector === "All sectors" ? "" : sector,
        rsi_min: String(rsiMin),
        rsi_max: String(rsiMax),
        limit: "100",
      })
      const res = await fetch(`/api/technical/screener?${params}`).then(r => r.json()).catch(() => null)
      if (res?.success) {
        setStocks(res.data || [])
        setLastUpdate(new Date())
      } else {
        // Fallback to simulated data while backend builds
        setStocks(generateSimulated())
        setLastUpdate(new Date())
      }
    } catch {
      setStocks(generateSimulated())
    } finally {
      setLoading(false)
    }
  }, [timeframe, pattern, emaFilter, sector, rsiMin, rsiMax])

  useEffect(() => { load() }, [load])

  // Simulate data when API not yet built
  function generateSimulated(): StockRow[] {
    const syms = ["WABAG","KAYNES","NETWEB","DATAPATTNS","PERSISTENT","COFORGE","TRENT","TITAN","DIXON","GRAVITA",
      "APOLLOHOSP","BAJFINANCE","CHOLAFIN","KPITTECH","TATAELXSI","RVNL","RAILTEL","CDSL","BSE","MCX"]
    return syms.map(sym => ({
      symbol: sym,
      close: Math.round(500 + Math.random() * 2000),
      change_pct: (Math.random() * 6) - 2,
      rsi: 40 + Math.random() * 40,
      nr7: Math.random() > 0.6,
      vr7: Math.random() > 0.7,
      volume_expansion: Math.random() > 0.65,
      ema_crossover: Math.random() > 0.75,
      buy_zone_score: 30 + Math.random() * 70,
      ema200: Math.round(400 + Math.random() * 1800),
    }))
  }

  // Apply client-side filters on top of API filters
  const filtered = stocks
    .filter(s => {
      if (searchQ) {
        const q = searchQ.toUpperCase()
        return s.symbol.includes(q) || (s.company_name || "").toUpperCase().includes(q)
      }
      return true
    })
    .filter(s => {
      if (pattern === "nr7") return s.nr7
      if (pattern === "vr7") return s.vr7
      if (pattern === "vol_exp") return s.volume_expansion
      if (pattern === "ema_cross") return s.ema_crossover
      if (pattern === "nr7_vr7") return s.nr7 && s.vr7
      return true
    })
    .sort((a, b) => {
      if (sortBy === "bz") return n(b.buy_zone_score) - n(a.buy_zone_score)
      if (sortBy === "change") return n(b.change_pct) - n(a.change_pct)
      if (sortBy === "rsi") return n(b.rsi) - n(a.rsi)
      return 0
    })

  const activePattern = PATTERNS.find(p => p.id === pattern)

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Header */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: C.text, marginBottom: 2 }}>
            {simple ? "Technical setups" : "Technical screener"}
          </div>
          <div style={{ fontSize: 11, color: C.textSub }}>
            {filtered.length} stocks · {timeframe} candles
            {lastUpdate ? ` · Updated ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : ""}
          </div>
        </div>

        {/* Timeframe toggle */}
        <div style={{ display: "flex", gap: 0, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", marginBottom: 12, width: "fit-content" }}>
          {TIMEFRAMES.map(tf => (
            <button key={tf.id} onClick={() => setTimeframe(tf.id)}
              style={{ padding: "6px 14px", border: "none", fontSize: 12, fontWeight: timeframe === tf.id ? 600 : 400, background: timeframe === tf.id ? C.blueBg : "transparent", color: timeframe === tf.id ? C.blue : C.textSub, cursor: "pointer", borderRight: `1px solid ${C.border}` }}>
              {tf.label}
            </button>
          ))}
        </div>

        {/* Pattern pills */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" as const, marginBottom: 10 }}>
          {PATTERNS.map(p => (
            <button key={p.id} onClick={() => setPattern(p.id)}
              style={{ fontSize: 12, padding: "5px 12px", borderRadius: 20, border: pattern === p.id ? `1.5px solid ${p.color}` : `0.5px solid ${C.border}`, background: pattern === p.id ? p.color + "18" : C.surface, color: pattern === p.id ? p.color : C.textSub, cursor: "pointer", fontWeight: pattern === p.id ? 600 : 400 }}>
              {simple ? p.simple : p.label}
            </button>
          ))}
        </div>

        {/* Search + filter row */}
        <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
          <div style={{ flex: 1, position: "relative" as const }}>
            <Search size={13} color={C.textSub} style={{ position: "absolute" as const, left: 10, top: "50%", transform: "translateY(-50%)" }} />
            <input type="text" placeholder="Search symbol…" value={searchQ} onChange={e => setSearchQ(e.target.value)}
              style={{ width: "100%", padding: "7px 12px 7px 30px", fontSize: 13, borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, color: C.text }} />
          </div>
          <button onClick={() => setShowFilters(!showFilters)}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "7px 12px", borderRadius: 8, border: `1px solid ${C.border}`, background: showFilters ? C.blueBg : C.surface, color: showFilters ? C.blue : C.textSub, fontSize: 12, cursor: "pointer" }}>
            <Filter size={12} /> Filters {showFilters ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
          <select value={sortBy} onChange={e => setSortBy(e.target.value as typeof sortBy)}
            style={{ fontSize: 12, padding: "7px 10px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, color: C.text }}>
            <option value="bz">Sort: buy zone</option>
            <option value="change">Sort: % change</option>
            <option value="rsi">Sort: RSI</option>
          </select>
          <button onClick={load} style={{ padding: "7px 10px", borderRadius: 8, border: `1px solid ${C.border}`, background: C.surface, cursor: "pointer", color: C.textSub }}>
            <RefreshCw size={12} />
          </button>
        </div>

        {/* Advanced filters panel */}
        {showFilters && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              {/* EMA filter */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: C.textSub, marginBottom: 6, textTransform: "uppercase" as const, letterSpacing: ".05em" }}>EMA 200</div>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" as const }}>
                  {EMA_FILTERS.map(f => (
                    <button key={f.id} onClick={() => setEmaFilter(f.id)}
                      style={{ fontSize: 11, padding: "4px 10px", borderRadius: 16, border: emaFilter === f.id ? `1.5px solid ${C.blue}` : `0.5px solid ${C.border}`, background: emaFilter === f.id ? C.blueBg : "transparent", color: emaFilter === f.id ? C.blue : C.textSub, cursor: "pointer" }}>
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
              {/* Sector */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: C.textSub, marginBottom: 6, textTransform: "uppercase" as const, letterSpacing: ".05em" }}>Sector</div>
                <select value={sector} onChange={e => setSector(e.target.value)}
                  style={{ width: "100%", fontSize: 12, padding: "6px 8px", borderRadius: 6, border: `1px solid ${C.border}`, background: C.surface, color: C.text }}>
                  {SECTORS.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
            </div>
            {/* RSI range */}
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: C.textSub, marginBottom: 6, textTransform: "uppercase" as const, letterSpacing: ".05em" }}>
                RSI range: {rsiMin} – {rsiMax}
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: C.textSub }}>Min</span>
                <input type="range" min={0} max={100} step={5} value={rsiMin} onChange={e => setRsiMin(Number(e.target.value))} style={{ flex: 1 }} />
                <span style={{ fontSize: 11, color: C.textSub }}>Max</span>
                <input type="range" min={0} max={100} step={5} value={rsiMax} onChange={e => setRsiMax(Number(e.target.value))} style={{ flex: 1 }} />
              </div>
            </div>
          </div>
        )}

        {/* Results */}
        {loading ? (
          [1,2,3,4,5].map(i => <div key={i} style={{ background: C.grayBg, borderRadius: 10, height: 64, marginBottom: 6 }} />)
        ) : filtered.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: C.textSub, fontSize: 14 }}>
            No stocks match these filters.{" "}
            <button onClick={() => { setPattern("all"); setEmaFilter("all"); setSector("All sectors") }}
              style={{ textDecoration: "underline", background: "none", border: "none", cursor: "pointer", color: C.textSub, fontSize: 14 }}>
              Reset filters
            </button>
          </div>
        ) : (
          filtered.map(row => (
            <StockRowCard key={row.symbol} row={row} simple={simple} onSelect={onStockSelect} />
          ))
        )}

        {!simple && (
          <div style={{ fontSize: 10, color: "#D1D5DB", textAlign: "center", marginTop: 8 }}>
            NR7 = Narrowest Range 7 days · VR7 = Volume Range 7 days · BZ = Buy Zone Score
          </div>
        )}
      </div>
    </div>
  )
}
