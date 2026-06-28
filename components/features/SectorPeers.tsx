"use client"
// components/features/SectorPeers.tsx
// Where this stock sits WITHIN its sector on quality (DNA), value (P/E), and growth — turning
// absolute numbers into relative judgement. From /api/fundamentals/universe. Research/context.

import { useEffect, useMemo, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", bg: "#F7F9FC",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", blue: "#2563EB", amber: "#D97706",
}
const gradeColor = (g: string | null) => {
  if (!g) return T.textMeta
  if (g === "AAA+" || g === "AAA") return T.green
  if (g === "AA") return "#15803D"; if (g === "A") return T.blue
  if (g === "BBB") return T.amber; if (g === "BB") return "#EA580C"; if (g === "B") return "#C2410C"
  return T.red
}

// percentile of `val` within arr (higher value -> higher percentile)
function pctileOf(val: number | null, arr: number[]): number | null {
  if (val === null || arr.length < 2) return null
  return (arr.filter(x => x <= val).length / arr.length) * 100
}

export default function SectorPeers({ symbol, onStockSelect }: { symbol: string; onStockSelect?: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch("/api/fundamentals/universe", { cache: "force-cache" })
      .then(r => r.json()).then(d => setRows(d.stocks || [])).catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [])

  const view = useMemo(() => {
    const me = rows.find(r => r.symbol === symbol.toUpperCase())
    if (!me || !me.sector) return null
    const peers = rows.filter(r => r.sector === me.sector)
    if (peers.length < 3) return { me, peers, thin: true } as any

    const dnaArr = peers.map(p => p.dna_score).filter((x): x is number => x !== null)
    const peArr = peers.map(p => p.pe).filter((x): x is number => x !== null)
    const npArr = peers.map(p => p.np_yoy).filter((x): x is number => x !== null)

    const dnaPct = pctileOf(me.dna_score, dnaArr)            // higher = better quality
    const pePct = pctileOf(me.pe, peArr)                     // higher = pricier than peers
    const npPct = pctileOf(me.np_yoy, npArr)                 // higher = faster growth

    const topPeers = [...peers].filter(p => p.symbol !== me.symbol && p.dna_score !== null)
      .sort((a, b) => b.dna_score - a.dna_score).slice(0, 5)

    return { me, peers, dnaPct, pePct, npPct, topPeers, n: peers.length, thin: false }
  }, [rows, symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Loading sector peers…</div>
  if (!view) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>No sector mapping for this name.</div>
  if (view.thin) return <div style={{ fontSize: 12, color: T.textSub, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 12px" }}>Too few graded peers in {view.me.sector} to rank ({view.peers.length}).</div>

  const { me, dnaPct, pePct, npPct, topPeers, n } = view as any
  const top = (p: number | null) => (p === null ? "—" : `top ${Math.max(1, Math.round(100 - p))}%`)
  const cheaper = (p: number | null) => (p === null ? "—" : `cheaper than ${Math.round(100 - p)}%`)

  const Stat = ({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) => (
    <div style={{ flex: "1 1 100px", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "8px 10px" }}>
      <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 9, color: T.textMeta }}>{sub}</div>
    </div>
  )

  return (
    <div>
      <div style={{ fontSize: 11, color: T.textSub, marginBottom: 8 }}>
        Within <b style={{ color: T.text }}>{me.sector}</b> ({n} graded peers)
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        <Stat label="QUALITY (DNA)" value={top(dnaPct)} sub={`grade ${me.grade ?? "—"} · score ${me.dna_score ?? "—"}`} color={dnaPct !== null && dnaPct >= 70 ? T.green : T.text} />
        <Stat label="VALUE (P/E)" value={cheaper(pePct)} sub={`P/E ${me.pe === null ? "—" : me.pe.toFixed(1)} of sector`} color={pePct !== null && pePct <= 30 ? T.green : pePct !== null && pePct >= 70 ? T.red : T.text} />
        <Stat label="GROWTH (YoY)" value={top(npPct)} sub={`profit ${me.np_yoy === null ? "—" : (me.np_yoy >= 0 ? "+" : "") + me.np_yoy.toFixed(0) + "%"}`} color={npPct !== null && npPct >= 70 ? T.green : T.text} />
      </div>

      <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 4 }}>TOP PEERS BY DNA</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {topPeers.map((p: any) => (
          <button key={p.symbol} onClick={() => onStockSelect && onStockSelect(p.symbol)}
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: T.text, background: "#fff",
              border: `1px solid ${T.border}`, borderRadius: 8, padding: "4px 8px", cursor: onStockSelect ? "pointer" : "default" }}>
            <span style={{ fontSize: 9, fontWeight: 800, color: "#fff", background: gradeColor(p.grade), padding: "1px 5px", borderRadius: 4 }}>{p.grade}</span>
            {p.symbol}
            <span style={{ color: T.textMeta }}>{p.dna_score}</span>
          </button>
        ))}
      </div>

      <div style={{ fontSize: 9, color: T.textMeta, marginTop: 8, lineHeight: 1.5 }}>
        Percentiles are within this sector only. "Cheaper than X%" uses current P/E across sector peers.
        Relative context to judge if a name is strong/cheap <i>for its sector</i> — not a buy call.
      </div>
    </div>
  )
}
