"use client"
// components/MobileApp.tsx
// Dedicated iPhone layout — bottom nav, card-based
// Rendered when window.innerWidth < 768

import { useState, useEffect, useCallback } from "react"
import { WatchlistScreen } from "./features/watchlist-screen"
import { StockResearchWorkspace } from "./features/stock-research-workspace"

const T = {
  bg:"#F7F9FC", surface:"#FFFFFF", border:"#E5E7EB",
  text:"#0F172A", textSub:"#64748B", textMeta:"#94A3B8",
  green:"#16A34A", greenBg:"#F0FDF4",
  blue:"#2563EB",  blueBg:"#EFF6FF",
  amber:"#D97706", amberBg:"#FFFBEB",
  red:"#DC2626",   redBg:"#FEF2F2",
  teal:"#0D9488",  tealBg:"#F0FDFA",
  purple:"#7C3AED",
}
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const SUPPRESS = /^(ANTELOP|ACUTAAS|BMWVENTURE)/i

function MCard({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 14, padding: "12px 14px", marginBottom: 8, ...style }}>
      {children}
    </div>
  )
}

function MLabel({ children }: { children: string }) {
  return <div style={{ fontSize: 9, fontWeight: 700, color: T.textMeta,
    textTransform: "uppercase" as const, letterSpacing: "0.08em", marginBottom: 5 }}>{children}</div>
}

