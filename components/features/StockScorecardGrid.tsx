"use client"
// components/features/StockScorecardGrid.tsx
// The funnel's front door. Renders the whole universe from /api/stocks as
// decomposed-score rows (the SAME 4 sub-scores as the workboard verdict), with
// sort by any sub-score and filters (search, sector, 💎-only, min convergence).
// Drop-in replacement for <StocksDiscovery>: same `onStockSelect` prop.
// Research signal, not a buy call.

import { useEffect, useMemo, useState } from "react"
import { Search, RefreshCw, ChevronRight } from "lucide-react"

const T = {
  bg: "#FAFAF8", surface: "#FFFFFF", border: "#E5E7EB", hover: "#F8FAFC",
  text: "#111827", textSub: "#374151", meta: "#6B7280",
  green: "#16A34A", teal: "#0D9488", amber: "#D97706", red: "#DC2626",
  blue: "#2563EB", purple: "#7C3AED", grayBg: "#F3F4F6",
}
const scoreColor = (s: number | null) =>
  s === null ? T.meta : s >= 80 ? T.green : s >= 65 ? T.teal : s >= 50 ? T.amber : T.red
const inr = (cr: number | null) =>
  cr === null ? "—" : cr >= 100000 ? `₹${(cr / 100000).toFixed(2)}L cr` : cr >= 1000 ? `₹${(cr / 1000).toFixed(1)}k cr` : `₹${Math.round(cr)} cr`

function Ring({ score, size = 40 }: { score: number | null; size?: number }) {
  const v = score ?? 0
  const r = (size - 5) / 2, circ = 2 * Math.PI * r, dash = Math.min(1, v / 100) * circ, col = scoreColor(score)
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={T.border} strokeWidth={3.5} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={3.5}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: 11, fontWeight: 800, fill: col }}>{score === null ? "—" : score}</text>
    </svg>
  )
}

function Sub({ label, score }: { label: string; score: number | null }) {
  const col = scoreColor(score)
  return (
    <div title={label} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, minWidth: 30 }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: col, lineHeight: 1 }}>{score === null ? "—" : score}</div>
      <div style={{ fontSize: 8, fontWeight: 700, color: T.meta, letterSpacing: "0.04em" }}>{label}</div>
    </div>
  )
}

const SORTS: { key: string; label: string }[] = [
  { key: "convergence", label: "Overall" },
  { key: "quality", label: "Quality" },
  { key: "smartMoney", label: "Smart money" },
  { key: "valuation", label: "Valuation" },
  { key: "momentum", label: "Momentum" },
  { key: "market_cap", label: "Market cap" },
]

