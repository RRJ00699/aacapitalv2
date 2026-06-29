"use client"
import React, { useEffect, useState } from "react"
import IpoLiveTickPanel from "./IpoLiveTickPanel"
import IpoLevelPanel from "./IpoLevelPanel"

/**
 * Renders a live tick panel for EVERY IPO currently streaming into ipo_tick_feed.
 * No symbols hardcoded — whatever the ticker writes (with --write-db) shows up
 * automatically and disappears 20 min after the stream stops.
 */
export default function IpoLiveBoard({ pollMs = 10000 }: { pollMs?: number }) {
  const [symbols, setSymbols] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const pull = async () => {
      try {
        const r = await fetch("/api/ipo/live-symbols", { cache: "no-store" })
        const j = await r.json()
        if (!alive) return
        setErr(j.error || null)
        setSymbols((j.symbols || []).map((s: any) => s.symbol).filter(Boolean))
        setLoaded(true)
      } catch (e: any) {
        if (alive) { setErr(String(e?.message || e)); setLoaded(true) }
      }
    }
    pull()
    const t = setInterval(pull, pollMs)
    return () => { alive = false; clearInterval(t) }
  }, [pollMs])

  const meta: React.CSSProperties = { fontSize: 12, color: "#94a3b8", fontFamily: "'IBM Plex Mono',monospace", textAlign: "center", padding: "28px 16px", lineHeight: 1.6 }

  if (!loaded) return <div style={meta}>checking for live listings…</div>
  if (err) return <div style={meta}>couldn't reach the live feed: {err}</div>
  if (symbols.length === 0)
    return (
      <div style={meta}>
        No IPO is streaming right now.<br />
        On listing day, run the ticker locally —<br />
        <span style={{ color: "#475569" }}>python _scripts/ipo/kite_ticker_ipo.py --symbols &lt;SYMBOL&gt; --write-db --interval 5</span><br />
        — and it appears here automatically.
      </div>
    )

  return (
    <div style={{ display: "grid", gap: 22 }}>
      {symbols.map((s) => (
        <div key={s} style={{ display: "grid", gap: 12 }}>
          <IpoLiveTickPanel symbol={s} />
          <IpoLevelPanel symbol={s} />
        </div>
      ))}
    </div>
  )
}
