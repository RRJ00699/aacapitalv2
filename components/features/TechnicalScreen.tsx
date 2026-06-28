"use client"
// components/features/TechnicalScreen.tsx
// Screen/rank the universe on technical descriptors (from /api/technical-features): relative strength,
// RVOL, volatility, Wyckoff stage, breakout-watch. Includes the validated REGIME-GATED BREAKOUT preset
// (breakout-watch setups, armed only when /api/market-regime says the market is in an uptrend — the one
// edge that survived backtesting, ~59%, regime-dependent). Descriptive ranking, not buy calls.

import { useEffect, useMemo, useState } from "react"

const T = {
  border: "#E5E7EB", border2: "#F1F5F9", bg: "#F7F9FC", text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2", amber: "#D97706", blue: "#2563EB",
}
const rcol = (p: number | null) => p === null ? T.textMeta : p >= 70 ? T.green : p >= 40 ? T.amber : T.red
const gcol = (v: number | null) => v === null ? T.textMeta : v >= 0 ? T.green : T.red

type SortKey = "rs_score" | "rvol" | "vol_pctile" | "pct_from_52wh" | "breakout_watch_score"

export default function TechnicalScreen({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [regime, setRegime] = useState<{ regime: string | null; breadth: number | null }>({ regime: null, breadth: null })

  const [minRS, setMinRS] = useState(0)
  const [minRvol, setMinRvol] = useState(0)
  const [stage, setStage] = useState("")
  const [sector, setSector] = useState("")
  const [search, setSearch] = useState("")
  const [breakoutOnly, setBreakoutOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>("rs_score")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")

  useEffect(() => {
    setLoading(true)
    fetch("/api/technical-features", { cache: "no-store" })
      .then(r => r.json()).then(d => { if (d.stocks) setRows(d.stocks); else setErr(d.error || "no data") })
      .catch(e => setErr(String(e))).finally(() => setLoading(false))
    fetch("/api/market-regime").then(r => r.json()).then(d => setRegime({ regime: d.regime ?? null, breadth: d.breadth ?? null })).catch(() => {})
  }, [])

  const sectors = useMemo(() => Array.from(new Set(rows.map(r => r.sector).filter(Boolean))).sort(), [rows])
  const stages = useMemo(() => Array.from(new Set(rows.map(r => r.stage).filter(Boolean))).sort(), [rows])
  const armed = regime.regime ? /up|bull/i.test(regime.regime) : null

  const applyLeaders = () => {
    setBreakoutOnly(false); setMinRS(80); setStage(""); setSector(""); setSearch("")
    setSortKey("rs_score"); setSortDir("desc")
  }
  const clearAll = () => { setBreakoutOnly(false); setMinRS(0); setMinRvol(0); setStage(""); setSector(""); setSearch("") }

  const filtered = useMemo(() => {
    let r = rows.filter(s => {
      if (minRS && (s.rs_score === null || s.rs_score < minRS)) return false
      if (minRvol && (s.rvol === null || s.rvol < minRvol)) return false
      if (stage && s.stage !== stage) return false
      if (sector && s.sector !== sector) return false
      if (breakoutOnly && !(s.breakout_watch_tier && /build|high|strong/i.test(s.breakout_watch_tier))) return false
      if (search) {
        const q = search.toLowerCase()
        if (!s.symbol.toLowerCase().includes(q)) return false
      }
      return true
    })
    const dir = sortDir === "desc" ? -1 : 1
    return [...r].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      if (av === null) return 1; if (bv === null) return -1
      return (av - bv) * dir
    })
  }, [rows, minRS, minRvol, stage, sector, search, breakoutOnly, sortKey, sortDir])

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => d === "desc" ? "asc" : "desc")
    else { setSortKey(k); setSortDir(k === "pct_from_52wh" ? "desc" : "desc") }
  }
  const sel: React.CSSProperties = { fontSize: 12, padding: "6px 8px", border: `1px solid ${T.border}`, borderRadius: 8, background: "#fff", color: T.text }
  const Th = ({ k, label, hint }: { k?: SortKey; label: string; hint?: string }) => (
    <th onClick={k ? () => toggleSort(k) : undefined} style={{ textAlign: k ? "right" : "left", padding: "8px 10px", fontSize: 10, fontWeight: 700, color: T.textSub, cursor: k ? "pointer" : "default", whiteSpace: "nowrap", userSelect: "none" }}>
      {label}{k && sortKey === k ? (sortDir === "desc" ? " ▾" : " ▴") : ""}{hint && <div style={{ fontWeight: 400, color: T.textMeta, fontSize: 8 }}>{hint}</div>}
    </th>
  )

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: T.text }}>Relative Strength</div>
          <div style={{ fontSize: 11, color: T.textMeta }}>Which stocks are leading the market — RS rank vs the universe & their sector, plus volume. Ranks are descriptors, not buy calls.</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {armed !== null && (
            <span style={{ fontSize: 11, fontWeight: 800, color: armed ? T.green : T.red, background: armed ? T.greenBg : T.redBg, padding: "4px 10px", borderRadius: 8 }}>
              {armed ? "● Regime: ARMED" : "● Regime: MUTED"}{regime.breadth !== null ? ` (${Math.round(regime.breadth)}% >200DMA)` : ""}
            </span>
          )}
          <button onClick={applyLeaders} style={{ fontSize: 12, fontWeight: 700, color: "#fff", background: T.green, border: "none", borderRadius: 8, padding: "8px 12px", cursor: "pointer" }}>★ Market Leaders</button>
          <button onClick={clearAll} style={{ fontSize: 12, fontWeight: 600, color: T.textSub, background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8, padding: "8px 12px", cursor: "pointer" }}>Clear</button>
        </div>
      </div>

      {minRS >= 80 && (
        <div style={{ fontSize: 11, color: T.green, background: T.greenBg, border: "1px solid #BBF7D0", borderRadius: 8, padding: "6px 10px", marginBottom: 10 }}>
          Market leaders — RS ≥ {minRS} (outperforming {minRS}%+ of the universe).{armed === false ? " Note: market regime is MUTED, so leadership may be narrow — size accordingly." : ""}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <select value={minRS} onChange={e => { setMinRS(+e.target.value); setBreakoutOnly(false) }} style={sel}>
          <option value={0}>RS: any</option><option value={60}>RS ≥ 60</option><option value={80}>RS ≥ 80 (strong)</option><option value={90}>RS ≥ 90 (leaders)</option>
        </select>
        <select value={minRvol} onChange={e => setMinRvol(+e.target.value)} style={sel}>
          <option value={0}>Volume: any</option><option value={1.5}>RVOL ≥ 1.5×</option><option value={2}>RVOL ≥ 2×</option><option value={3}>RVOL ≥ 3×</option>
        </select>
        <select value={stage} onChange={e => setStage(e.target.value)} style={sel}>
          <option value="">Any stage</option>{stages.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={sector} onChange={e => setSector(e.target.value)} style={sel}>
          <option value="">All sectors</option>{sectors.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search symbol" style={{ ...sel, minWidth: 140 }} />
      </div>

      {loading && <div style={{ fontSize: 13, color: T.textMeta, padding: 20 }}>Loading technical store…</div>}
      {err && <div style={{ fontSize: 13, color: T.red, padding: 20 }}>Couldn't load: {err}</div>}

      {!loading && !err && (
        <>
          <div style={{ fontSize: 11, color: T.textMeta, marginBottom: 6 }}>{filtered.length.toLocaleString()} match{filtered.length === 1 ? "" : "es"} · {rows.length.toLocaleString()} scored{filtered.length > 200 ? " · showing top 200" : ""}</div>
          <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead><tr style={{ background: T.bg, borderBottom: `1px solid ${T.border}` }}>
                <Th label="Stock" /><Th label="Sector" />
                <Th k="rs_score" label="RS" hint="vs universe" />
                <Th k="rvol" label="RVOL" />
                <Th k="vol_pctile" label="Vol %ile" />
                <Th label="Stage" />
                <Th k="breakout_watch_score" label="Breakout" />
                <Th k="pct_from_52wh" label="52wH" hint="% away" />
              </tr></thead>
              <tbody>
                {filtered.slice(0, 200).map((s, i) => (
                  <tr key={s.symbol} onClick={() => onStockSelect(s.symbol)} style={{ borderBottom: `1px solid ${T.border2}`, cursor: "pointer", background: i % 2 ? "#fff" : "#FCFDFE" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: T.text }}>{s.symbol}</td>
                    <td style={{ padding: "8px 10px", fontSize: 11, color: T.textSub, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.sector || "—"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: rcol(s.rs_score) }}>{s.rs_score === null ? "—" : Math.round(s.rs_score)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: s.rvol >= 2 ? T.blue : T.textSub, fontWeight: s.rvol >= 2 ? 700 : 400 }}>{s.rvol === null ? "—" : `${s.rvol.toFixed(1)}×`}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: T.textSub }}>{s.vol_pctile === null ? "—" : Math.round(s.vol_pctile)}</td>
                    <td style={{ padding: "8px 10px", fontSize: 10, color: T.textSub, maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.stage || "—"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>{s.breakout_watch_score === null ? "—" : <span style={{ fontWeight: 700, color: s.breakout_watch_score >= 60 ? T.green : T.textSub }}>{s.breakout_watch_score}</span>}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: gcol(s.pct_from_52wh) }}>{s.pct_from_52wh === null ? "—" : `${s.pct_from_52wh.toFixed(0)}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && <div style={{ fontSize: 12, color: T.textMeta, padding: 20, textAlign: "center" }}>No names match — loosen the filters.</div>}
        </>
      )}
    </div>
  )
}
