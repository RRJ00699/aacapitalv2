"use client"
// components/features/QualityValueScreen.tsx
// The Quality + Value (GARP) screen: DNA grade (quality) × valuation percentile (price) × quarterly
// growth, across the universe, sortable and filterable. Flagship preset surfaces ≥A businesses trading
// cheap vs their own history with profit growing. Powered by /api/fundamentals/universe.
// Research signal, NOT a buy call — quality+value is a starting shortlist, not a recommendation.

import { useEffect, useMemo, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", border2: "#F1F5F9", bg: "#F7F9FC",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2",
  amber: "#D97706", blue: "#2563EB", track: "#EEF2F7",
}

const GRADE_RANK: Record<string, number> = { "AAA+": 8, AAA: 7, AA: 6, A: 5, BBB: 4, BB: 3, B: 2, Avoid: 1 }
const gradeColor = (g: string | null) => {
  if (!g) return T.textMeta
  if (g === "AAA+" || g === "AAA") return T.green
  if (g === "AA") return "#15803D"
  if (g === "A") return T.blue
  if (g === "BBB") return T.amber
  if (g === "BB") return "#EA580C"
  if (g === "B") return "#C2410C"
  return T.red
}
const valColor = (p: number | null) => (p === null ? T.textMeta : p < 30 ? T.green : p > 70 ? T.red : T.amber)
const gcol = (v: number | null) => (v === null ? T.textMeta : v >= 0 ? T.green : T.red)
const mcap = (v: number | null) => v === null ? "—" : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)}L cr` : v >= 1e3 ? `₹${(v / 1e3).toFixed(1)}k cr` : `₹${v.toFixed(0)} cr`

type SortKey = "dna_score" | "pe_percentile" | "np_yoy" | "market_cap_cr"

export default function QualityValueScreen({ onStockSelect }: { onStockSelect: (sym: string) => void }) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  // filters
  const [minGrade, setMinGrade] = useState(0)          // 0 = any, else GRADE_RANK threshold
  const [maxVal, setMaxVal] = useState(100)            // valuation percentile ceiling
  const [minGrowth, setMinGrowth] = useState<number | null>(null)
  const [sector, setSector] = useState("")
  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState<SortKey>("dna_score")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [garp, setGarp] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch("/api/fundamentals/universe", { cache: "no-store" })
      .then(r => r.json())
      .then(d => { if (d.stocks) setRows(d.stocks); else setErr(d.error || "no data") })
      .catch(e => setErr(String(e))).finally(() => setLoading(false))
  }, [])

  const sectors = useMemo(() =>
    Array.from(new Set(rows.map(r => r.sector).filter(Boolean))).sort(), [rows])

  const applyGarp = () => {
    // ≥A DNA · valuation under 40th percentile of own history · profit growing
    setGarp(true); setMinGrade(GRADE_RANK["A"]); setMaxVal(40); setMinGrowth(0); setSector(""); setSearch("")
    setSortKey("dna_score"); setSortDir("desc")
  }
  const clearAll = () => {
    setGarp(false); setMinGrade(0); setMaxVal(100); setMinGrowth(null); setSector(""); setSearch("")
  }

  const filtered = useMemo(() => {
    let r = rows.filter(s => {
      if (minGrade && (GRADE_RANK[s.grade] || 0) < minGrade) return false
      if (maxVal < 100 && (s.pe_percentile === null || s.pe_percentile > maxVal)) return false
      if (minGrowth !== null && (s.np_yoy === null || s.np_yoy < minGrowth)) return false
      if (sector && s.sector !== sector) return false
      if (search) {
        const q = search.toLowerCase()
        if (!s.symbol.toLowerCase().includes(q) && !(s.name || "").toLowerCase().includes(q)) return false
      }
      return true
    })
    const dir = sortDir === "desc" ? -1 : 1
    r = [...r].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      if (av === null) return 1
      if (bv === null) return -1
      return (av - bv) * dir
    })
    return r
  }, [rows, minGrade, maxVal, minGrowth, sector, search, sortKey, sortDir])

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => (d === "desc" ? "asc" : "desc"))
    else { setSortKey(k); setSortDir(k === "pe_percentile" ? "asc" : "desc") }
  }

  const selWrap: React.CSSProperties = { fontSize: 12, padding: "6px 8px", border: `1px solid ${T.border}`, borderRadius: 8, background: "#fff", color: T.text }
  const Th = ({ k, label, hint }: { k?: SortKey; label: string; hint?: string }) => (
    <th onClick={k ? () => toggleSort(k) : undefined}
      style={{ textAlign: k ? "right" : "left", padding: "8px 10px", fontSize: 10, fontWeight: 700, color: T.textSub,
        cursor: k ? "pointer" : "default", whiteSpace: "nowrap", userSelect: "none" }}>
      {label}{k && sortKey === k ? (sortDir === "desc" ? " ▾" : " ▴") : ""}
      {hint && <div style={{ fontWeight: 400, color: T.textMeta, fontSize: 8 }}>{hint}</div>}
    </th>
  )

  return (
    <div style={{ padding: 16 }}>
      {/* header + GARP preset */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: T.text }}>Quality + Value</div>
          <div style={{ fontSize: 11, color: T.textMeta }}>Good businesses (DNA) trading cheap vs their own history (valuation), with growing profit. A shortlist, not a buy call.</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={applyGarp} style={{ fontSize: 12, fontWeight: 700, color: "#fff", background: T.green, border: "none", borderRadius: 8, padding: "8px 12px", cursor: "pointer" }}>
            ✦ GARP preset
          </button>
          <button onClick={clearAll} style={{ fontSize: 12, fontWeight: 600, color: T.textSub, background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8, padding: "8px 12px", cursor: "pointer" }}>
            Clear
          </button>
        </div>
      </div>

      {garp && (
        <div style={{ fontSize: 11, color: T.green, background: T.greenBg, border: "1px solid #BBF7D0", borderRadius: 8, padding: "6px 10px", marginBottom: 10 }}>
          GARP preset active — ≥A DNA · valuation under 40th percentile of own history · profit growing YoY.
        </div>
      )}

      {/* filters */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <select value={minGrade} onChange={e => { setMinGrade(+e.target.value); setGarp(false) }} style={selWrap}>
          <option value={0}>DNA: any grade</option>
          <option value={GRADE_RANK["AAA"]}>DNA ≥ AAA</option>
          <option value={GRADE_RANK["AA"]}>DNA ≥ AA</option>
          <option value={GRADE_RANK["A"]}>DNA ≥ A</option>
          <option value={GRADE_RANK["BBB"]}>DNA ≥ BBB</option>
        </select>
        <select value={maxVal} onChange={e => { setMaxVal(+e.target.value); setGarp(false) }} style={selWrap}>
          <option value={100}>Valuation: any</option>
          <option value={30}>Cheap (under 30th pctile)</option>
          <option value={40}>Under 40th pctile</option>
          <option value={50}>Under median</option>
        </select>
        <select value={minGrowth ?? ""} onChange={e => { setMinGrowth(e.target.value === "" ? null : +e.target.value); setGarp(false) }} style={selWrap}>
          <option value="">Growth: any</option>
          <option value={0}>Profit growing (YoY &gt; 0)</option>
          <option value={15}>YoY &gt; 15%</option>
          <option value={30}>YoY &gt; 30%</option>
        </select>
        <select value={sector} onChange={e => setSector(e.target.value)} style={selWrap}>
          <option value="">All sectors</option>
          {sectors.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search symbol / name" style={{ ...selWrap, minWidth: 160 }} />
      </div>

      {loading && <div style={{ fontSize: 13, color: T.textMeta, padding: 20 }}>Loading universe…</div>}
      {err && <div style={{ fontSize: 13, color: T.red, padding: 20 }}>Couldn't load: {err}</div>}

      {!loading && !err && (
        <>
          <div style={{ fontSize: 11, color: T.textMeta, marginBottom: 6 }}>
            {filtered.length.toLocaleString()} match{filtered.length === 1 ? "" : "es"} · {rows.length.toLocaleString()} graded names
            {filtered.length > 200 ? " · showing top 200" : ""}
          </div>
          <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ background: T.bg, borderBottom: `1px solid ${T.border}` }}>
                  <Th label="Stock" />
                  <Th label="Sector" />
                  <Th k="market_cap_cr" label="M.Cap" />
                  <Th label="Grade" />
                  <Th k="dna_score" label="DNA" hint="quality 0-100" />
                  <Th label="P/E" />
                  <Th k="pe_percentile" label="Val %ile" hint="vs own 10yr" />
                  <Th k="np_yoy" label="Profit YoY" />
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 200).map((s, i) => (
                  <tr key={s.symbol} onClick={() => onStockSelect(s.symbol)}
                    style={{ borderBottom: `1px solid ${T.border2}`, cursor: "pointer", background: i % 2 ? "#fff" : "#FCFDFE" }}>
                    <td style={{ padding: "8px 10px" }}>
                      <div style={{ fontWeight: 700, color: T.text }}>{s.symbol}</div>
                      <div style={{ fontSize: 10, color: T.textMeta, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</div>
                    </td>
                    <td style={{ padding: "8px 10px", fontSize: 11, color: T.textSub, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.sector || "—"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: T.textSub }}>{mcap(s.market_cap_cr)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>
                      <span style={{ fontSize: 11, fontWeight: 800, color: "#fff", background: gradeColor(s.grade), padding: "2px 7px", borderRadius: 6 }}>{s.grade || "—"}</span>
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: T.text }}>{s.dna_score ?? "—"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: T.textSub }}>{s.pe === null ? "—" : s.pe.toFixed(1)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: valColor(s.pe_percentile) }}>
                      {s.pe_percentile === null ? "—" : `${s.pe_percentile.toFixed(0)}th`}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: gcol(s.np_yoy) }}>
                      {s.np_yoy === null ? "—" : `${s.np_yoy >= 0 ? "+" : ""}${s.np_yoy.toFixed(0)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && <div style={{ fontSize: 12, color: T.textMeta, padding: 20, textAlign: "center" }}>No names match these filters — loosen them or clear.</div>}
        </>
      )}
    </div>
  )
}
