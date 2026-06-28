"use client"
// components/features/EarningsSurprise.tsx
// Did this stock beat OUR house estimate? Per-quarter revenue/PAT surprise vs the backtested model,
// classified with the model's own error as the noise floor (rev ±7.5%, PAT ±25%) + beat/miss streak.
// From /api/earnings-surprise. "Surprise vs our estimate" (no street consensus). Research, not a call.

import { useEffect, useState } from "react"

const T = {
  border: "#E5E7EB", bg: "#F7F9FC", text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2", amber: "#D97706", blue: "#2563EB",
}
const vcol = (v: string | null) => v === "BEAT" ? T.green : v === "MISS" ? T.red : v === "MIXED" ? T.amber : T.textSub
const vbg = (v: string | null) => v === "BEAT" ? T.greenBg : v === "MISS" ? T.redBg : "#F1F5F9"
const sp = (x: number | null) => x === null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(0)}%`

export default function EarningsSurprise({ symbol }: { symbol: string }) {
  const [d, setD] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setD(null)
    fetch(`/api/earnings-surprise?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json()).then(setD).catch(() => setD({ error: true })).finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Loading earnings surprise…</div>
  if (!d || d.error) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Earnings surprise unavailable.</div>
  const qs: any[] = d.quarters || []
  if (!qs.length) return <div style={{ fontSize: 12, color: T.textSub, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 12px" }}>No matched quarters yet — needs a house estimate and a reported actual for the same quarter.</div>

  const latest = qs[0]
  const streakTxt = latest.streak > 1 ? `${latest.streak} straight beats` : latest.streak < -1 ? `${Math.abs(latest.streak)} straight misses` : null

  return (
    <div>
      {/* latest quarter headline */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{latest.quarter}</span>
        <span style={{ fontSize: 13, fontWeight: 800, color: vcol(latest.verdict), background: vbg(latest.verdict), padding: "3px 10px", borderRadius: 8 }}>{latest.verdict || "—"}</span>
        <span style={{ fontSize: 11, color: T.textSub }}>
          revenue <b style={{ color: vcol(latest.revenue_verdict) }}>{sp(latest.revenue_surprise_pct)}</b> · profit <b style={{ color: vcol(latest.pat_verdict) }}>{sp(latest.pat_surprise_pct)}</b> vs est
        </span>
        {streakTxt && <span style={{ fontSize: 11, fontWeight: 700, color: latest.streak > 0 ? T.green : T.red }}>🔥 {streakTxt}</span>}
      </div>

      {/* history table */}
      <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead><tr style={{ background: T.bg, borderBottom: `1px solid ${T.border}` }}>
            {["Quarter", "Rev (est→act)", "Rev surp", "Profit (est→act)", "Profit surp", "Verdict"].map((h, i) => (
              <th key={i} style={{ textAlign: i === 0 ? "left" : "right", padding: "6px 8px", fontSize: 9, fontWeight: 700, color: T.textSub, whiteSpace: "nowrap" }}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {qs.slice(0, 8).map((q, i) => (
              <tr key={i} style={{ borderBottom: `1px solid #F1F5F9` }}>
                <td style={{ padding: "6px 8px", fontWeight: 600, color: T.text }}>{q.quarter}</td>
                <td style={{ padding: "6px 8px", textAlign: "right", color: T.textSub }}>{q.est_revenue?.toFixed(0)}→{q.act_revenue?.toFixed(0)}</td>
                <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700, color: vcol(q.revenue_verdict) }}>{sp(q.revenue_surprise_pct)}</td>
                <td style={{ padding: "6px 8px", textAlign: "right", color: T.textSub }}>{q.est_pat?.toFixed(0)}→{q.act_pat?.toFixed(0)}</td>
                <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700, color: vcol(q.pat_verdict) }}>{sp(q.pat_surprise_pct)}</td>
                <td style={{ padding: "6px 8px", textAlign: "right" }}><span style={{ fontSize: 9, fontWeight: 800, color: vcol(q.verdict), background: vbg(q.verdict), padding: "1px 6px", borderRadius: 5 }}>{q.verdict}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ fontSize: 9, color: T.textMeta, marginTop: 8, lineHeight: 1.5 }}>
        Surprise is <b>vs our house estimate</b> (we don't have street consensus). BEAT/MISS use the model's own
        backtested error as the bar — revenue must clear ±7.5%, profit ±25% — so small deviations read INLINE rather
        than a fake beat. Profit-led verdict. Context for "is this business out-/under-delivering," not a buy call.
      </div>
    </div>
  )
}
