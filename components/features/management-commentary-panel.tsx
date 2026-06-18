// components/features/management-commentary-panel.tsx
// Sprint 11: Management Commentary panel — used inside Stock Research Workspace
// Shows AI-extracted guidance, tone, order book, key drivers/risks
// Drop-in: import { ManagementCommentaryPanel } from "./management-commentary-panel"
// Usage:   <ManagementCommentaryPanel symbol="DIXON" quarter="Q4FY26" />

"use client"
import { useState, useEffect } from "react"

const C = {
  bg: "#FAFAF8", surface: "#FFFFFF", blue: "#2563EB", blueBg: "#EFF6FF",
  green: "#16A34A", amber: "#D97706", red: "#DC2626", purple: "#7c3aed",
  text: "#111827", border: "#E5E7EB", gray: "#6b7280",
}

const TONE_CONFIG: Record<string, { color: string; bg: string; emoji: string }> = {
  BULLISH:               { color: C.green,  bg: "#F0FDF4", emoji: "🟢" },
  CAUTIOUSLY_OPTIMISTIC: { color: "#059669", bg: "#ECFDF5", emoji: "🔵" },
  NEUTRAL:               { color: C.gray,   bg: "#F9FAFB", emoji: "⚪" },
  CAUTIOUS:              { color: C.amber,  bg: "#FEF3C7", emoji: "🟡" },
  BEARISH:               { color: C.red,    bg: "#FEF2F2", emoji: "🔴" },
}

const GUIDANCE_CONFIG: Record<string, { color: string; label: string }> = {
  RAISED:          { color: C.green,  label: "↑ Raised" },
  MAINTAINED:      { color: C.gray,   label: "→ Maintained" },
  LOWERED:         { color: C.red,    label: "↓ Lowered" },
  FIRST_GUIDANCE:  { color: C.blue,   label: "★ First guidance" },
  WITHDRAWN:       { color: C.red,    label: "✕ Withdrawn" },
  NOT_PROVIDED:    { color: C.gray,   label: "— Not provided" },
}

interface Commentary {
  id: number
  nse_symbol: string
  company_name: string
  quarter: string
  revenue_guidance: string | null
  margin_guidance: string | null
  order_book_cr: number | null
  order_book_coverage: string | null
  management_tone: string
  guidance_direction: string
  key_growth_drivers: string[]
  key_risks: string[]
  positive_surprises: string[]
  negative_surprises: string[]
  mgmt_quality_score: number | null
  data_source: string
  source_url: string | null
  confidence: string
  extraction_notes: string | null
  created_at: string
}

interface Props {
  symbol: string
  quarter?: string
}

