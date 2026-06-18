// components/features/stock-search.tsx
// Universal stock search — queries DB directly by symbol or name
// Drop into any tab: <StockSearch onSelect={(sym) => setWorkspaceSymbol(sym)} />
// Works from any tab — Today, Discovery, Portfolio, IPO

"use client"
import { useState, useEffect, useRef } from "react"

const C = {
  surface: "#FFFFFF", border: "#E5E7EB", text: "#111827",
  blue: "#2563EB", green: "#16A34A", gray: "#6b7280",
  bg: "#F9FAFB", purple: "#7c3aed", amber: "#D97706",
}

interface SearchResult {
  symbol: string
  name: string
  industry: string
  price: number
  convergence: number
  business_grade: string
  business_score: number
  sm_score: number
  ob_score: number | null
  ob_coverage: string | null
  current_ob_cr: number | null
  earnings_momentum: number | null
  consecutive_beats: number | null
  is_nr7: boolean
  stage: string | null
  breakout_ready: boolean
}

function gradeColor(grade: string): string {
  return grade === "A+" ? C.purple : grade === "A" ? C.blue : grade === "B" ? C.amber : C.gray
}

function convColor(score: number): string {
  return score >= 70 ? C.purple : score >= 55 ? C.blue : score >= 40 ? C.amber : C.gray
}

interface Props {
  onSelect: (symbol: string) => void
  placeholder?: string
}

export function StockSearch({ onSelect, placeholder = "Search symbol or company name..." }: Props) {
  const [query, setQuery]     = useState("")
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen]       = useState(false)
  const ref                   = useRef<HTMLDivElement>(null)
  const timer                 = useRef<any>(null)

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  // Debounced search
  useEffect(() => {
    if (query.length < 2) { setResults([]); setOpen(false); return }
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
        const d   = await res.json()
        setResults(d.results ?? [])
        setOpen(true)
      } catch {
        setResults([])
        setOpen(true)
      }
      finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(timer.current)
  }, [query])

  function handleSelect(sym: string) {
    setQuery("")
    setResults([])
    setOpen(false)
    onSelect(sym)
  }

  return (
    <div ref={ref} style={{ position: "relative", width: "100%" }}>
      {/* Input */}
      <div style={{ position: "relative" }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => { if (results.length > 0) setOpen(true) }}
          onKeyDown={e => {
            if (e.key === "Escape") { setOpen(false); setQuery("") }
            if (e.key === "Enter") {
              e.preventDefault()
              const first = results[0]?.symbol || query.trim().toUpperCase()
              if (first) handleSelect(first)
            }
          }}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          style={{
            width: "100%", boxSizing: "border-box",
            border: `1px solid ${open ? C.blue : C.border}`,
            borderRadius: 10, padding: "10px 36px 10px 14px",
            fontSize: 13, background: C.surface, color: C.text,
            outline: "none", transition: "border-color 0.15s",
          }}
        />
        {/* Search icon / spinner */}
        <div style={{ position: "absolute", right: 12, top: "50%",
          transform: "translateY(-50%)", color: C.gray, fontSize: 14 }}>
          {loading ? "⟳" : "⌕"}
        </div>
      </div>

      {/* Dropdown */}
      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
          background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 10, boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
          zIndex: 99999, overflow: "hidden", maxHeight: 480, overflowY: "auto",
        }}>
          {results.map((r, i) => (
            <div
              key={r.symbol}
              onMouseDown={(e) => { e.preventDefault(); handleSelect(r.symbol) }}
              style={{
                padding: "10px 14px", cursor: "pointer",
                borderBottom: i < results.length - 1 ? `1px solid ${C.border}` : "none",
                background: "transparent",
                transition: "background 0.1s",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = C.bg)}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              {/* Row 1: symbol + badges */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
                  {r.symbol}
                </span>
                {/* Grade badge */}
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "1px 6px",
                  borderRadius: 4, background: `${gradeColor(r.business_grade)}15`,
                  color: gradeColor(r.business_grade),
                }}>
                  {r.business_grade}
                </span>
                {/* Convergence */}
                <span style={{
                  fontSize: 10, fontWeight: 600, padding: "1px 6px",
                  borderRadius: 4, background: `${convColor(r.convergence)}15`,
                  color: convColor(r.convergence),
                }}>
                  {r.convergence}
                </span>
                {/* NR7 badge */}
                {r.is_nr7 && (
                  <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px",
                    borderRadius: 3, background: "#F5F3FF", color: C.purple }}>
                    NR7
                  </span>
                )}
                {/* Breakout badge */}
                {r.breakout_ready && (
                  <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px",
                    borderRadius: 3, background: "#FFF7ED", color: C.amber }}>
                    BREAKOUT
                  </span>
                )}
                {/* Order book badge */}
                {r.ob_coverage === "STRONG" && (
                  <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px",
                    borderRadius: 3, background: "#F0FDF4", color: C.green }}>
                    OB {r.ob_score}
                  </span>
                )}
                {/* Price */}
                <span style={{ marginLeft: "auto", fontSize: 12,
                  fontWeight: 600, color: C.text }}>
                  ₹{Number(r.price).toLocaleString("en-IN")}
                </span>
              </div>

              {/* Row 2: company name + industry */}
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: C.gray }}>{r.name}</span>
                <span style={{ fontSize: 10, color: "#9CA3AF" }}>{r.industry}</span>
              </div>

              {/* Row 3: signal pills */}
              <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                {r.consecutive_beats && r.consecutive_beats >= 2 && (
                  <span style={{ fontSize: 9, color: C.green }}>
                    {r.consecutive_beats} consecutive beats
                  </span>
                )}
                {r.stage && (
                  <span style={{ fontSize: 9, color: C.gray }}>
                    Stage {r.stage}
                  </span>
                )}
                {r.sm_score >= 75 && (
                  <span style={{ fontSize: 9, color: C.blue }}>
                    Smart money: {r.sm_score}
                  </span>
                )}
                {r.current_ob_cr && (
                  <span style={{ fontSize: 9, color: C.green }}>
                    OB ₹{(r.current_ob_cr/1000).toFixed(1)}K Cr
                  </span>
                )}
              </div>
            </div>
          ))}

          {/* Footer */}
          <div style={{ padding: "6px 14px", background: C.bg,
            fontSize: 10, color: "#9CA3AF", borderTop: `1px solid ${C.border}` }}>
            {results.length} results · Click to open research workspace
          </div>
        </div>
      )}

      {/* No results */}
      {open && query.length >= 2 && results.length === 0 && !loading && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
          background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 10, padding: "14px", textAlign: "center",
          fontSize: 12, color: C.gray, zIndex: 99999,
        }}>
          No exact DB match for "{query}"
        </div>
      )}

      {open && query.length >= 2 && results.length === 0 && !loading && (
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); handleSelect(query.trim().toUpperCase()) }}
          style={{
            position: "absolute", top: "calc(100% + 52px)", left: 0, right: 0,
            background: "#EFF6FF", border: `1px solid ${C.blue}`,
            borderRadius: 10, padding: "10px 14px", textAlign: "center",
            fontSize: 12, color: C.blue, fontWeight: 700, zIndex: 99999, cursor: "pointer",
          }}
        >
          Open {query.trim().toUpperCase()} research workspace
        </button>
      )}
    </div>
  )
}