export default function StockScorecardGrid({ onStockSelect }: { onStockSelect: (sym: string) => void }) {
  const [all, setAll] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const [q, setQ] = useState("")
  const [sortKey, setSortKey] = useState("convergence")
  const [sector, setSector] = useState("All")
  const [gemOnly, setGemOnly] = useState(false)
  const [minConv, setMinConv] = useState(0)

  const load = () => {
    setLoading(true); setErr(null)
    fetch("/api/stocks", { cache: "no-store" })
      .then(r => r.json())
      .then(d => { if (d.ok) setAll(d.stocks || []); else setErr(d.error || "failed"); setLoading(false) })
      .catch(e => { setErr(String(e)); setLoading(false) })
  }
  useEffect(load, [])

  const sectors = useMemo(
    () => ["All", ...Array.from(new Set(all.map(s => s.industry).filter(Boolean))).sort()],
    [all]
  )

  const view = useMemo(() => {
    const needle = q.trim().toUpperCase()
    let rows = all.filter(s => {
      if (gemOnly && !s.has_conviction) return false
      if (sector !== "All" && s.industry !== sector) return false
      if (minConv && (s.convergence ?? 0) < minConv) return false
      if (needle && !(`${s.symbol} ${s.name ?? ""}`.toUpperCase().includes(needle))) return false
      return true
    })
    rows = rows.sort((a, b) => (b[sortKey] ?? -1) - (a[sortKey] ?? -1))
    return rows
  }, [all, q, sortKey, sector, gemOnly, minConv])

  const shown = view.slice(0, 150)

  const ctrl: React.CSSProperties = {
    fontSize: 12, padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`,
    background: T.surface, color: T.text, outline: "none",
  }

  return (
    <div style={{ background: T.bg, minHeight: "100%", padding: "14px 16px" }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: T.text }}>Stocks · Scorecard</div>
          <div style={{ fontSize: 11, color: T.meta }}>
            {loading ? "Scoring the universe…" : `${view.length.toLocaleString()} of ${all.length.toLocaleString()} · same 4 sub-scores as the workboard`}
          </div>
        </div>
        <button onClick={load} title="Refresh" style={{ ...ctrl, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* controls */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <div style={{ position: "relative", flex: "1 1 200px", minWidth: 160 }}>
          <Search size={13} style={{ position: "absolute", left: 9, top: 9, color: T.meta }} />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search symbol or name"
            style={{ ...ctrl, width: "100%", paddingLeft: 28 }} />
        </div>
        <select value={sortKey} onChange={e => setSortKey(e.target.value)} style={ctrl}>
          {SORTS.map(s => <option key={s.key} value={s.key}>Sort: {s.label}</option>)}
        </select>
        <select value={sector} onChange={e => setSector(e.target.value)} style={{ ...ctrl, maxWidth: 180 }}>
          {sectors.map(s => <option key={s} value={s}>{s === "All" ? "All sectors" : s}</option>)}
        </select>
        {[0, 50, 65, 75].map(v => (
          <button key={v} onClick={() => setMinConv(v)}
            style={{ ...ctrl, cursor: "pointer", fontWeight: 700,
              background: minConv === v ? T.text : T.surface, color: minConv === v ? "#fff" : T.textSub }}>
            {v === 0 ? "All" : `${v}+`}
          </button>
        ))}
        <button onClick={() => setGemOnly(g => !g)}
          style={{ ...ctrl, cursor: "pointer", fontWeight: 700,
            background: gemOnly ? T.purple : T.surface, color: gemOnly ? "#fff" : T.textSub,
            borderColor: gemOnly ? T.purple : T.border }}>
          💎 Conviction
        </button>
      </div>

      {err && <div style={{ fontSize: 12, color: T.red, padding: 12 }}>Couldn’t load: {err}</div>}

      {/* column hint */}
      {!loading && !err && shown.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 16px 6px", fontSize: 8, fontWeight: 700, color: T.meta, letterSpacing: "0.04em" }}>
          <span style={{ width: 40 }} /><span style={{ flex: 1 }} />
          <span style={{ width: 30, textAlign: "center" }}>QLTY</span>
          <span style={{ width: 30, textAlign: "center" }}>SMART</span>
          <span style={{ width: 30, textAlign: "center" }}>VAL</span>
          <span style={{ width: 30, textAlign: "center" }}>MOM</span>
          <span style={{ width: 16 }} />
        </div>
      )}

      {/* rows */}
      <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 14, overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: 24, fontSize: 12, color: T.meta }}>Computing scores from your fundamentals…</div>
        ) : shown.length === 0 ? (
          <div style={{ padding: 24, fontSize: 12, color: T.meta }}>No stocks match these filters.</div>
        ) : shown.map(s => (
          <div key={s.symbol} onClick={() => onStockSelect(s.symbol)}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px", cursor: "pointer", borderBottom: `1px solid ${T.grayBg}` }}
            onMouseEnter={e => (e.currentTarget.style.background = T.hover)}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
            <Ring score={s.convergence} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: T.text }}>{s.symbol}</span>
                {s.has_conviction && <span style={{ fontSize: 11 }} title={`${s.conviction_funds} high-conviction fund(s)`}>💎</span>}
                <span style={{ fontSize: 10, color: T.meta, fontWeight: 600 }}>{inr(s.market_cap)}</span>
              </div>
              <div style={{ fontSize: 10.5, color: T.meta, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 280 }}>
                {s.read}
              </div>
            </div>
            <Sub label="Q" score={s.quality} />
            <Sub label="SM" score={s.smartMoney} />
            <Sub label="V" score={s.valuation} />
            <Sub label="M" score={s.momentum} />
            <ChevronRight size={15} color={T.meta} />
          </div>
        ))}
      </div>

      {view.length > shown.length && (
        <div style={{ textAlign: "center", fontSize: 11, color: T.meta, padding: "10px 0" }}>
          Showing top {shown.length} of {view.length.toLocaleString()} — narrow with filters to see more.
        </div>
      )}
      <div style={{ fontSize: 9, color: T.meta, textAlign: "center", padding: "4px 0 2px" }}>
        Research signal, not a buy call. Tap a row for the full workboard.
      </div>
    </div>
  )
}
