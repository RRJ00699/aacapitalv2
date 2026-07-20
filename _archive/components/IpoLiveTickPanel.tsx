"use client"
import React, { useEffect, useRef, useState } from "react"

type Row = {
  ltp: number | string | null
  vwap: number | string | null
  vwap_dist: number | string | null
  obir: number | string | null
  day_volume: number | string | null
  momentum: string | null
  divergence: boolean | null
  signal: string | null
  recorded_at: string
}
const n = (v: any): number | null => {
  if (v === null || v === undefined || v === "") return null
  const f = parseFloat(v); return isNaN(f) ? null : f
}

const C = {
  ink: "#0F1B2D", sub: "#475569", meta: "#94a3b8", line: "#ECE8E1",
  green: "#0E9F6E", red: "#E02424", amber: "#B8860B", blue: "#2563EB",
}

function sigTone(s: string | null): { bg: string; fg: string } {
  const t = (s || "").toUpperCase()
  if (t.includes("AVOID") || t.includes("WEAK") || t.includes("SELL")) return { bg: "#FDECEC", fg: C.red }
  if (t.includes("BID") || t.includes("RECLAIM") || t.includes("STRONG") || t.includes("BUY")) return { bg: "#E7F6EF", fg: C.green }
  if (t.includes("WATCH") || t.includes("FLIP") || t.includes("ASK")) return { bg: "#FBF3E0", fg: C.amber }
  return { bg: "#EEF1F4", fg: C.sub }
}

function Spark({ series }: { series: Row[] }) {
  const pts = series.map((r) => ({ p: n(r.ltp), v: n(r.vwap) })).filter((d) => d.p != null)
  if (pts.length < 2) return <div style={{ height: 70, display: "flex", alignItems: "center", justifyContent: "center", color: C.meta, fontSize: 12, fontFamily: "'IBM Plex Mono',monospace" }}>waiting for ticks…</div>
  const W = 680, H = 70, pad = 4
  const ys = pts.flatMap((d) => [d.p as number, ...(d.v != null ? [d.v as number] : [])])
  const min = Math.min(...ys), max = Math.max(...ys), rng = max - min || 1
  const x = (i: number) => pad + (i * (W - 2 * pad)) / (pts.length - 1)
  const y = (val: number) => pad + (H - 2 * pad) * (1 - (val - min) / rng)
  const path = (sel: "p" | "v") => pts.map((d, i) => (d[sel] == null ? null : `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d[sel] as number).toFixed(1)}`)).filter(Boolean).join(" ")
  const last = pts[pts.length - 1]
  const up = last.v != null ? (last.p as number) >= (last.v as number) : true
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 70 }}>
      {last.v != null && <path d={path("v")} fill="none" stroke={C.meta} strokeWidth={1.4} strokeDasharray="4 3" />}
      <path d={path("p")} fill="none" stroke={up ? C.green : C.red} strokeWidth={2} />
    </svg>
  )
}

