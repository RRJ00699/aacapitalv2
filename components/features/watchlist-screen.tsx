"use client"
// components/features/watchlist-screen.tsx
// Full watchlist — add stocks, track convergence daily, remove stocks
// Uses /api/watchlists (GET/POST/DELETE) + /api/investment-command-center per stock

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, Plus, Trash2, TrendingUp, Bell, Star } from "lucide-react"

const T = {
  bg:"#F7F9FC", surface:"#FFFFFF", border:"#E5E7EB", border2:"#F1F5F9",
  text:"#0F172A", textSub:"#64748B", textMeta:"#94A3B8",
  green:"#16A34A", greenBg:"#F0FDF4", greenBd:"#BBF7D0",
  blue:"#2563EB",  blueBg:"#EFF6FF",  blueBd:"#BFDBFE",
  amber:"#D97706", amberBg:"#FFFBEB", amberBd:"#FDE68A",
  red:"#DC2626",   redBg:"#FEF2F2",   redBd:"#FECACA",
  purple:"#7C3AED",purpleBg:"#F5F3FF",purpleBd:"#E9D5FF",
}
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0

function convColor(s: number) {
  return s >= 75 ? T.purple : s >= 60 ? T.blue : s >= 45 ? T.amber : T.textMeta
}
function convBg(s: number) {
  return s >= 75 ? T.purpleBg : s >= 60 ? T.blueBg : s >= 45 ? T.amberBg : T.bg
}

function ScoreRing({ score }: { score: number }) {
  const size = 44, r = 17, circ = 2 * Math.PI * r
  const color = convColor(score)
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)", flexShrink: 0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={T.border} strokeWidth={4}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${(score/100)*circ} ${circ}`} strokeLinecap="round"/>
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
        style={{transform:"rotate(90deg)",transformOrigin:"center",fontSize:11,fontWeight:700,fill:color}}>
        {Math.round(score)||"—"}
      </text>
    </svg>
  )
}

