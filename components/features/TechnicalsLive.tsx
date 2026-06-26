"use client"
// TechnicalsLive — Technical tab content driven by REAL price_candles via
// /api/stock/technicals. Replaces the simulated "Technical Structure" and the
// fake conviction-formula "Expected Returns" sections. Honest by design: shows
// provenance (how many candles, through what date), and an explicit message when
// a symbol's history is too thin — never fabricated numbers.
//
// Drop-in: import into stock-research-workspace.tsx and render
//   <TechnicalsLive symbol={symbol} />
// in the Technical tab where the two old sections were.

import { useEffect, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", border2: "#F1F5F9",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", greenBd: "#BBF7D0",
  blue: "#2563EB", red: "#DC2626", amber: "#D97706", textOn: "#0F172A",
}

const num = (v: unknown): number | null => {
  const n = Number(v); return Number.isFinite(n) ? n : null
}
const show = (v: number | null, d = 2) => (v === null ? "—" : v.toFixed(d))
const showPct = (v: number | null) => (v === null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`)

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16, padding: "14px 16px", marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: `1px solid ${T.border2}`, paddingBottom: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 800, color: T.textSub, textTransform: "uppercase", letterSpacing: "0.1em" }}>{title}</span>
        {action}
      </div>
      {children}
    </div>
  )
}

function KV({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border2}`, borderRadius: 10, padding: "10px 14px" }}>
      <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: color ?? T.text }}>{value}</div>
    </div>
  )
}

function trendColor(t?: string) {
  if (!t) return T.textSub
  if (t.includes("Uptrend")) return T.green
  if (t.includes("Downtrend") || t.includes("Bearish")) return T.red
  return T.textSub
}
function retColor(v: number | null) {
  return v === null ? T.textSub : v >= 0 ? T.green : T.red
}

export default function TechnicalsLive({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let on = true
    setLoading(true)
    fetch(`/api/stock/technicals?sym=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json())
      .then(d => { if (on) { setData(d); setLoading(false) } })
      .catch(() => { if (on) { setData({ ok: false }); setLoading(false) } })
    return () => { on = false }
  }, [symbol])

  if (loading) {
    return <Section title="Technicals"><div style={{ fontSize: 11, color: T.textMeta, padding: "8px 0" }}>Computing from candles…</div></Section>
  }

  // honest empty / thin-history state
  if (!data || data.ok === false || data.technical === null || !data.daily?.enough) {
    const reason = data?.reason
      || (data?.daily && !data.daily.enough ? `Only ${data.daily.bars} daily candle(s) — not enough history for indicators yet.` : null)
      || "Technicals unavailable for this symbol."
    return (
      <Section title="Technicals">
        <div style={{ fontSize: 12, color: T.textSub, background: "#FAFAFA", border: `1px solid ${T.border2}`, borderRadius: 10, padding: "12px 14px" }}>
          {reason}
        </div>
      </Section>
    )
  }

  const d = data.daily, w = data.weekly, p = data.price, r = data.returns, s = data.structure
  const provenance = `${data.coverage?.dailyBars?.toLocaleString?.() ?? data.coverage?.dailyBars} daily candles · through ${data.asOf}`

  // EMA alignment read
  const emaStack = (d.ema20 && d.ema50 && d.ema200)
    ? (d.ema20 > d.ema50 && d.ema50 > d.ema200 ? "20 > 50 > 200 (bullish stack)"
      : d.ema20 < d.ema50 && d.ema50 < d.ema200 ? "20 < 50 < 200 (bearish stack)"
      : "mixed")
    : "—"

  return (
    <>
      <Section
        title="Trend & Momentum"
        action={<span style={{ fontSize: 9, color: T.textMeta }}>{provenance}</span>}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
          <KV label="Daily Trend"  value={d.trend ?? "—"} color={trendColor(d.trend)} />
          <KV label="Weekly Trend" value={w?.enough ? (w.trend ?? "—") : "—"} color={trendColor(w?.trend)} />
          <KV label="RSI (14)"     value={show(num(d.rsi), 1)}
              color={num(d.rsi) !== null && num(d.rsi)! >= 70 ? T.amber : num(d.rsi) !== null && num(d.rsi)! <= 30 ? T.blue : T.text} />
          <KV label="ATR %"        value={d.atrPct === null ? "—" : `${show(num(d.atrPct), 1)}%`} />
          <KV label="Vol vs 10d"   value={s?.volumeRatio == null ? "—" : `${show(num(s.volumeRatio), 2)}×`}
              color={num(s?.volumeRatio) !== null && num(s.volumeRatio)! >= 1.5 ? T.green : T.text} />
          <KV label="Delivery %"   value={s?.deliveryPct == null ? "—" : `${show(num(s.deliveryPct), 1)}%`} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 8 }}>
          <KV label="EMA 20"  value={show(num(d.ema20))} />
          <KV label="EMA 50"  value={show(num(d.ema50))} />
          <KV label="EMA 200" value={show(num(d.ema200))} />
        </div>
        <div style={{ fontSize: 10, color: T.textMeta, marginTop: 8 }}>EMA stack: {emaStack}</div>
      </Section>

      <Section title="52-Week Range">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
          <KV label="52W High"     value={show(num(p?.week52High))} />
          <KV label="52W Low"      value={show(num(p?.week52Low))} />
          <KV label="Below High"   value={p?.pctBelow52WHigh == null ? "—" : `${show(num(p.pctBelow52WHigh), 1)}%`}
              color={T.amber} />
          <KV label="Above Low"    value={p?.pctAbove52WLow == null ? "—" : `${show(num(p.pctAbove52WLow), 1)}%`}
              color={T.green} />
        </div>
      </Section>

      <Section title="Returns (from candles)" action={<span style={{ fontSize: 9, color: T.textMeta }}>actual, not modeled</span>}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
          <KV label="1 Month"  value={showPct(num(r?.r1m))} color={retColor(num(r?.r1m))} />
          <KV label="3 Month"  value={showPct(num(r?.r3m))} color={retColor(num(r?.r3m))} />
          <KV label="6 Month"  value={showPct(num(r?.r6m))} color={retColor(num(r?.r6m))} />
          <KV label="1 Year"   value={showPct(num(r?.r1y))} color={retColor(num(r?.r1y))} />
        </div>
        <div style={{ fontSize: 10, color: T.textMeta, marginTop: 8 }}>
          Research signal, not a buy call. Computed from your price_candles, not a probability model.
        </div>
      </Section>
    </>
  )
}