// ── Search overlay ────────────────────────────────────────────────────────────
function MobileSearch({ onSelect, onClose }: { onSelect: (s: string) => void; onClose: () => void }) {
  const [query,    setQuery]    = useState("")
  const [results,  setResults]  = useState<any[]>([])
  const [loading,  setLoading]  = useState(false)

  useEffect(() => {
    if (!query.trim() || query.length < 1) { setResults([]); return }
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=8`)
        const d = await r.json()
        setResults(d.results ?? d.stocks ?? [])
      } catch {}
      finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  return (
    <div style={{ position: "fixed", inset: 0, background: T.surface, zIndex: 100,
      display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${T.border}`,
        display: "flex", gap: 10, alignItems: "center" }}>
        <input autoFocus value={query} onChange={e => setQuery(e.target.value.toUpperCase())}
          placeholder="Search stocks e.g. INFY, TATA…"
          style={{ flex: 1, padding: "10px 14px", borderRadius: 10, border: `1px solid ${T.border}`,
            fontSize: 15, fontFamily: "inherit", outline: "none", background: T.bg }}/>
        <button onClick={onClose} style={{ padding: "10px 14px", borderRadius: 10,
          border: `1px solid ${T.border}`, background: T.surface, fontSize: 13,
          cursor: "pointer", color: T.textSub }}>Cancel</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto" as const, padding: "8px 14px" }}>
        {loading && <div style={{ padding: 20, textAlign: "center" as const, color: T.textMeta }}>Searching…</div>}
        {results.map((r: any) => (
          <div key={r.nse_symbol ?? r.symbol} onClick={() => { onSelect(r.nse_symbol ?? r.symbol); onClose() }}
            style={{ padding: "12px 0", borderBottom: `1px solid ${T.border}`, cursor: "pointer" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{r.nse_symbol ?? r.symbol}</div>
            <div style={{ fontSize: 12, color: T.textSub }}>{r.name} · {r.industry ?? ""}</div>
          </div>
        ))}
        {!loading && results.length === 0 && query.length > 0 && (
          <div style={{ padding: 20, textAlign: "center" as const, color: T.textMeta }}>
            No results for "{query}"
          </div>
        )}
      </div>
    </div>
  )
}

// ── Today screen ─────────────────────────────────────────────────────────────
function MobileToday({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [snap,    setSnap]    = useState<any>(null)
  const [global,  setGlobal]  = useState<any>(null)
  const [signals, setSignals] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshed, setRefreshed] = useState("")

  const load = useCallback(async () => {
    try {
      const [sRes, gRes, tRes] = await Promise.all([
        fetch("/api/market/snapshot", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/market/global",   { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/technical/screener?limit=8", { cache: "no-store" }).then(r => r.json()).catch(() => null),
      ])
      setSnap(sRes?.data ?? sRes)
      // global has india + global keys
      const globalData = gRes?.global ?? gRes?.data ?? gRes ?? {}
      setGlobal(globalData)
      setSignals((tRes?.data ?? []).filter((x: any) => !SUPPRESS.test(x.symbol || "")))
      setRefreshed(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }))
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    load()
    // Auto-refresh every 60s during market hours
    const isMarketHours = () => {
      const ist = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }))
      const mins = ist.getHours() * 60 + ist.getMinutes()
      const day  = ist.getDay()
      return day >= 1 && day <= 5 && mins >= 555 && mins <= 930
    }
    const timer = setInterval(() => { if (isMarketHours()) load() }, 60000)
    // Always refetch when the app regains focus/visibility (fixes stale data on reopen,
    // e.g. opening the app in the evening still showed yesterday's signals)
    const onVisible = () => { if (document.visibilityState === "visible") load() }
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("focus", load)
    return () => {
      clearInterval(timer)
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("focus", load)
    }
  }, [load])

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "60vh", flexDirection: "column", gap: 12, color: T.textMeta }}>
      <div style={{ fontSize: 32 }}>⚡</div>
      <div style={{ fontSize: 13 }}>Loading…</div>
    </div>
  )

  const s = snap ?? {}
  const regime      = (s.regime ?? s.active_regime ?? s.market_regime ?? "NORMAL").toString().toUpperCase()
  const regimeColor = regime === "HOT" ? T.red : regime === "NORMAL" ? T.teal : T.amber
  const nifty       = n(s.nifty_price ?? s.nifty ?? s.index_price ?? s.nifty50)
  const bankNifty   = n(s.banknifty_price ?? s.banknifty ?? s.bank_nifty)
  const vix         = n(s.vix ?? s.india_vix ?? s.vix_index)
  const pcr         = n(s.pcr)
  const fiiNet      = n(s.fii_net ?? s.fii_cash_flow ?? s.fii_flow)
  const diiNet      = n(s.dii_net ?? s.dii_cash_flow ?? s.dii_flow)

  // Global markets — handle both array and object formats
  const globalList: Array<{label:string; chg:number}> = []
  if (global && typeof global === "object") {
    const entries = Array.isArray(global) ? global :
      Object.entries(global).map(([k, v]: any) => ({ label: v?.name ?? k, changePct: v?.changePct ?? v?.change_pct }))
    entries.slice(0, 20).forEach((e: any) => {
      const label = e.label ?? e.name ?? e.symbol ?? ""
      const chg   = n(e.changePct ?? e.change_pct ?? e.changePercent)
      if (label) globalList.push({ label, chg })
    })
  }

  return (
    <div style={{ padding: "12px 14px", paddingBottom: 80 }}>

      {/* Refresh indicator */}
      {refreshed && (
        <div style={{ fontSize: 10, color: T.textMeta, textAlign: "right" as const, marginBottom: 6 }}>
          Updated {refreshed} IST · auto-refreshes during market hours
        </div>
      )}

      {/* Regime */}
      <MCard style={{ background: `${regimeColor}12`, border: `1px solid ${regimeColor}30` }}>
        <MLabel>Macro regime</MLabel>
        <div style={{ fontSize: 26, fontWeight: 800, color: regimeColor, marginBottom: 2 }}>{regime}</div>
        <div style={{ fontSize: 12, color: T.textSub }}>
          {regime === "HOT" ? "Risk-on · Deploy 80–100%" :
           regime === "NORMAL" ? "Deploy selectively · 50–70%" : "Be cautious · 20–40%"}
        </div>
      </MCard>

      {/* Indices */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
        {[
          { label: "NIFTY 50",   value: nifty > 0 ? nifty.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—", color: T.text, live: true },
          { label: "BANK NIFTY", value: bankNifty > 0 ? bankNifty.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—", color: T.text },
          { label: "VIX",   value: vix > 0 ? vix.toFixed(2) : "—", color: vix > 20 ? T.red : T.green },
          { label: "PCR",   value: pcr > 0 ? pcr.toFixed(2) : "—", color: pcr > 1 ? T.green : T.red },
        ].map(c => (
          <MCard key={c.label} style={{ padding: "10px 12px", marginBottom: 0 }}>
            <MLabel>{c.label}</MLabel>
            <div style={{ fontSize: 20, fontWeight: 700, color: c.color }}>{c.value}</div>
          </MCard>
        ))}
      </div>

      {/* FII/DII */}
      <MCard>
        <MLabel>Institutional flows</MLabel>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {[{ label: "FII", val: fiiNet }, { label: "DII", val: diiNet }].map(f => (
            <div key={f.label}>
              <div style={{ fontSize: 11, color: T.textSub, marginBottom: 2 }}>{f.label}</div>
              <div style={{ fontSize: 17, fontWeight: 700, color: f.val >= 0 ? T.green : T.red }}>
                {f.val >= 0 ? "+" : ""}₹{Math.abs(f.val).toLocaleString("en-IN", { maximumFractionDigits: 0 })}Cr
              </div>
            </div>
          ))}
        </div>
      </MCard>

      {/* Top signals */}
      {signals.length > 0 && (
        <MCard>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6}}>
            <MLabel>Top signals</MLabel>
            <span style={{fontSize:10,color:T.textMeta}}>{signals.length} stocks</span>
          </div>
          <div style={{maxHeight:280,overflowY:"auto" as const}}>
          {signals.map((sig: any) => (
            <div key={sig.symbol} onClick={() => onStockSelect(sig.symbol)}
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "9px 0", borderBottom: `1px solid ${T.border}`, cursor: "pointer" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{sig.symbol}</span>
                  {(sig.is_nr7 || sig.nr7) && (
                    <span style={{ fontSize: 9, background: "#F5F3FF", color: T.purple,
                      padding: "1px 6px", borderRadius: 20, fontWeight: 700 }}>NR7</span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: T.textSub }}>{sig.company_name || ""}</div>
              </div>
              <div style={{ fontSize: 20, fontWeight: 800,
                color: n(sig.buy_zone_score) >= 70 ? T.green : n(sig.buy_zone_score) >= 55 ? T.amber : T.textSub }}>
                {Math.round(n(sig.buy_zone_score || sig.probability_score || 0)) || "—"}
              </div>
            </div>
          ))}
          </div>
        </MCard>
      )}

      {/* Global markets */}
      {globalList.length > 0 && (
        <MCard>
          <MLabel>Global markets</MLabel>
          <div style={{maxHeight:200,overflowY:"auto" as const}}>
          {globalList.map(g => (
            <div key={g.label} style={{ display: "flex", justifyContent: "space-between",
              padding: "6px 0", borderBottom: `1px solid ${T.border}`, fontSize: 12 }}>
              <span style={{ color: T.textSub }}>{g.label}</span>
              <span style={{ fontWeight: 600, color: g.chg >= 0 ? T.green : T.red }}>
                {g.chg >= 0 ? "+" : ""}{g.chg.toFixed(2)}%
              </span>
            </div>
          ))}
          </div>
        </MCard>
      )}
    </div>
  )
}

