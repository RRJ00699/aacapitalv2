"use client"
// components/features/ValuationLens.tsx
// "Cheap or expensive vs its OWN history?" — today's P/E placed as a percentile in the stock's
// ~10yr band, from /api/valuation. The price complement to DNA's quality. Research, not a buy call.

import { useEffect, useState } from "react"

const T = {
  surface: "#FFFFFF", border: "#E5E7EB", bg: "#F7F9FC",
  text: "#0F172A", textSub: "#64748B", textMeta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2",
  amber: "#D97706", blue: "#2563EB", track: "#EEF2F7",
}

// percentile -> colour: low = cheap (green), high = expensive (red)
const pcol = (p: number | null) =>
  p === null ? T.textMeta : p < 30 ? T.green : p > 70 ? T.red : T.amber

export default function ValuationLens({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setData(null)
    fetch(`/api/valuation?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json()).then(setData).catch(() => setData({ error: true }))
      .finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Loading valuation…</div>
  if (!data || data.error) return <div style={{ fontSize: 12, color: T.textMeta, padding: "8px 2px" }}>Valuation unavailable.</div>
  if (data.available === false)
    return (
      <div style={{ fontSize: 12, color: T.textSub, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 12px" }}>
        No valuation band yet — needs price history + annual earnings for this name.
      </div>
    )

  const pe = data.current_pe, pctile = data.pe_percentile
  const c = pcol(pctile)
  // marker position on the band (clamp 0-100)
  const pos = pctile === null ? null : Math.max(0, Math.min(100, pctile))

  return (
    <div>
      {/* headline */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
        <div>
          <span style={{ fontSize: 24, fontWeight: 900, color: T.text }}>{pe === null ? "—" : pe.toFixed(1)}</span>
          <span style={{ fontSize: 11, color: T.textMeta, fontWeight: 600 }}> P/E</span>
        </div>
        {data.ttm_pe !== null && (
          <span style={{ fontSize: 11, color: T.textSub }}>TTM {data.ttm_pe.toFixed(1)}</span>
        )}
        {data.verdict && (
          <span style={{ fontSize: 11, fontWeight: 800, color: c, background: pctile < 30 ? T.greenBg : pctile > 70 ? T.redBg : "#FEF9EC",
            padding: "2px 8px", borderRadius: 7 }}>
            {data.verdict}
          </span>
        )}
      </div>

      {/* percentile band: cheap (left) -> expensive (right), marker at current */}
      {pos !== null && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ position: "relative", height: 10, borderRadius: 6, overflow: "hidden",
            background: "linear-gradient(90deg,#16A34A 0%,#D97706 50%,#DC2626 100%)", opacity: 0.85 }}>
          </div>
          <div style={{ position: "relative", height: 0 }}>
            <div style={{ position: "absolute", left: `calc(${pos}% - 6px)`, top: -13,
              width: 0, height: 0, borderLeft: "6px solid transparent", borderRight: "6px solid transparent",
              borderTop: `7px solid ${T.text}` }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: T.textMeta, marginTop: 2 }}>
            <span>cheap</span>
            <span style={{ fontWeight: 800, color: c }}>{pctile.toFixed(0)}th percentile of own 10yr</span>
            <span>expensive</span>
          </div>
        </div>
      )}

      {/* band detail */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 6 }}>
        <Tile label="10yr low" value={data.pe_min} />
        <Tile label="10yr median" value={data.pe_median} />
        <Tile label="10yr high" value={data.pe_max} />
      </div>

      {(data.current_pb !== null || data.pb_median !== null) && (
        <div style={{ fontSize: 11, color: T.textSub, marginTop: 8, background: T.bg, border: `1px solid ${T.border}`, borderRadius: 8, padding: "6px 10px" }}>
          P/B now <b style={{ color: T.text }}>{data.current_pb === null ? "—" : data.current_pb.toFixed(2)}</b>
          {data.pb_median !== null && <> · median {data.pb_median.toFixed(2)}</>}
          {data.pb_percentile !== null && <> · <span style={{ color: pcol(data.pb_percentile), fontWeight: 700 }}>{data.pb_percentile.toFixed(0)}th pctile</span></>}
        </div>
      )}

      <div style={{ fontSize: 9, color: T.textMeta, marginTop: 8, lineHeight: 1.5 }}>
        Today's P/E vs the stock's own {data.years ?? "~10"}-yr range (point-in-time, no look-ahead).
        Low percentile = cheap relative to its history, high = expensive. Pairs with DNA: <b>DNA = is it a
        good business, valuation = are you overpaying right now.</b> Not a fair-value call — context only.
      </div>
    </div>
  )
}

function Tile({ label, value }: { label: string; value: number | null }) {
  return (
    <div style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 8, padding: "6px 8px", textAlign: "center" }}>
      <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 800, color: T.text }}>{value === null ? "—" : value.toFixed(1)}</div>
    </div>
  )
}
