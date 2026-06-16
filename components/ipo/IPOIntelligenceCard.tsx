"use client"
// components/ipo/IPOIntelligenceCard.tsx
// Displays the full AACapital IPO Alpha Engine output for one IPO.
// Data source: /api/ipo/intelligence?name=BLS+E-Services

import { useEffect, useState } from "react"

interface IpoIntelligence {
  company_name:  string
  symbol:        string
  sector:        string
  issue_price:   number
  listing_gain:  number
  archetype:     string
  lqi:           number
  p_above_10:    number
  p_loss:        number
  exp_return:    number
  confidence:    string
  action:        string
  qib_x:         number | null
  nii_x:         number | null
  gmp_pct:       number | null
  gmp_momentum:  string | null
  ofs_pct:       number | null
  ipo_pe:        number | null
  peer_pe:       number | null
  brlm:          string | null
  anchor:        string | null
  return_d30:    number | null
  return_d90:    number | null
  max_up:        number | null
  max_down:      number | null
  similar_ipos:  string[]
  updated_at:    string
}

interface Props {
  companyName?: string
  data?:        IpoIntelligence
}

function ActionBadge({ action }: { action: string }) {
  const styles: Record<string, string> = {
    "MOMENTUM CHASE": "bg-green-50 text-green-800 border-green-200",
    "VALUE DIP BUY":  "bg-blue-50  text-blue-800  border-blue-200",
    "TACTICAL HOLD":  "bg-amber-50 text-amber-800 border-amber-200",
    "AVOID":          "bg-red-50   text-red-800   border-red-200",
  }
  const cls = styles[action] || "bg-gray-50 text-gray-700 border-gray-200"
  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded border ${cls}`}>
      {action}
    </span>
  )
}

function LqiBar({ score }: { score: number }) {
  const color = score >= 80 ? "bg-green-500" : score >= 60 ? "bg-amber-500" : "bg-red-500"
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-medium w-8 text-right">{score}</span>
    </div>
  )
}

function ProbBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-gray-500 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
      <span className="w-10 text-right font-medium">{value.toFixed(1)}%</span>
    </div>
  )
}

function Field({ label, value, warn }: { label: string; value: React.ReactNode; warn?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-xs text-gray-400">{label}</span>
      <span className={`text-xs font-medium ${warn ? "text-red-600" : "text-gray-800"}`}>{value ?? "—"}</span>
    </div>
  )
}

export default function IPOIntelligenceCard({ companyName, data: propData }: Props) {
  const [data, setData]     = useState<IpoIntelligence | null>(propData || null)
  const [loading, setLoading] = useState(!propData && !!companyName)
  const [error, setError]   = useState("")

  useEffect(() => {
    if (propData) { setData(propData); return }
    if (!companyName) return
    setLoading(true)
    fetch(`/api/ipo/intelligence?name=${encodeURIComponent(companyName)}&limit=1`)
      .then(r => r.json())
      .then(j => {
        if (j.ok && j.ipos?.length) setData(j.ipos[0])
        else setError("IPO not found")
      })
      .catch(() => setError("Failed to load"))
      .finally(() => setLoading(false))
  }, [companyName, propData])

  if (loading) return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 animate-pulse">
      <div className="h-4 bg-gray-100 rounded w-48 mb-3" />
      <div className="h-3 bg-gray-100 rounded w-32" />
    </div>
  )

  if (error || !data) return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-400">
      {error || "No data"}
    </div>
  )

  const gmpWarn = data.gmp_pct !== null && data.gmp_pct < 5
  const peWarn  = data.ipo_pe !== null && data.peer_pe !== null &&
                  data.peer_pe > 0 && (data.ipo_pe / data.peer_pe) > 1.3

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">

      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold text-gray-900 text-base leading-tight">{data.company_name}</h3>
            <p className="text-xs text-gray-400 mt-0.5">{data.sector} · {data.symbol || "—"}</p>
          </div>
          <ActionBadge action={data.action} />
        </div>
      </div>

      <div className="px-5 py-4 space-y-5">

        {/* LQI */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs font-medium text-gray-500">LQI Score</span>
            <span className="text-xs text-gray-400">{data.confidence} confidence</span>
          </div>
          <LqiBar score={data.lqi} />
        </div>

        {/* Probabilities */}
        <div className="space-y-1.5">
          <ProbBar label="P(>10% gain)"   value={data.p_above_10} color="bg-green-500" />
          <ProbBar label="P(loss)"         value={data.p_loss}     color="bg-red-500"   />
          <div className="flex items-center gap-2 text-xs mt-1">
            <span className="w-20 text-gray-500 shrink-0">Exp. return</span>
            <span className={`font-semibold ${data.exp_return >= 0 ? "text-green-700" : "text-red-700"}`}>
              {data.exp_return > 0 ? "+" : ""}{data.exp_return.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Deal structure */}
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Deal</p>
          <Field label="Issue price"  value={data.issue_price ? `₹${data.issue_price}` : null} />
          <Field label="Listing gain" value={data.listing_gain ? `${data.listing_gain > 0 ? "+" : ""}${data.listing_gain.toFixed(1)}%` : null} />
          <Field label="OFS %"        value={data.ofs_pct !== null ? `${data.ofs_pct.toFixed(0)}%` : null} warn={data.ofs_pct !== null && data.ofs_pct > 60} />
          <Field label="Anchor"       value={data.anchor} />
          <Field label="BRLM"         value={data.brlm ? data.brlm.split(",")[0].trim() : null} />
        </div>

        {/* Subscription */}
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Subscription</p>
          <Field label="QIB"    value={data.qib_x    !== null ? `${data.qib_x.toFixed(1)}x`    : null} />
          <Field label="NII"    value={data.nii_x    !== null ? `${data.nii_x.toFixed(1)}x`    : null} />
          <Field label="Retail" value={data.retail_x !== null ? `${(data as any).retail_x.toFixed(1)}x` : null} />
        </div>

        {/* GMP */}
        {data.gmp_pct !== null && (
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Grey Market</p>
            <Field label="GMP %" value={`${data.gmp_pct.toFixed(1)}%`} warn={gmpWarn} />
            <Field label="Trend" value={data.gmp_momentum} />
            {gmpWarn && (
              <p className="text-xs text-amber-600 bg-amber-50 rounded px-2 py-1 mt-1">
                Low GMP — market not pricing listing alpha
              </p>
            )}
          </div>
        )}

        {/* Valuation */}
        {(data.ipo_pe || data.peer_pe) && (
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Valuation</p>
            <Field label="IPO P/E"    value={data.ipo_pe  ? `${data.ipo_pe.toFixed(1)}x`  : null} />
            <Field label="Peer P/E"   value={data.peer_pe ? `${data.peer_pe.toFixed(1)}x` : null} />
            {peWarn && (
              <p className="text-xs text-red-600 bg-red-50 rounded px-2 py-1 mt-1">
                Premium vs peers — valuation risk
              </p>
            )}
          </div>
        )}

        {/* Post-listing returns */}
        {(data.return_d30 !== null || data.return_d90 !== null) && (
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Actual returns</p>
            <Field label="Day 30" value={data.return_d30 !== null ? `${data.return_d30 > 0 ? "+" : ""}${data.return_d30.toFixed(1)}%` : null} />
            <Field label="Day 90" value={data.return_d90 !== null ? `${data.return_d90 > 0 ? "+" : ""}${data.return_d90.toFixed(1)}%` : null} />
            <Field label="Max up"   value={data.max_up   !== null ? `+${data.max_up.toFixed(1)}%`    : null} />
            <Field label="Max down" value={data.max_down !== null ? `${data.max_down.toFixed(1)}%`   : null} />
          </div>
        )}

        {/* Similar IPOs */}
        {data.similar_ipos?.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Similar IPOs</p>
            <div className="space-y-1">
              {data.similar_ipos.slice(0, 5).map((name, i) => (
                <div key={i} className="text-xs text-gray-600 flex items-center gap-1">
                  <span className="w-4 h-4 rounded-full bg-gray-100 flex items-center justify-center text-[10px] text-gray-400 shrink-0">{i + 1}</span>
                  {name}
                </div>
              ))}
            </div>
          </div>
        )}

      </div>

      {/* Footer */}
      <div className="px-5 py-2 bg-gray-50 border-t border-gray-100">
        <p className="text-[10px] text-gray-400">
          Updated {data.updated_at ? new Date(data.updated_at).toLocaleDateString("en-IN") : "—"}
          · AACapital Alpha Engine V3
        </p>
      </div>
    </div>
  )
}