// ── Opportunities (mobile) ────────────────────────────────────────────────────
// ── IPO (mobile) ─────────────────────────────────────────────────────────────
function MobileIPO({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [ipos, setIpos] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/ipo/playbook?limit=20", { cache: "no-store" })
      .then(r => r.json())
      .then(d => {
        setIpos(d.rows ?? d.ipos ?? [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const PLAY_COLOR: Record<string, string> = {
    BUY_AT_OPEN: "#16A34A", WAIT_FOR_VWAP: "#2563EB",
    BUY_AFTER_DAY3: "#7C3AED", AVOID: "#DC2626",
  }

  if (loading) return (
    <div style={{ padding: "60px 16px", textAlign: "center" as const, color: T.textMeta }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>🚀</div>
      <div>Loading IPOs…</div>
    </div>
  )

  return (
    <div style={{ padding: "12px 14px", paddingBottom: 80 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: T.textMeta,
        textTransform: "uppercase" as const, letterSpacing: "0.08em", marginBottom: 10 }}>
        Upcoming & Recent IPOs
      </div>
      {ipos.length === 0 ? (
        <div style={{ padding: "40px 0", textAlign: "center" as const, color: T.textMeta }}>
          No IPO data — run sync script
        </div>
      ) : ipos.map((ipo: any) => {
        const play = ipo.play_recommendation || "—"
        const playColor = PLAY_COLOR[play] || T.textMeta
        const isUpcoming = !ipo.listing_date || new Date(ipo.listing_date) >= new Date()
        return (
          <div key={ipo.id ?? ipo.company_name}
            style={{ background: T.surface, border: `1px solid ${T.border}`,
              borderLeft: `3px solid ${playColor}`,
              borderRadius: 12, padding: "11px 13px", marginBottom: 7 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 2 }}>
                  {ipo.company_name}
                </div>
                <div style={{ fontSize: 11, color: T.textSub }}>
                  ₹{ipo.issue_price || "?"} · ₹{ipo.issue_size_cr || "?"}Cr
                </div>
                {isUpcoming && ipo.close_date && (
                  <div style={{ fontSize: 10, color: T.amber, marginTop: 2 }}>
                    Closes {ipo.close_date}
                  </div>
                )}
                {ipo.listing_date && !isUpcoming && (
                  <div style={{ fontSize: 10, color: T.textMeta, marginTop: 2 }}>
                    Listed {ipo.listing_date}
                    {ipo.return_listing_open ? ` · +${ipo.return_listing_open?.toFixed(1)}% open` : ""}
                  </div>
                )}
              </div>
              <div style={{ textAlign: "right" as const, marginLeft: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: playColor,
                  background: `${playColor}15`, padding: "2px 8px", borderRadius: 20 }}>
                  {play.replace(/_/g, " ")}
                </div>
                {ipo.play_confidence && (
                  <div style={{ fontSize: 10, color: T.textMeta, marginTop: 3 }}>
                    {ipo.play_confidence}% conf
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function MobileOpportunities({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [stocks,  setStocks]  = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState<"all"|"nr7"|"stage2">("all")

  useEffect(() => {
    fetch("/api/technical/screener?limit=50", { cache: "no-store" })
      .then(r => r.json())
      .then(d => {
        const data = (d?.data ?? []).filter((x: any) =>
          !SUPPRESS.test(x.symbol || "") &&
          ((x.buy_zone_score || 0) >= 35 || (x.conviction_score || 0) >= 40 || (x.probability_score || 0) >= 35)
        )
        setStocks(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = stocks.filter(s => {
    if (filter === "nr7")    return s.is_nr7 || s.nr7
    if (filter === "stage2") return s.stage === "2" || s.stage_label?.includes("2")
    return true
  })

  if (loading) return (
    <div style={{ padding: "60px 16px", textAlign: "center" as const, color: T.textMeta }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>📈</div>
      <div>Loading signals…</div>
    </div>
  )

  return (
    <div style={{ padding: "12px 14px", paddingBottom: 80 }}>
      {/* Filters */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12, overflowX: "auto" as const }}>
        {([["all","All"], ["nr7","NR7 only"], ["stage2","Stage 2"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setFilter(id)}
            style={{ padding: "6px 14px", borderRadius: 20, border: `1px solid ${filter===id?T.blue:T.border}`,
              background: filter===id ? T.blueBg : T.surface,
              color: filter===id ? T.blue : T.textSub,
              fontSize: 12, fontWeight: filter===id ? 700 : 400,
              cursor: "pointer", whiteSpace: "nowrap" as const, flexShrink: 0 }}>
            {label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={{ padding: "40px 0", textAlign: "center" as const, color: T.textMeta }}>
          No stocks match this filter
        </div>
      ) : filtered.map((s: any) => {
        const score = Math.round(n(s.buy_zone_score || s.probability_score || 0))
        return (
          <div key={s.symbol} onClick={() => onStockSelect(s.symbol)}
            style={{ background: T.surface, border: `1px solid ${T.border}`,
              borderLeft: `3px solid ${score >= 70 ? T.green : score >= 55 ? T.amber : T.textMeta}`,
              borderRadius: 12, padding: "11px 13px", marginBottom: 7,
              display: "flex", justifyContent: "space-between", alignItems: "center",
              cursor: "pointer" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: T.text }}>{s.symbol}</span>
                {(s.is_nr7 || s.nr7) && (
                  <span style={{ fontSize: 9, background: "#F5F3FF", color: T.purple,
                    padding: "1px 6px", borderRadius: 20, fontWeight: 700 }}>NR7</span>
                )}
              </div>
              <div style={{ fontSize: 11, color: T.textSub }}>
                {s.company_name || s.symbol} · {s.stage_label || ""}
              </div>
              <div style={{ fontSize: 10, color: T.textMeta, marginTop: 2 }}>
                6M: {n(s.momentum_6m) >= 0 ? "+" : ""}{n(s.momentum_6m).toFixed(1)}%
              </div>
            </div>
            <div style={{ fontSize: 24, fontWeight: 900,
              color: score >= 70 ? T.green : score >= 55 ? T.amber : T.textSub }}>
              {score || "—"}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Bottom nav ────────────────────────────────────────────────────────────────
const NAV_TABS = [
  { id: "today",  icon: "⚡", label: "Today"  },
  { id: "opps",   icon: "📈", label: "Signals" },
  { id: "watch",  icon: "⭐", label: "Watch"  },
  { id: "ipo",    icon: "🚀", label: "IPO"    },
]

// ── Mobile App root ───────────────────────────────────────────────────────────
export function MobileApp() {
  const [tab,       setTab]       = useState("today")
  const [workspace, setWorkspace] = useState<string | null>(null)
  const [showSearch,setShowSearch]= useState(false)

  if (workspace) return (
    <StockResearchWorkspace symbol={workspace} onClose={() => setWorkspace(null)}/>
  )

  if (showSearch) return (
    <MobileSearch onSelect={setWorkspace} onClose={() => setShowSearch(false)}/>
  )

  return (
    <div style={{ background: T.bg, minHeight: "100vh", maxWidth: 480, margin: "0 auto",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>

      {/* Sticky header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "10px 14px", display: "flex", alignItems: "center",
        justifyContent: "space-between", position: "sticky", top: 0, zIndex: 20,
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 30, height: 30, background: T.blue, borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, fontWeight: 800, color: "#fff", letterSpacing: "-0.5px" }}>AA</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text, lineHeight: 1.2 }}>AACapital</div>
            <div style={{ fontSize: 9, color: T.textMeta }}>Institutional Research</div>
          </div>
        </div>
        <button onClick={() => setShowSearch(true)}
          style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: 20,
            padding: "7px 14px", fontSize: 12, color: T.textSub, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6 }}>
          🔍 Search stock
        </button>
      </div>

      {/* Content */}
      <div style={{ paddingBottom: 70 }}>
        {tab === "today" && <MobileToday onStockSelect={setWorkspace}/>}
        {tab === "opps"  && <MobileOpportunities onStockSelect={setWorkspace}/>}
        {tab === "watch" && <WatchlistScreen onStockSelect={setWorkspace}/>}
        {tab === "ipo"   && <MobileIPO onStockSelect={setWorkspace}/>}
      </div>

      {/* Bottom nav */}
      <div style={{ position: "fixed", bottom: 0, left: "50%", transform: "translateX(-50%)",
        width: "100%", maxWidth: 480, background: T.surface,
        borderTop: `1px solid ${T.border}`, display: "flex",
        paddingBottom: "env(safe-area-inset-bottom, 8px)",
        boxShadow: "0 -2px 10px rgba(0,0,0,0.05)" }}>
        {NAV_TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ flex: 1, padding: "10px 0 6px", border: "none", background: "transparent",
              cursor: "pointer", display: "flex", flexDirection: "column" as const,
              alignItems: "center", gap: 2 }}>
            <div style={{ fontSize: 18 }}>{t.icon}</div>
            <div style={{ fontSize: 10, fontWeight: tab === t.id ? 700 : 400,
              color: tab === t.id ? T.blue : T.textMeta }}>{t.label}</div>
            {tab === t.id && (
              <div style={{ width: 18, height: 2, background: T.blue, borderRadius: 1 }}/>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
