"use client"
import React, { useEffect, useRef, useState } from "react"

const C = {
  ink: "#0F1B2D", sub: "#475569", meta: "#94a3b8", line: "#ECE8E1",
  green: "#0E9F6E", red: "#E02424", amber: "#B8860B", blue: "#2563EB", poc: "#7C3AED",
}
const mono = "'IBM Plex Mono',monospace"
const num = (v: any): number | null => {
  if (v === null || v === undefined || v === "") return null
  const f = parseFloat(v); return isNaN(f) ? null : f
}

function verdictTone(v: string | null): { bg: string; fg: string } {
  const t = (v || "").toUpperCase()
  if (t.includes("BROKEN") || t.includes("LOCKED")) return { bg: "#FDECEC", fg: C.red }
  if (t.includes("INTACT")) return { bg: "#E7F6EF", fg: C.green }
  if (t.includes("AT FLOOR")) return { bg: "#FBF3E0", fg: C.amber }
  if (t.includes("CEILING")) return { bg: "#FBF3E0", fg: C.amber }
  return { bg: "#EEF1F4", fg: C.sub }
}

function VolumeProfile({ profile, floor, ceiling, poc, current }:
  { profile: Record<string, number>; floor: number | null; ceiling: number | null; poc: number | null; current: number | null }) {
  const entries = Object.entries(profile).map(([p, v]) => ({ p: parseFloat(p), v: Number(v) }))
    .filter((d) => !isNaN(d.p)).sort((a, b) => b.p - a.p) // high price on top
  if (entries.length === 0) return null
  const maxV = Math.max(...entries.map((d) => d.v)) || 1
  const near = (a: number | null, b: number) => a != null && Math.abs(a - b) < 0.01
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 10, color: C.meta, fontFamily: mono, letterSpacing: 1, marginBottom: 6 }}>VOLUME PROFILE (where money traded)</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {entries.map((d, i) => {
          const isFloor = near(floor, d.p), isCeil = near(ceiling, d.p), isPoc = near(poc, d.p)
          const color = isFloor ? C.green : isCeil ? C.red : isPoc ? C.poc : "#CBD5E1"
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, position: "relative" }}>
              <span style={{ width: 52, textAlign: "right", fontSize: 10, fontFamily: mono, color: near(current, d.p) ? C.ink : C.meta, fontWeight: near(current, d.p) ? 800 : 400 }}>
                {d.p.toFixed(2)}{near(current, d.p) ? " ◄" : ""}
              </span>
              <div style={{ flex: 1, height: 11, background: "#F4F6F8", borderRadius: 3, overflow: "hidden" }}>
                <div style={{ width: `${Math.max(2, (d.v / maxV) * 100)}%`, height: "100%", background: color, opacity: isFloor || isCeil || isPoc ? 1 : 0.6 }} />
              </div>
              <span style={{ width: 38, fontSize: 9, fontFamily: mono, color: C.meta }}>
                {isFloor ? "floor" : isCeil ? "ceil" : isPoc ? "POC" : ""}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function IpoLevelPanel({ symbol = "TURTLEMINT", pollMs = 30000 }: { symbol?: string; pollMs?: number }) {
  const [latest, setLatest] = useState<any>(null)
  const [series, setSeries] = useState<any[]>([])
  const [err, setErr] = useState<string | null>(null)
  const timer = useRef<any>(null)

  useEffect(() => {
    let alive = true
    const pull = async () => {
      try {
        const r = await fetch(`/api/ipo/levels?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
        const j = await r.json()
        if (!alive) return
        setErr(j.error || null); setLatest(j.latest || null); setSeries(j.series || [])
      } catch (e: any) { if (alive) setErr(String(e?.message || e)) }
    }
    pull(); timer.current = setInterval(pull, pollMs)
    return () => { alive = false; clearInterval(timer.current) }
  }, [symbol, pollMs])

  const card: React.CSSProperties = { background: "#fff", border: `1px solid ${C.line}`, borderRadius: 14, padding: 16 }

  if (!latest) {
    return (
      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: 14, color: C.ink, marginBottom: 6 }}>{symbol} · Floor / Ceiling</div>
        <div style={{ fontSize: 12, color: C.meta, fontFamily: mono, lineHeight: 1.6 }}>
          {err ? `error: ${err}` : "Level analysis pending — runs once the capture has enough ticks (analyze_listing_day.py). The live numbers above are real-time; this read fills in shortly."}
        </div>
      </div>
    )
  }

  const tone = verdictTone(latest.verdict)
  const floor = num(latest.floor_price), ceil = num(latest.ceiling_price), poc = num(latest.poc_price)
  const close = num(latest.day_close), gapPct = num(latest.gap_pct)
  let profile: Record<string, number> = {}
  try { profile = typeof latest.profile_json === "string" ? JSON.parse(latest.profile_json) : (latest.profile_json || {}) } catch { profile = {} }

  const stat = (label: string, val: string, color = C.ink) => (
    <div>
      <div style={{ fontSize: 10, color: C.meta, fontFamily: mono, letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 800, color }}>{val}</div>
    </div>
  )

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
        <div style={{ fontWeight: 800, fontSize: 14, color: C.ink }}>{symbol} · Floor / Ceiling</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {latest.gap_bucket && <span style={{ fontSize: 10, fontWeight: 800, color: C.sub, background: "#EEF1F4", borderRadius: 6, padding: "3px 8px", fontFamily: mono }}>
            {latest.gap_bucket} GAP{gapPct != null ? ` ${gapPct >= 0 ? "+" : ""}${gapPct.toFixed(1)}%` : ""}
          </span>}
          <span style={{ fontSize: 11, fontWeight: 800, color: tone.fg, background: tone.bg, borderRadius: 6, padding: "4px 9px" }}>{latest.verdict}</span>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
        {stat("FLOOR", floor != null ? floor.toFixed(2) : "—", C.green)}
        {stat("DEFENSES", latest.floor_defenses != null ? String(latest.floor_defenses) : "—")}
        {stat("CEILING", ceil != null ? ceil.toFixed(2) : "—", C.red)}
        {stat("POC", poc != null ? poc.toFixed(2) : "—", C.poc)}
        {stat("CLOSE", close != null ? close.toFixed(2) : "—")}
      </div>

      {latest.risk_note && (
        <div style={{ marginTop: 10, fontSize: 12.5, color: C.sub, lineHeight: 1.55, background: "#FAFAF8", border: `1px solid ${C.line}`, borderRadius: 8, padding: "9px 11px" }}>
          {latest.risk_note}
        </div>
      )}

      <VolumeProfile profile={profile} floor={floor} ceiling={ceil} poc={poc} current={close} />

      {series.length > 1 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 10, color: C.meta, fontFamily: mono, letterSpacing: 1, marginBottom: 6 }}>FLOOR BY DAY (through anchor window)</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {series.map((r, i) => {
              const f = num(r.floor_price)
              return (
                <div key={i} style={{ fontSize: 10, fontFamily: mono, color: C.sub, border: `1px solid ${C.line}`, borderRadius: 6, padding: "3px 7px" }}>
                  <span style={{ color: C.meta }}>{String(r.trade_date).slice(5)}</span> {f != null ? f.toFixed(1) : "—"}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div style={{ marginTop: 10, fontSize: 9.5, color: C.meta, fontFamily: mono }}>
        Floor/ceiling = observed volume + defense mechanics, not a forecast. Research signal, not a buy call.
      </div>
    </div>
  )
}
