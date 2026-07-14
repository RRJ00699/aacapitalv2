"use client"
import { useState, useEffect, useCallback } from "react"
import { useSearchParams } from "next/navigation"

type Journey = {
  ok: boolean; sym: string; hasData: boolean; note?: string
  entry?: number; peak?: number; low?: number; live?: number; liveSource?: string
  armed?: boolean; floorLevel?: number; trailLevel?: number
  gainNow?: number; offPeak?: number; daysHeld?: number; lockinDaysLeft?: number
  decision?: string; reason?: string; tone?: string
  series?: Array<{ date: string; close: number; high: number; low: number }>
}

const C = {
  bg: "var(--t-bg)", card: "var(--t-surface)", bd: "var(--t-border)", text: "var(--t-text)",
  meta: "var(--t-meta)", green: "var(--t-green)", greenBg: "var(--t-greenBg)", greenBd: "var(--t-greenBd)",
  red: "var(--t-red)", redBg: "var(--t-redBg)", redBd: "var(--t-redBd)", gold: "var(--t-gold)",
}

export default function JourneyPage() {
  const params = useSearchParams()
  const sym = (params.get("sym") || "").toUpperCase()
  const [d, setD] = useState<Journey | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshedAt, setRefreshedAt] = useState<string>("")

  const load = useCallback(async () => {
    if (!sym) return
    try {
      const r = await fetch(`/api/ipo/journey?sym=${sym}`)
      const j = await r.json()
      setD(j)
      setRefreshedAt(new Date().toLocaleTimeString())
    } catch { /* keep prior */ }
    setLoading(false)
  }, [sym])

  useEffect(() => {
    load()
    const t = setInterval(load, 60000) // live refresh every 60s
    return () => clearInterval(t)
  }, [load])

  if (!sym) return <Shell><p style={{ color: C.meta }}>No IPO selected. Open a journey from an IPO card.</p></Shell>
  if (loading) return <Shell><p style={{ color: C.meta }}>Loading {sym}…</p></Shell>
  if (!d || !d.ok) return <Shell><p style={{ color: C.red }}>Couldn&apos;t load {sym}.</p></Shell>
  if (!d.hasData) return <Shell><h2 style={{ color: C.text }}>{sym}</h2><p style={{ color: C.meta }}>{d.note}</p></Shell>

  const exit = d.decision === "EXIT"
  const decCol = exit ? C.red : C.green
  const decBg = exit ? C.redBg : C.greenBg
  const decBd = exit ? C.redBd : C.greenBd

  // chart geometry
  const s = d.series || []
  const prices = s.flatMap((p) => [p.high, p.low]).concat([d.entry!, d.live!, d.peak!, d.low!])
  const min = Math.min(...prices), max = Math.max(...prices), rng = max - min || 1
  const W = 340, H = 130, pad = 8
  const x = (i: number) => pad + (i / Math.max(1, s.length - 1)) * (W - 2 * pad)
  const y = (v: number) => H - pad - ((v - min) / rng) * (H - 2 * pad)
  const line = s.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join(" ")

  return (
    <Shell>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ color: C.text, margin: 0, fontSize: 20 }}>{sym}</h2>
          <div style={{ color: C.meta, fontSize: 12.5, marginTop: 2 }}>Day {d.daysHeld} of 30 · the hold</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: exit ? C.red : C.green, fontSize: 24, fontWeight: 800 }}>₹{d.live}</div>
          <div style={{ color: C.meta, fontSize: 11 }}>{d.gainNow! >= 0 ? "+" : ""}{d.gainNow}% vs open · {d.liveSource}</div>
        </div>
      </div>

      {/* price story chart */}
      <div style={{ margin: "14px 0" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H }}>
          {/* floor + trail reference lines */}
          <line x1={pad} y1={y(d.floorLevel!)} x2={W - pad} y2={y(d.floorLevel!)} stroke={C.gold} strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
          <line x1={pad} y1={y(d.trailLevel!)} x2={W - pad} y2={y(d.trailLevel!)} stroke={C.red} strokeWidth="1" strokeDasharray="3,3" opacity="0.5" />
          <path d={line} fill="none" stroke={C.green} strokeWidth="2.5" />
          {/* entry / peak / now dots */}
          <circle cx={x(0)} cy={y(d.entry!)} r="4" fill={C.green} />
          <circle cx={x(s.length - 1)} cy={y(d.live!)} r="5" fill="#FFFFFF" stroke={C.bg} strokeWidth="2" />
        </svg>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.meta, marginTop: 2 }}>
          <span>open ₹{d.entry}</span>
          <span style={{ color: C.gold }}>floor ₹{d.floorLevel}</span>
          <span style={{ color: C.gold }}>peak ₹{d.peak}</span>
        </div>
      </div>

      {/* decision cockpit */}
      <div style={{ padding: 14, background: decBg, border: `1px solid ${decBd}`, borderRadius: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ background: decCol, color: C.bg, fontSize: 13, fontWeight: 800, padding: "4px 13px", borderRadius: 7 }}>{d.decision}</span>
          <span style={{ color: decCol, fontSize: 12.5 }}>{d.armed ? "floor armed" : "not yet armed"}</span>
        </div>
        <div style={{ color: C.text, fontSize: 13, marginTop: 10, lineHeight: 1.5 }}>{d.reason}</div>
      </div>

      {/* engine tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}>
        <Tile label="Floor (+3%)" val={`₹${d.floorLevel}`} col={d.live! > d.floorLevel! ? C.green : C.red} />
        <Tile label="Trail (12% off peak)" val={`₹${d.trailLevel}`} col={d.live! > d.trailLevel! ? C.green : C.red} />
        <Tile label="Off peak" val={`${d.offPeak}%`} col={C.gold} />
        <Tile label="Low since listing" val={`₹${d.low}`} col={C.meta} />
      </div>

      {/* lock-in timeline */}
      <div style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", color: C.meta, fontSize: 10, marginBottom: 5 }}>
          <span>Listing</span><span>Anchor lock-in →</span>
        </div>
        <div style={{ height: 6, background: C.bd, borderRadius: 3, position: "relative" }}>
          <div style={{ position: "absolute", left: 0, top: 0, height: 6, width: `${Math.min(100, (d.daysHeld! / 30) * 100)}%`, background: C.green, borderRadius: 3 }} />
        </div>
        <div style={{ color: C.meta, fontSize: 10.5, marginTop: 5 }}>Day {d.daysHeld} · {d.lockinDaysLeft} days to first unlock</div>
      </div>

      <div style={{ color: C.meta, fontSize: 10, marginTop: 12, textAlign: "center" }}>
        live check every 60s · updated {refreshedAt} · research signal, not a buy call
      </div>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div style={{ minHeight: "100vh", background: C.bg, padding: 16 }}>
    <div style={{ maxWidth: 440, margin: "0 auto", background: C.card, border: `1px solid ${C.bd}`, borderRadius: 16, padding: 18 }}>{children}</div>
  </div>
}

function Tile({ label, val, col }: { label: string; val: string; col: string }) {
  return <div style={{ background: "#12202B", border: `1px solid ${C.bd}`, borderRadius: 9, padding: "10px 12px" }}>
    <div style={{ color: C.meta, fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4 }}>{label}</div>
    <div style={{ color: col, fontSize: 16, fontWeight: 700, marginTop: 3 }}>{val}</div>
  </div>
}
