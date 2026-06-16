"use client"
// components/ipo/IpoCommandCenter.tsx
// Main IPO Command Center — shows scored IPOs from engine + live search

import { useEffect, useState } from "react"
import IPOIntelligenceCard from "./IPOIntelligenceCard"

interface IpoSummary {
  company_name: string
  symbol:       string
  sector:       string
  lqi:          number
  p_above_10:   number
  exp_return:   number
  action:       string
  archetype:    string
  gmp_pct:      number | null
  qib_x:        number | null
}

const ACTION_FILTERS = ["All", "MOMENTUM CHASE", "VALUE DIP BUY", "TACTICAL HOLD", "AVOID"]

export default function IpoCommandCenter() {
  const [ipos,    setIpos]    = useState<IpoSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [search,  setSearch]  = useState("")
  const [filter,  setFilter]  = useState("All")
  const [selected, setSelected] = useState<string | null>(null)
  const [summary,  setSummary]  = useState({ momentum: 0, value: 0, avoid: 0, avg_lqi: 0 })

  useEffect(() => {
    setLoading(true)
    fetch("/api/ipo/intelligence?limit=50")
      .then(r => r.json())
      .then(j => {
        if (j.ok) {
          setIpos(j.ipos)
          setSummary(j.summary)
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const filtered = ipos.filter(ipo => {
    const matchName   = !search || ipo.company_name.toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === "All" || ipo.action === filter
    return matchName && matchFilter
  })

  const actionColor = (action: string) => {
    if (action === "MOMENTUM CHASE") return "text-green-700 bg-green-50"
    if (action === "VALUE DIP BUY")  return "text-blue-700  bg-blue-50"
    if (action === "AVOID")          return "text-red-700   bg-red-50"
    return "text-gray-600 bg-gray-50"
  }

  return (
    <div className="flex gap-4 h-full">

      {/* Left panel — list */}
      <div className="w-80 flex-shrink-0 flex flex-col gap-3">

        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-green-50 rounded-lg p-2 text-center">
            <p className="text-lg font-semibold text-green-800">{summary.momentum}</p>
            <p className="text-[10px] text-green-600">Chase</p>
          </div>
          <div className="bg-blue-50 rounded-lg p-2 text-center">
            <p className="text-lg font-semibold text-blue-800">{summary.value}</p>
            <p className="text-[10px] text-blue-600">Value</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-2 text-center">
            <p className="text-lg font-semibold text-gray-700">{summary.avg_lqi}</p>
            <p className="text-[10px] text-gray-500">Avg LQI</p>
          </div>
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search IPO..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:border-gray-400"
        />

        {/* Filter tabs */}
        <div className="flex gap-1 flex-wrap">
          {ACTION_FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                filter === f
                  ? "bg-gray-800 text-white border-gray-800"
                  : "bg-white text-gray-500 border-gray-200 hover:border-gray-300"
              }`}
            >
              {f === "MOMENTUM CHASE" ? "Chase" : f === "VALUE DIP BUY" ? "Value" : f}
            </button>
          ))}
        </div>

        {/* IPO list */}
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-14 bg-gray-50 rounded-lg animate-pulse" />
            ))
          ) : filtered.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No IPOs found</p>
          ) : filtered.map(ipo => (
            <button
              key={ipo.company_name}
              onClick={() => setSelected(ipo.company_name)}
              className={`w-full text-left rounded-lg border p-2.5 transition-colors ${
                selected === ipo.company_name
                  ? "border-gray-800 bg-gray-50"
                  : "border-gray-100 bg-white hover:border-gray-200"
              }`}
            >
              <div className="flex items-start justify-between gap-1">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-900 truncate">{ipo.company_name}</p>
                  <p className="text-[10px] text-gray-400">{ipo.sector}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs font-semibold text-gray-800">{ipo.lqi}</p>
                  <p className="text-[10px] text-gray-400">LQI</p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-1.5">
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${actionColor(ipo.action)}`}>
                  {ipo.action === "MOMENTUM CHASE" ? "Chase" :
                   ipo.action === "VALUE DIP BUY"  ? "Value" : ipo.action}
                </span>
                <span className="text-[10px] text-gray-500">
                  P(&gt;10%): {ipo.p_above_10?.toFixed(0)}%
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel — detail card */}
      <div className="flex-1 overflow-y-auto">
        {selected ? (
          <IPOIntelligenceCard companyName={selected} />
        ) : (
          <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
            Select an IPO to see full analysis
          </div>
        )}
      </div>

    </div>
  )
}
