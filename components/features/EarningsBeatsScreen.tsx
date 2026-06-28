"use client"
// components/features/EarningsBeatsScreen.tsx
// Leaderboard of who's beating OUR house estimate — ranks the universe by latest-quarter verdict and
// consecutive beat streak (from /api/earnings-surprise). Distinct from the "Earnings" calendar tab:
// this is a fundamentals-delivery scorecard, not an upcoming-results schedule. Research, not buy calls.

import { useEffect, useMemo, useState } from "react"

const C = {
  border: "#E5E7EB", border2: "#F1F5F9", bg: "#F7F9FC", text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2", amber: "#D97706",
}
const vcol = (v: string | null) => v === "BEAT" ? C.green : v === "MISS" ? C.red : v === "MIXED" ? C.amber : C.textSub
const vbg = (v: string | null) => v === "BEAT" ? C.greenBg : v === "MISS" ? C.redBg : "#F1F5F9"
const sp = (x: number | null) => x === null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(0)}%`

export default function EarningsBeatsScreen({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [verdict, setVerdict] = useState("")
  const [minStreak, setMinStreak] = useState(0)
  const [sector, setSector] = useState("")
  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState<"streak" | "pat_surprise_pct">("streak")

  useEffect(() => {
    setLoading(true)
    fetch("/api/earnings-surprise", { cache: "no-store" })
      .then(r => r.json()).then(d => { if (d.stocks) setRows(d.stocks); else setErr(d.error || "no data") })
      .catch(e => setErr(String(e))).finally(() => setLoading(false))
  }, [])

  const sectors = useMemo(() => Array.from(new Set(rows.map(r => r.sector).filter(Boolean))).sort(), [rows])

  const filtered = useMemo(() => {
    let r = rows.filter(s => {
      if (verdict && s.verdict !== verdict) return false
      if (minStreak && (s.streak === null || s.streak < minStreak)) return false
      if (sector && s.sector !== sector) return false
      if (search && !s.symbol.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
    return [...r].sort((a, b) => {
      const av = a[sortKey] ?? -999, bv = b[sortKey] ?? -999
      return bv - av
    })
  }, [rows, verdict, minStreak, sector, search, sortKey])

  const sel: React.CSSProperties = { fontSize: 12, padding: "6px 8px", border: `1px solid ${C.border}`, borderRadius: 8, background: "#fff", color: C.text }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>Earnings Beats</div>
          <div style={{ fontSize: 11, color: C.textMeta }}>Who's out-delivering our house estimate, and on what streak. BEAT/MISS use the model's own error band (rev ±7.5%, PAT ±25%). Not a buy call.</div>
        </div>
        <button onClick={() => { setVerdict("BEAT"); setMinStreak(2); setSortKey("streak"); setSector(""); setSearch("") }}
          style={{ fontSize: 12, fontWeight: 700, color: "#fff", background: C.green, border: "none", borderRadius: 8, padding: "8px 12px", cursor: "pointer" }}>🔥 Beat streaks</button>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <select value={verdict} onChange={e => setVerdict(e.target.value)} style={sel}>
          <option value="">Any verdict</option><option value="BEAT">Beat</option><option value="MISS">Miss</option><option value="INLINE">In-line</option>
        </select>
        <select value={minStreak} onChange={e => setMinStreak(+e.target.value)} style={sel}>
          <option value={0}>Any streak</option><option value={2}>≥ 2 beats</option><option value={3}>≥ 3 beats</option>
        </select>
        <select value={sector} onChange={e => setSector(e.target.value)} style={sel}>
          <option value="">All sectors</option>{sectors.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search symbol" style={{ ...sel, minWidth: 140 }} />
        <select value={sortKey} onChange={e => setSortKey(e.target.value as any)} style={sel}>
          <option value="streak">Sort: streak</option><option value="pat_surprise_pct">Sort: profit surprise</option>
        </select>
      </div>

      {loading && <div style={{ fontSize: 13, color: C.textMeta, padding: 20 }}>Loading earnings surprises…</div>}
      {err && <div style={{ fontSize: 13, color: C.red, padding: 20 }}>Couldn't load: {err}</div>}

      {!loading && !err && (
        <>
          <div style={{ fontSize: 11, color: C.textMeta, marginBottom: 6 }}>{filtered.length.toLocaleString()} of {rows.length.toLocaleString()} scored{filtered.length > 200 ? " · showing top 200" : ""}</div>
          <div style={{ overflowX: "auto", border: `1px solid ${C.border}`, borderRadius: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead><tr style={{ background: C.bg, borderBottom: `1px solid ${C.border}` }}>
                {["Stock", "Sector", "Quarter", "Rev surp", "Profit surp", "Verdict", "Streak"].map((h, i) => (
                  <th key={i} style={{ textAlign: i < 3 ? "left" : "right", padding: "8px 10px", fontSize: 10, fontWeight: 700, color: C.textSub, whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {filtered.slice(0, 200).map((s, i) => (
                  <tr key={s.symbol} onClick={() => onStockSelect(s.symbol)} style={{ borderBottom: `1px solid ${C.border2}`, cursor: "pointer", background: i % 2 ? "#fff" : "#FCFDFE" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text }}>{s.symbol}</td>
                    <td style={{ padding: "8px 10px", fontSize: 11, color: C.textSub, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.sector || "—"}</td>
                    <td style={{ padding: "8px 10px", fontSize: 11, color: C.textSub }}>{s.quarter || "—"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: vcol(s.revenue_verdict) }}>{sp(s.revenue_surprise_pct)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: vcol(s.pat_verdict) }}>{sp(s.pat_surprise_pct)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}><span style={{ fontSize: 10, fontWeight: 800, color: vcol(s.verdict), background: vbg(s.verdict), padding: "1px 7px", borderRadius: 5 }}>{s.verdict || "—"}</span></td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: s.streak > 0 ? C.green : s.streak < 0 ? C.red : C.textMeta }}>{s.streak > 0 ? `+${s.streak}` : s.streak}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && <div style={{ fontSize: 12, color: C.textMeta, padding: 20, textAlign: "center" }}>No names match — loosen the filters.</div>}
        </>
      )}
    </div>
  )
}
