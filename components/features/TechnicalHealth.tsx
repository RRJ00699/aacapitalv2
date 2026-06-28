"use client"
// components/features/TechnicalHealth.tsx
// Deep-dive technical snapshot for one stock from /api/technical-features: relative strength
// (universe + sector percentile), RVOL, volatility percentile, 52w/ATH proximity, trend (EMA
// alignment), RSI, plus the nightly engine's Wyckoff stage & breakout-watch. Descriptive, not a call.

import { useEffect, useState } from "react"

const T = {
  border: "#E5E7EB", bg: "#F7F9FC", text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2", amber: "#D97706", blue: "#2563EB", track: "#EEF2F7",
}
const rankColor = (p: number | null) => p === null ? T.textMeta : p >= 70 ? T.green : p >= 40 ? T.amber : T.red

function RankBar({ label, value, hint }: { label: string; value: number | null; hint?: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: T.textSub, fontWeight: 600 }}>{label}{hint && <span style={{ color: T.textMeta, fontWeight: 400 }}> · {hint}</span>}</span>
        <span style={{ fontSize: 11, fontWeight: 800, color: rankColor(value) }}>{value === null ? "—" : `${Math.round(value)}`}</span>
      </div>
      <div style={{ height: 6, background: T.track, borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, height: "100%", background: rankColor(value), borderRadius: 4 }} />
      </div>
    </div>
  )
}

export default function TechnicalHealth({ symbol }: { symbol: string }) {
  const [d, setD] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setD(null)
    fetch(`/api/technical-features?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json()).then(setD).catch(() => setD({ error: true })).finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Loading technical health…</div>
  if (!d || d.error) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Technical data unavailable.</div>
  if (d.available === false)
    return <div style={{ fontSize: 12, color: T.textSub, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 12px" }}>Not yet in the technical feature store — runs with the next compute.</div>

  const t = d.technical
  const chip = (txt: string, color: string, bg: string) => (
    <span style={{ fontSize: 10, fontWeight: 800, color, background: bg, padding: "2px 8px", borderRadius: 7 }}>{txt}</span>
  )

  return (
    <div>
      {/* trend + stage row */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {t.ema_aligned ? chip("EMA aligned ↑", "#fff", T.green) : t.above_ema200 ? chip("Above 200-EMA", T.blue, "#EFF6FF") : chip("Below 200-EMA", T.red, T.redBg)}
        {t.stage && chip(t.stage, T.text, T.bg)}
        {t.breakout_watch_tier && chip(`Breakout: ${t.breakout_watch_tier}`, T.amber, "#FEF9EC")}
        {t.rsi14 !== null && chip(`RSI ${t.rsi14.toFixed(0)}`, t.rsi14 >= 70 ? T.red : t.rsi14 <= 30 ? T.green : T.textSub, T.bg)}
      </div>

      {/* relative strength ranks */}
      <div style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 12, padding: "12px 12px 6px", marginBottom: 8 }}>
        <RankBar label="Relative Strength" value={t.rs_score} hint="vs universe (3m+6m)" />
        <RankBar label="RS within sector" value={t.rs_6m_sector} hint={`6m · ${t.sector || "—"}`} />
        <RankBar label="Relative Volume rank" value={t.rvol_rank} hint={t.rvol !== null ? `${t.rvol.toFixed(1)}× normal` : ""} />
        <RankBar label="Volatility percentile" value={t.vol_pctile} hint={t.atr_pct !== null ? `ATR ${t.atr_pct.toFixed(1)}%` : ""} />
      </div>

      {/* proximity tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <Tile label="3M return" value={t.ret_3m === null ? "—" : `${t.ret_3m >= 0 ? "+" : ""}${t.ret_3m.toFixed(0)}%`} color={t.ret_3m >= 0 ? T.green : T.red} />
        <Tile label="from 52w high" value={t.pct_from_52wh === null ? "—" : `${t.pct_from_52wh.toFixed(0)}%`} color={t.pct_from_52wh > -5 ? T.green : T.textSub} />
        <Tile label="from ATH" value={t.pct_from_ath === null ? "—" : `${t.pct_from_ath.toFixed(0)}%`} color={t.pct_from_ath > -10 ? T.green : T.textSub} />
      </div>

      {/* Bucket-A descriptors — context lenses, explicitly NOT signals */}
      <div style={{ marginTop: 10, padding: "10px 12px", background: T.bg, border: `1px solid ${T.border}`, borderRadius: 12 }}>
        <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 700, marginBottom: 6 }}>STRUCTURE & CONTEXT (descriptive — not buy signals)</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {t.compression_state && chip(
            t.compression_state,
            t.compression_state.startsWith("Coil") ? T.blue : t.compression_state.startsWith("Expand") ? T.amber : T.textSub,
            t.compression_state.startsWith("Coil") ? "#EFF6FF" : T.bg
          )}
          {t.gap_dir && t.gap_dir !== "None" && chip(
            `Gap ${t.gap_dir} ${t.gap_size?.toFixed(1)}%${t.gap_filled ? " · filled" : " · open"}`,
            t.gap_dir === "Up" ? T.green : T.red,
            t.gap_dir === "Up" ? T.greenBg : T.redBg
          )}
          {t.delivery_state && t.delivery_today !== null && chip(
            `Delivery ${t.delivery_today.toFixed(0)}%${t.delivery_ratio ? ` (${t.delivery_ratio.toFixed(1)}× norm)` : ""} · ${t.delivery_state}`,
            t.delivery_state === "Elevated" ? T.blue : t.delivery_state === "Light" ? T.textSub : T.textSub,
            T.bg
          )}
        </div>
        {(t.support !== null || t.resistance !== null) && (
          <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11 }}>
            {t.support !== null && (
              <span style={{ color: T.textSub }}>Support <b style={{ color: T.green }}>₹{t.support.toFixed(0)}</b>
                {t.support_dist !== null && <span style={{ color: T.textMeta }}> ({t.support_dist.toFixed(1)}%)</span>}</span>
            )}
            {t.resistance !== null && (
              <span style={{ color: T.textSub }}>Resistance <b style={{ color: T.red }}>₹{t.resistance.toFixed(0)}</b>
                {t.resistance_dist !== null && <span style={{ color: T.textMeta }}> (+{t.resistance_dist.toFixed(1)}%)</span>}</span>
            )}
          </div>
        )}
        <div style={{ fontSize: 9, color: T.textMeta, marginTop: 6, lineHeight: 1.5 }}>
          Coiling = range is tightening (not a breakout prediction). Levels are where price turned before.
          Delivery vs this stock's own norm — backtested as context, <b>not</b> a forward signal.
        </div>
      </div>
    </div>
  )
}

function Tile({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 8, padding: "6px 8px", textAlign: "center" }}>
      <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 800, color }}>{value}</div>
    </div>
  )
}
