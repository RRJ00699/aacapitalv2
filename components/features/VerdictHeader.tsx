"use client"

import { useEffect, useState } from "react"

// ── VerdictHeader ────────────────────────────────────────────────────────────
// Renders the decomposed conviction scorecard for a stock: composite + 4 named
// sub-scores (each tap-to-explain), a generated plain-language read, the 💎
// conviction badge, and the honest "research signal, not a buy call" framing.
// Mounts ABOVE the existing Fundamentals/Technicals tabs — additive, not replacing.
//
// Usage:  <VerdictHeader symbol={symbol} />

type SubScore = { score: number | null; inputs: Record<string, any> }
type Scorecard = {
  ok: boolean
  symbol: string
  name?: string
  industry?: string
  price?: number | null
  market_cap?: number | null
  convergence: number | null
  read: string
  subscores: { quality: SubScore; smartMoney: SubScore; valuation: SubScore; momentum: SubScore }
  disclaimer: string
}

const LABELS: Record<string, string> = {
  quality: "Quality",
  smartMoney: "Smart money",
  valuation: "Valuation",
  momentum: "Momentum",
}

// score → semantic color (green strong / amber middling / muted weak)
function toneFor(n: number | null): string {
  if (n === null) return "var(--text-muted, #9ca3af)"
  if (n >= 65) return "#15803d"        // green-700
  if (n >= 45) return "#b45309"        // amber-700
  return "#6b7280"                      // gray-500 (weak, not alarming-red — honest, not punitive)
}

function fmtInput(k: string, v: any): string {
  if (v === null || v === undefined) return "—"
  if (k === "is_lender") return v ? "yes (debt N/A)" : "no"
  if (typeof v === "number") {
    if (k.includes("flow") || k.includes("cap")) return v.toLocaleString("en-IN")
    return (Math.round(v * 100) / 100).toString()
  }
  return String(v)
}

const INPUT_LABELS: Record<string, string> = {
  roce: "ROCE %", roe: "ROE %", opm_pct: "Op margin %", debt_to_equity: "Debt / equity",
  interest_coverage: "Int. coverage", business_dna_grade: "Business DNA", is_lender: "Lender",
  smart_money_signal: "Signal", bulk_net_flow: "Bulk net flow", bulk_deal_count: "Bulk deals",
  conviction_funds: "Conviction funds", funds: "Funds", pe_ratio: "PE", sector_pe: "Sector PE",
  return_3m: "3m return %", return_6m: "6m return %", earnings_category: "Earnings",
  pat_growth_1y: "PAT growth %", sector_rotation_score: "Sector rotation",
}

export default function VerdictHeader({ symbol }: { symbol: string }) {
  const [data, setData] = useState<Scorecard | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return
    setData(null); setErr(null); setOpen(null)
    fetch(`/api/stock/scorecard?sym=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => { if (j?.ok) setData(j); else setErr(j?.error || "no data") })
      .catch((e) => setErr(String(e)))
  }, [symbol])

  if (err) return null                 // fail quiet — don't show a broken panel
  if (!data) {
    return <div style={{ padding: "14px 16px", fontSize: 13, color: "var(--text-muted,#9ca3af)" }}>Loading scorecard…</div>
  }

  const subs = data.subscores
  const conviction = Number(subs.smartMoney?.inputs?.conviction_funds || 0)
  const fundsLabel = subs.smartMoney?.inputs?.funds

  const card: React.CSSProperties = {
    background: "var(--surface-2, #fff)", border: "0.5px solid var(--border, #e5e7eb)",
    borderRadius: 12, padding: "14px 16px",
  }
  const tile: React.CSSProperties = {
    background: "var(--surface-1, #f8f8f6)", borderRadius: 8, padding: "10px 12px", cursor: "pointer",
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 14 }}>
      <div style={card}>
        {/* header row */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 18, fontWeight: 500 }}>{data.symbol}</span>
              {conviction > 0 && (
                <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 6, background: "#e6f1fb", color: "#0c447c" }}>
                  💎 new MF buy ×{conviction}
                </span>
              )}
            </div>
            <div style={{ fontSize: 13, color: "var(--text-secondary,#6b7280)", marginTop: 2 }}>
              {data.name}{data.industry ? ` · ${data.industry}` : ""}
            </div>
          </div>
          {data.price != null && (
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 18, fontWeight: 500 }}>₹{data.price.toLocaleString("en-IN")}</div>
              {data.market_cap != null && (
                <div style={{ fontSize: 12, color: "var(--text-muted,#9ca3af)" }}>
                  MCap ₹{Math.round(data.market_cap).toLocaleString("en-IN")}Cr
                </div>
              )}
            </div>
          )}
        </div>

        {/* composite + read */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
          <span style={{ fontSize: 32, fontWeight: 500 }}>{data.convergence ?? "—"}</span>
          <span style={{ fontSize: 14, color: "var(--text-muted,#9ca3af)" }}>/100 conviction</span>
          <span style={{ fontSize: 13, color: "var(--text-secondary,#6b7280)", marginLeft: "auto", maxWidth: 320, textAlign: "right" }}>
            {data.read}
          </span>
        </div>

        {/* sub-score tiles */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginTop: 12 }}>
          {(["quality", "smartMoney", "valuation", "momentum"] as const).map((k) => {
            const s = subs[k]?.score ?? null
            return (
              <div key={k} style={tile} onClick={() => setOpen(open === k ? null : k)}>
                <div style={{ fontSize: 12, color: "var(--text-secondary,#6b7280)" }}>{LABELS[k]}</div>
                <div style={{ fontSize: 18, fontWeight: 500, color: toneFor(s) }}>{s ?? "—"}</div>
                <div style={{ height: 3, background: "var(--border,#e5e7eb)", borderRadius: 2, marginTop: 6 }}>
                  <div style={{ width: `${s ?? 0}%`, height: 3, background: toneFor(s), borderRadius: 2 }} />
                </div>
              </div>
            )
          })}
        </div>

        {/* tap-to-explain drawer */}
        {open && (
          <div style={{ marginTop: 10, padding: "10px 12px", background: "var(--surface-1,#f8f8f6)", borderRadius: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 6 }}>{LABELS[open]} · inputs</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "4px 16px" }}>
              {Object.entries(subs[open as keyof typeof subs].inputs).map(([k, v]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                  <span style={{ color: "var(--text-secondary,#6b7280)" }}>{INPUT_LABELS[k] || k}</span>
                  <span>{fmtInput(k, v)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ fontSize: 11, color: "var(--text-muted,#9ca3af)", marginTop: 10 }}>
          Tap any score to see its inputs. Research signal, not a buy call.
        </div>
      </div>

      {/* what-changed / conviction strip — only when there's something to say */}
      {conviction > 0 && (
        <div style={card}>
          <div style={{ fontSize: 12, color: "var(--text-secondary,#6b7280)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
            What changed
          </div>
          <div style={{ fontSize: 13 }}>
            <span style={{ color: "#0c447c" }}>💎 </span>
            {fundsLabel ? <span>{fundsLabel} </span> : null}
            <span style={{ color: "var(--text-secondary,#6b7280)" }}>
              {conviction === 1 ? "initiated a new position" : `${conviction} funds initiated new positions`} — fresh conviction
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