export function WatchlistScreen({ onStockSelect }: { onStockSelect?: (s: string) => void }) {
  const [stocks,    setStocks]    = useState<any[]>([])
  const [details,   setDetails]   = useState<Record<string, any>>({})
  const [loading,   setLoading]   = useState(true)
  const [adding,    setAdding]    = useState(false)
  const [input,     setInput]     = useState("")
  const [error,     setError]     = useState<string | null>(null)
  const [removing,  setRemoving]  = useState<string | null>(null)

  const loadWatchlist = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch("/api/watchlists")
      const d = await r.json()
      const list = d.stocks ?? []
      setStocks(list)
      // Fetch convergence for each stock
      const results = await Promise.all(
        list.map((s: any) =>
          fetch(`/api/investment-command-center?symbol=${s.symbol}`, { cache: "no-store" })
            .then(r => r.json()).catch(() => null)
        )
      )
      const map: Record<string, any> = {}
      results.forEach((r, i) => { if (r?.ok) map[list[i].symbol] = r })
      setDetails(map)
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadWatchlist() }, [loadWatchlist])

  async function addStock() {
    const sym = input.trim().toUpperCase()
    if (!sym) return
    setAdding(true); setError(null)
    try {
      const r = await fetch("/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym }),
      })
      const d = await r.json()
      if (!r.ok) { setError(d.error ?? "Failed to add"); return }
      setInput("")
      await loadWatchlist()
    } catch { setError("Failed to add stock") }
    finally { setAdding(false) }
  }

  async function removeStock(sym: string) {
    setRemoving(sym)
    try {
      await fetch("/api/watchlists", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym }),
      })
      await loadWatchlist()
    } catch {}
    finally { setRemoving(null) }
  }

  const nr7Count      = stocks.filter(s => details[s.symbol]?.technical?.is_nr7).length
  const highConv      = stocks.filter(s => n(details[s.symbol]?.scores?.convergence) >= 60).length
  const alerts        = stocks.filter(s => {
    const conv = n(details[s.symbol]?.scores?.convergence)
    return conv >= 70 || details[s.symbol]?.technical?.is_nr7
  }).length

  return (
    <div style={{ background: T.bg, minHeight: "100vh", paddingBottom: 80 }}>

      {/* Header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "16px 20px", position: "sticky", top: 52, zIndex: 9 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Star size={18} color={T.amber} fill={T.amber}/>
              <span style={{ fontSize: 20, fontWeight: 700, color: T.text }}>Watchlist</span>
            </div>
            <div style={{ fontSize: 12, color: T.textSub, marginTop: 2 }}>
              {stocks.length} stocks · {nr7Count} NR7 · {highConv} high conviction
            </div>
          </div>
          <button onClick={loadWatchlist} style={{ display: "flex", alignItems: "center", gap: 5,
            padding: "7px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
            background: T.surface, fontSize: 12, color: T.textSub, cursor: "pointer" }}>
            <RefreshCw size={12}/> Refresh
          </button>
        </div>

        {/* Add stock input */}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <input value={input} onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && addStock()}
            placeholder="Add symbol e.g. INFY, TATAMOTORS…"
            style={{ flex: 1, padding: "9px 14px", borderRadius: 10, border: `1px solid ${T.border}`,
              fontSize: 13, fontFamily: "inherit", outline: "none", background: T.bg }}/>
          <button onClick={addStock} disabled={adding || !input.trim()}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 16px",
              borderRadius: 10, border: "none", background: input.trim() ? T.blue : T.border,
              color: input.trim() ? "#fff" : T.textMeta, fontSize: 13, fontWeight: 600,
              cursor: input.trim() ? "pointer" : "default" }}>
            <Plus size={14}/> {adding ? "Adding…" : "Add"}
          </button>
        </div>
        {error && <div style={{ fontSize: 11, color: T.red, marginTop: 6 }}>{error}</div>}
      </div>

      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Summary stats */}
        {stocks.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginBottom: 14 }}>
            {[
              { label: "Stocks tracked", value: stocks.length, color: T.blue,   bg: T.blueBg   },
              { label: "High conviction", value: highConv,      color: T.purple, bg: T.purpleBg },
              { label: "Action alerts",   value: alerts,        color: T.amber,  bg: T.amberBg  },
            ].map(c => (
              <div key={c.label} style={{ background: c.bg, borderRadius: 12,
                padding: "12px 14px", border: `1px solid ${c.color}20` }}>
                <div style={{ fontSize: 22, fontWeight: 800, color: c.color }}>{c.value}</div>
                <div style={{ fontSize: 11, color: T.textSub, marginTop: 2 }}>{c.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Stock list */}
        {loading ? (
          <div style={{ padding: "60px 0", textAlign: "center" as const, color: T.textMeta }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>⭐</div>
            <div>Loading watchlist…</div>
          </div>
        ) : stocks.length === 0 ? (
          <div style={{ background: T.surface, border: `1px dashed ${T.border}`,
            borderRadius: 16, padding: "48px 24px", textAlign: "center" as const }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>⭐</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 6 }}>
              No stocks in watchlist yet
            </div>
            <div style={{ fontSize: 13, color: T.textSub, marginBottom: 20 }}>
              Type a symbol above and press Enter to add
            </div>
            <div style={{ background: T.bg, border: `1px solid ${T.border}`,
              borderRadius: 10, padding: "12px 16px", fontSize: 12, color: T.textSub,
              textAlign: "left" as const }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>You'll get alerts when:</div>
              <div style={{ marginBottom: 4 }}>🔔 NR7 compression detected — breakout imminent</div>
              <div style={{ marginBottom: 4 }}>📈 Convergence score upgrades from below 60 to above 70</div>
              <div>💰 Price crosses your target level</div>
            </div>
          </div>
        ) : stocks.map((s: any) => {
          const d    = details[s.symbol]
          const conv = n(d?.scores?.convergence)
          const isNR7 = d?.technical?.is_nr7
          const price = n(d?.current_price)
          const name  = d?.name ?? s.symbol
          const industry = d?.industry ?? ""
          const rating   = d?.conviction?.rating ?? ""

          // Alert logic
          const alerts: string[] = []
          if (isNR7) alerts.push("NR7 — coiling for breakout")
          if (conv >= 70) alerts.push(`High conviction ${Math.round(conv)}/100`)
          if (conv < 35 && conv > 0) alerts.push("Conviction dropped — review position")

          return (
            <div key={s.symbol} style={{ background: T.surface,
              border: `1px solid ${alerts.length ? T.amber : T.border}`,
              borderLeft: `3px solid ${alerts.length ? T.amber : convColor(conv)}`,
              borderRadius: 14, marginBottom: 10, overflow: "hidden" }}>

              {/* Alert banner */}
              {alerts.length > 0 && (
                <div style={{ background: T.amberBg, padding: "6px 14px",
                  borderBottom: `1px solid ${T.amberBd}`,
                  display: "flex", alignItems: "center", gap: 6 }}>
                  <Bell size={11} color={T.amber}/>
                  <span style={{ fontSize: 11, color: T.amber, fontWeight: 600 }}>
                    {alerts[0]}
                  </span>
                </div>
              )}

              <div style={{ padding: "12px 14px", display: "flex",
                alignItems: "center", gap: 12 }}>

                <ScoreRing score={conv}/>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0, cursor: "pointer" }}
                  onClick={() => onStockSelect?.(s.symbol)}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: T.text }}>{s.symbol}</span>
                    {isNR7 && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px",
                        borderRadius: 20, background: T.purpleBg, color: T.purple }}>NR7</span>
                    )}
                    {rating && (
                      <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 20,
                        background: convBg(conv), color: convColor(conv), fontWeight: 600 }}>
                        {rating}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: T.textSub }}>{name} · {industry}</div>
                  <div style={{ fontSize: 11, color: T.textMeta, marginTop: 3 }}>
                    Added {new Date(s.added_at).toLocaleDateString("en-IN")}
                    {price > 0 && ` · ₹${price.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                  </div>
                </div>

                {/* Action buttons */}
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <button onClick={() => onStockSelect?.(s.symbol)}
                    style={{ padding: "6px 12px", borderRadius: 8, border: `1px solid ${T.blueBd}`,
                      background: T.blueBg, color: T.blue, fontSize: 11, fontWeight: 600,
                      cursor: "pointer" }}>
                    <TrendingUp size={12}/>
                  </button>
                  <button onClick={() => removeStock(s.symbol)}
                    disabled={removing === s.symbol}
                    style={{ padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.redBd}`,
                      background: T.redBg, color: T.red, fontSize: 11, cursor: "pointer" }}>
                    <Trash2 size={12}/>
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