export function ManagementCommentaryPanel({ symbol, quarter }: Props) {
  const [data, setData]       = useState<Commentary | null>(null)
  const [loading, setLoading] = useState(true)
  const [extracting, setExtracting] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return
    setLoading(true)
    setError(null)
    const url = quarter
      ? `/api/management-commentary?symbol=${symbol}&quarter=${quarter}`
      : `/api/management-commentary?symbol=${symbol}`
    fetch(url)
      .then(async r => {
        const body = await r.json().catch(() => null)
        if (!r.ok || !body) { setError("Failed to load"); setLoading(false); return }
        if (body.cached && body.latest) {
          setData(body.latest as Commentary)
        } else {
          setData(null) // no commentary yet
        }
        setLoading(false)
      })
      .catch(() => { setError("Network error"); setLoading(false) })
  }, [symbol, quarter])

  async function handleExtract() {
    setExtracting(true)
    setError(null)
    try {
      // Uses Screener.in scraper — no Claude API credits needed
      const res = await fetch("/api/management-commentary/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, force: true }),
      })
      const body = await res.json()
      if (!res.ok || !body.ok) {
        setError(body.error ?? `Run locally: python _scripts/score_management_commentary.py --symbols ${symbol}`)
        return
      }
      setData(null); setError(null); setTimeout(()=>window.location.reload(), 500)
    } catch {
      setError(`Run locally: python _scripts/score_management_commentary.py --symbols ${symbol}`)
    } finally {
      setExtracting(false)
    }
  }

  if (loading) return (
    <div style={{ padding: 12, color: C.gray, fontSize: 12 }}>
      Loading management commentary...
    </div>
  )

  if (!data) return (
    <div style={{ padding: 12, background: C.blueBg, borderRadius: 8,
      border: `1px solid #BFDBFE`, fontSize: 12 }}>
      <div style={{ color: C.blue, fontWeight: 600, marginBottom: 6 }}>
        📋 No commentary yet for {symbol}
      </div>
      <div style={{ color: C.gray, marginBottom: 10 }}>
        Extract management guidance, tone, and order book from latest earnings call.
      </div>
      <button
        onClick={handleExtract}
        disabled={extracting}
        style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px",
          background: extracting ? C.gray : C.blue, color: "#fff",
          border: "none", borderRadius: 6, cursor: extracting ? "not-allowed" : "pointer" }}
      >
        {extracting ? "Scraping Screener.in..." : "Extract Commentary"}
      </button>
      {error && <div style={{ color: C.red, fontSize: 11, marginTop: 6 }}>{error}</div>}
    </div>
  )

  const tone = TONE_CONFIG[data.management_tone] ?? TONE_CONFIG.NEUTRAL
  const guidance = GUIDANCE_CONFIG[data.guidance_direction] ?? GUIDANCE_CONFIG.NOT_PROVIDED
  const drivers = Array.isArray(data.key_growth_drivers) ? data.key_growth_drivers : []
  const risks = Array.isArray(data.key_risks) ? data.key_risks : []
  const positives = Array.isArray(data.positive_surprises) ? data.positive_surprises : []
  const negatives = Array.isArray(data.negative_surprises) ? data.negative_surprises : []

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Header row — tone + guidance + quarter */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: tone.color,
          background: tone.bg, padding: "3px 8px", borderRadius: 5 }}>
          {tone.emoji} {data.management_tone.replace(/_/g, " ")}
        </span>
        <span style={{ fontSize: 11, fontWeight: 600, color: guidance.color }}>
          {guidance.label}
        </span>
        <span style={{ fontSize: 10, color: C.gray, marginLeft: "auto" }}>
          {data.quarter} · {data.data_source === "PDF_EXTRACTION" ? "📄 PDF" : "🌐 Web"}
          {data.confidence === "HIGH" ? " · ✓ High confidence" : data.confidence === "MEDIUM" ? " · ~ Medium" : " · ⚠ Low"}
        </span>
      </div>

      {/* Guidance numbers */}
      {(data.revenue_guidance || data.margin_guidance || data.order_book_cr) && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {data.revenue_guidance && (
            <div style={{ background: "#F0FDF4", border: "1px solid #BBF7D0",
              borderRadius: 6, padding: "5px 10px", fontSize: 11 }}>
              <div style={{ color: C.gray, fontSize: 10 }}>Revenue guidance</div>
              <div style={{ fontWeight: 700, color: C.green }}>{data.revenue_guidance}</div>
            </div>
          )}
          {data.margin_guidance && (
            <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE",
              borderRadius: 6, padding: "5px 10px", fontSize: 11 }}>
              <div style={{ color: C.gray, fontSize: 10 }}>Margin guidance</div>
              <div style={{ fontWeight: 700, color: C.blue }}>{data.margin_guidance}</div>
            </div>
          )}
          {data.order_book_cr && (
            <div style={{ background: "#F5F3FF", border: "1px solid #DDD6FE",
              borderRadius: 6, padding: "5px 10px", fontSize: 11 }}>
              <div style={{ color: C.gray, fontSize: 10 }}>Order book</div>
              <div style={{ fontWeight: 700, color: C.purple }}>
                ₹{Number(data.order_book_cr).toLocaleString("en-IN")} Cr
                {data.order_book_coverage && ` · ${data.order_book_coverage}`}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Management quality score */}
      {data.mgmt_quality_score != null && (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: C.gray }}>Mgmt quality:</span>
          <span style={{ fontSize: 12, fontWeight: 700,
            color: Number(data.mgmt_quality_score) >= 70 ? C.green
              : Number(data.mgmt_quality_score) >= 50 ? C.amber : C.red }}>
            {data.mgmt_quality_score}/100
          </span>
        </div>
      )}

      {/* Growth drivers */}
      {drivers.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.gray,
            textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 4 }}>
            Growth drivers
          </div>
          {drivers.map((d, i) => (
            <div key={i} style={{ fontSize: 11, color: C.text, padding: "2px 0",
              paddingLeft: 8, borderLeft: `2px solid ${C.green}`, marginBottom: 3 }}>
              {d}
            </div>
          ))}
        </div>
      )}

      {/* Risks */}
      {risks.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.gray,
            textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 4 }}>
            Key risks
          </div>
          {risks.map((r, i) => (
            <div key={i} style={{ fontSize: 11, color: C.text, padding: "2px 0",
              paddingLeft: 8, borderLeft: `2px solid ${C.red}`, marginBottom: 3 }}>
              {r}
            </div>
          ))}
        </div>
      )}

      {/* Surprises */}
      {(positives.length > 0 || negatives.length > 0) && (
        <div style={{ display: "flex", gap: 8 }}>
          {positives.length > 0 && (
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 10, color: C.green, fontWeight: 700, marginBottom: 3 }}>
                ✓ Positive surprises
              </div>
              {positives.map((p, i) => (
                <div key={i} style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>· {p}</div>
              ))}
            </div>
          )}
          {negatives.length > 0 && (
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 10, color: C.red, fontWeight: 700, marginBottom: 3 }}>
                ✕ Negative surprises
              </div>
              {negatives.map((n, i) => (
                <div key={i} style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>· {n}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Re-extract button */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
        marginTop: 4, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
        <span style={{ fontSize: 10, color: C.gray }}>
          Extracted {new Date(data.created_at).toLocaleDateString("en-IN")}
        </span>
        <button
          onClick={handleExtract}
          disabled={extracting}
          style={{ fontSize: 10, color: C.blue, background: "none", border: "none",
            cursor: "pointer", textDecoration: "underline" }}
        >
          {extracting ? "Scraping..." : "Re-extract"}
        </button>
      </div>
      {error && <div style={{ color: C.red, fontSize: 11 }}>{error}</div>}
    </div>
  )
}
