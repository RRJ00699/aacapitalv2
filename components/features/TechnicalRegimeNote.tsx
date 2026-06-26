"use client"

import React, { useEffect, useState } from "react"

/**
 * TechnicalRegimeNote — the honest, validated conclusion from the 10-year backtest of the
 * live breakout signals (backtest_screener.py / backtest_regime.py). These setups are NOT
 * "2023 mirages" — they have real edge, but only in uptrends, and they bleed in drawdowns.
 * So we surface the truth in the UI instead of selling them as always-on "profitable".
 *
 * Optionally shows the LIVE market regime (equal-weight universe index vs its 200-DMA),
 * so the user knows whether breakout setups are currently ARMED or MUTED. Drop it at the
 * top of the screener / Technical view.
 */

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", text: "#111827", textSub: "#374151", meta: "#6B7280",
  green: "#16A34A", greenBg: "#ECFDF3", amber: "#D97706", amberBg: "#FFFBEB",
  red: "#DC2626", redBg: "#FEF2F2", blue: "#2563EB", grayBg: "#F3F4F6",
}

type Regime = "uptrend" | "downtrend" | null

export default function TechnicalRegimeNote({ regime: regimeProp }: { regime?: Regime }) {
  const [open, setOpen] = useState(true)
  const [regime, setRegime] = useState<Regime>(regimeProp ?? null)
  const [breadth, setBreadth] = useState<number | null>(null)

  // If no regime passed in, try the endpoint; fail silently (card still shows the conclusion).
  useEffect(() => {
    if (regimeProp !== undefined) return
    let alive = true
    fetch("/api/market-regime")
      .then(r => (r.ok ? r.json() : null))
      .then(j => { if (alive && j?.ok) { setRegime(j.regime ?? null); setBreadth(j.breadth ?? null) } })
      .catch(() => {})
    return () => { alive = false }
  }, [regimeProp])

  if (!open) return null

  const armed = regime === "uptrend"
  const muted = regime === "downtrend"
  const badge = armed
    ? { label: "Uptrend → breakout setups ARMED", color: T.green, bg: T.greenBg }
    : muted
      ? { label: "Drawdown → breakout setups MUTED", color: T.red, bg: T.redBg }
      : { label: "Regime unknown", color: T.meta, bg: T.grayBg }

  return (
    <div style={{
      background: T.surface, border: `0.5px solid ${T.border}`, borderLeft: `3px solid ${T.amber}`,
      borderRadius: 10, padding: "12px 14px", marginBottom: 12, fontSize: 13, lineHeight: 1.5, color: T.textSub,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 6 }}>
        <span style={{ fontWeight: 700, color: T.text, fontSize: 13 }}>
          Breakout signals — read this first
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, color: badge.color, background: badge.bg,
            padding: "3px 8px", borderRadius: 999, whiteSpace: "nowrap",
          }}>
            {badge.label}{breadth != null ? ` · breadth ${Math.round(breadth * 100)}%` : ""}
          </span>
          <button onClick={() => setOpen(false)} aria-label="dismiss"
            style={{ border: "none", background: "transparent", color: T.meta, cursor: "pointer", fontSize: 14, lineHeight: 1 }}>
            ×
          </button>
        </div>
      </div>

      <p style={{ margin: "0 0 6px" }}>
        Tested honestly over 10 years, these breakout setups (near-52w-high + volume expansion
        above the 200-DMA, NR7 breakouts) aren't <em>“2023 mirages”</em> — they carry real edge.
        But they’re <strong>bull-market amplifiers</strong>: they add return when the market trends
        up and <strong>actively bleed in drawdowns</strong> (they underperformed in 2018 and 2022).
      </p>
      <p style={{ margin: "0 0 6px" }}>
        So the rule isn’t “ship” or “kill” — it’s <strong>gate them on market regime</strong>. Fire
        breakout setups only while the broad market is in an uptrend (index above its 200-DMA);
        switch them off in corrections. Always-on, they hand the edge back.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        <Chip color={T.green} bg={T.greenBg}>Edge in 2017 · 2020 · 2021 · 2023</Chip>
        <Chip color={T.red} bg={T.redBg}>Worse than baseline in 2018 · 2022</Chip>
        <Chip color={T.meta} bg={T.grayBg}>Signal, not a buy call</Chip>
      </div>
    </div>
  )
}

function Chip({ children, color, bg }: { children: React.ReactNode; color: string; bg: string }) {
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color, background: bg, padding: "3px 8px", borderRadius: 6 }}>
      {children}
    </span>
  )
}