export default function IpoLiveTickPanel({ symbol = "TURTLEMINT", pollMs = 4000 }: { symbol?: string; pollMs?: number }) {
  const [series, setSeries] = useState<Row[]>([])
  const [latest, setLatest] = useState<Row | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [stamp, setStamp] = useState<string>("")
  const timer = useRef<any>(null)

  useEffect(() => {
    let alive = true
    const pull = async () => {
      try {
        const r = await fetch(`/api/ipo/tick-feed?symbol=${encodeURIComponent(symbol)}&limit=150`, { cache: "no-store" })
        const j = await r.json()
        if (!alive) return
        if (j.error) setErr(j.error); else setErr(null)
        setSeries(j.series || []); setLatest(j.latest || null)
        setStamp(new Date().toLocaleTimeString())
      } catch (e: any) { if (alive) setErr(String(e?.message || e)) }
    }
    pull(); timer.current = setInterval(pull, pollMs)
    return () => { alive = false; clearInterval(timer.current) }
  }, [symbol, pollMs])

  const ltp = n(latest?.ltp), vwap = n(latest?.vwap), dist = n(latest?.vwap_dist), obir = n(latest?.obir)
  const aboveV = ltp != null && vwap != null ? ltp >= vwap : null
  const tone = sigTone(latest?.signal ?? null)
  const stale = !latest

  const card: React.CSSProperties = { background: "#fff", border: `1px solid ${C.line}`, borderRadius: 14, padding: 16 }
  const mono = "'IBM Plex Mono',monospace"

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 9, height: 9, borderRadius: "50%", background: stale ? C.meta : C.green, boxShadow: stale ? "none" : `0 0 0 3px #0E9F6E22` }} />
          <span style={{ fontWeight: 800, fontSize: 16, color: C.ink }}>{symbol}</span>
          <span style={{ fontSize: 11, color: C.meta, fontFamily: mono }}>{stale ? "no ticks yet" : "live"}</span>
        </div>
        <span style={{ fontSize: 11, color: C.meta, fontFamily: mono }}>{stamp && `updated ${stamp}`}</span>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 18, alignItems: "flex-end" }}>
        <div>
          <div style={{ fontSize: 10, color: C.meta, fontFamily: mono, letterSpacing: 1 }}>LTP</div>
          <div style={{ fontSize: 30, fontWeight: 800, color: C.ink, lineHeight: 1 }}>{ltp != null ? ltp.toFixed(2) : "—"}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.meta, fontFamily: mono, letterSpacing: 1 }}>VWAP</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: aboveV == null ? C.sub : aboveV ? C.green : C.red }}>
            {vwap != null && vwap > 0 ? vwap.toFixed(2) : "—"}
            {dist != null && <span style={{ fontSize: 12, marginLeft: 6 }}>({dist >= 0 ? "+" : ""}{dist.toFixed(2)}%)</span>}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.meta, fontFamily: mono, letterSpacing: 1 }}>ORDER-BOOK (OBIR)</div>
          {obir != null ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 120, height: 10, borderRadius: 5, overflow: "hidden", display: "flex", border: `1px solid ${C.line}` }}>
                <div style={{ width: `${Math.round(obir * 100)}%`, background: C.green }} />
                <div style={{ flex: 1, background: C.red }} />
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: obir >= 0.55 ? C.green : obir <= 0.45 ? C.red : C.sub, fontFamily: mono }}>
                {(obir * 100).toFixed(0)}% bid
              </span>
            </div>
          ) : <div style={{ fontSize: 16, color: C.meta }}>—</div>}
        </div>
      </div>

      <div style={{ marginTop: 12 }}><Spark series={series} /></div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8, flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 11, fontWeight: 800, color: tone.fg, background: tone.bg, borderRadius: 6, padding: "4px 9px" }}>
            {latest?.signal || "—"}
          </span>
          {latest?.momentum && <span style={{ fontSize: 11, color: C.sub, fontFamily: mono }}>{latest.momentum}</span>}
          {latest?.divergence && <span style={{ fontSize: 11, color: C.amber, fontFamily: mono }}>⚠ divergence</span>}
        </div>
        <span style={{ fontSize: 11, color: C.meta, fontFamily: mono }}>{series.length} pts</span>
      </div>

      {(stale || err) && (
        <div style={{ marginTop: 10, fontSize: 11, color: C.meta, fontFamily: mono, lineHeight: 1.5 }}>
          {err ? `error: ${err}` : "No rows in ipo_tick_feed yet. Make sure the ticker is running with --write-db and the market is open. VWAP/OBIR fill in once trading starts."}
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 9.5, color: C.meta, fontFamily: mono }}>
        VWAP = trustworthy. OBIR = displayed depth (spoofable) — context, not a trigger. Research signal, not a buy call.
      </div>
    </div>
  )
}
