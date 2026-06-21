"use client"
// components/features/stocks-discovery.tsx
// THE unified stock intelligence screen.
// Replaces: Opportunities (6 sub-tabs) + Watchlist
// Discovery-first: browse what the engines found → click to drill in

import { useState, useEffect, useCallback, useRef } from "react"
import { Search, Star, RefreshCw, TrendingUp, Zap, ChevronRight } from "lucide-react"

// ── Design tokens (matches lib/design-tokens.ts) ─────────────────────────────
const T = {
  bg: "#FAFAF8", surface: "#FFFFFF", border: "#E5E7EB", hover: "#F8FAFC",
  text: "#111827", textSub: "#374151", meta: "#6B7280",
  green: "#16A34A", greenBg: "#F0FDF4", greenBd: "#BBF7D0",
  blue: "#2563EB", blueBg: "#EFF6FF", blueBd: "#BFDBFE",
  amber: "#D97706", amberBg: "#FFFBEB", amberBd: "#FDE68A",
  red: "#DC2626", redBg: "#FEF2F2",
  orange: "#EA580C", orangeBg: "#FFF7ED", orangeBd: "#FED7AA",
  teal: "#0D9488", tealBg: "#F0FDFA", tealBd: "#99F6E4",
  purple: "#7C3AED", grayBg: "#F3F4F6",
}

const scoreColor = (s: number) =>
  s >= 80 ? T.green : s >= 65 ? T.teal : s >= 50 ? T.amber : T.red

const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const pctFmt = (v: unknown) => {
  const x = n(v); return x === 0 ? "" : `${x > 0 ? "+" : ""}${x.toFixed(1)}%`
}

// ── Score ring ─────────────────────────────────────────────────────────────
function ScoreRing({ score, size = 36 }: { score: number; size?: number }) {
  const r    = (size - 5) / 2
  const circ = 2 * Math.PI * r
  const dash = Math.min(1, score / 100) * circ
  const col  = scoreColor(score)
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={T.border} strokeWidth={3.5}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={col} strokeWidth={3.5}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`}/>
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: 10, fontWeight: 800, fill: col }}>{score}</text>
    </svg>
  )
}

// ── Signal pill ────────────────────────────────────────────────────────────
function Pill({ text, color = T.blue }: { text: string; color?: string }) {
  return (
    <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
      background: color + "18", color, border: `1px solid ${color}30`, whiteSpace: "nowrap" }}>
      {text}
    </span>
  )
}

// ── Stock row ──────────────────────────────────────────────────────────────
function StockRow({
  stock, onSelect, onWatchlist, inWatchlist, compact = false,
}: {
  stock: any; onSelect: (s: string) => void;
  onWatchlist: (s: string, add: boolean) => void;
  inWatchlist: boolean; compact?: boolean;
}) {
  const score  = Math.round(n(stock.buy_zone_score ?? stock.mb_score ?? stock.score ?? stock.breakout_watch_score ?? 50))
  const change = n(stock.change_pct ?? stock.changePct ?? 0)
  const sym    = stock.symbol ?? stock.tradingsymbol ?? ""
  const name   = stock.company_name ?? stock.name ?? sym

  const signals: Array<{t: string; c: string}> = []
  if (stock.is_nr7 || stock.nr7)          signals.push({ t: "NR7",    c: T.orange })
  if (stock.above_ema200)                  signals.push({ t: "EMA200", c: T.green  })
  if (stock.volume_expansion)              signals.push({ t: "Vol↑",   c: T.purple })
  if (stock.breakout_watch_tier === "COILED")   signals.push({ t: "🔥 COILED",   c: T.orange })
  if (stock.breakout_watch_tier === "BUILDING") signals.push({ t: "⚡ BUILDING", c: T.amber  })
  const stageL = stock.stage_label ?? (stock.stage ? `Stage ${stock.stage}` : "")
  if (stageL) signals.push({ t: stageL, c: T.teal })

  return (
    <div
      onClick={() => onSelect(sym)}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: compact ? "8px 14px" : "11px 16px",
        cursor: "pointer", borderBottom: `1px solid #F3F4F6`,
        transition: "background .15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = T.hover)}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      <ScoreRing score={score} size={compact ? 32 : 36} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 800, color: T.text }}>{sym}</span>
          {signals.slice(0, 3).map(s => <Pill key={s.t} text={s.t} color={s.c} />)}
        </div>
        <div style={{ fontSize: 10, color: T.meta, truncate: true, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis", maxWidth: 200 }}>
          {name}
        </div>
      </div>

      {/* Change % */}
      {change !== 0 && (
        <span style={{ fontSize: 11, fontWeight: 700, color: change >= 0 ? T.green : T.red, flexShrink: 0 }}>
          {pctFmt(change)}
        </span>
      )}

      {/* Watchlist star */}
      <button
        onClick={e => { e.stopPropagation(); onWatchlist(sym, !inWatchlist) }}
        style={{ background: "none", border: "none", cursor: "pointer", padding: "2px 4px", flexShrink: 0 }}
      >
        <Star size={14} fill={inWatchlist ? T.amber : "none"}
          color={inWatchlist ? T.amber : T.meta} />
      </button>

      <ChevronRight size={12} color={T.meta} style={{ flexShrink: 0 }} />
    </div>
  )
}

// ── Section header ────────────────────────────────────────────────────────
function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div style={{ marginBottom: 8 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "8px 16px", background: T.grayBg, border: "none", cursor: "pointer",
          borderTop: `1px solid ${T.border}`, borderBottom: open ? `1px solid ${T.border}` : "none" }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, color: T.textSub, textTransform: "uppercase", letterSpacing: "0.07em" }}>
          {title} {count != null && <span style={{ color: T.meta, fontWeight: 400 }}>({count})</span>}
        </span>
        <span style={{ fontSize: 11, color: T.meta }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && <div style={{ background: T.surface }}>{children}</div>}
    </div>
  )
}

// ── Sector row ────────────────────────────────────────────────────────────
function SectorRow({ s }: { s: any }) {
  const perf   = n(s.return_3m ?? s.performance ?? s.return_6m)
  const score  = Math.round(n(s.rotation_score ?? s.score ?? 0))
  const color  = perf >= 0 ? T.green : T.red
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
      borderBottom: `1px solid #F3F4F6` }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{s.industry_group ?? s.name}</div>
        <div style={{ fontSize: 10, color: T.meta }}>{s.rotation_signal ?? s.signal ?? "Strong Rotate In"}</div>
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color, fontFamily: "monospace", minWidth: 58, textAlign: "right" }}>
        {perf >= 0 ? "+" : ""}{perf.toFixed(1)}%
      </span>
      <div style={{ width: 30, height: 30, borderRadius: "50%", background: T.blueBg,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 11, fontWeight: 800, color: T.blue }}>
        {score}
      </div>
    </div>
  )
}

// ── Empty state ─────────────────────────────────────────────────────────────
function Empty({ icon, msg, sub }: { icon: React.ReactNode; msg: string; sub?: string }) {
  return (
    <div style={{ padding: "28px 16px", textAlign: "center", color: T.meta }}>
      <div style={{ marginBottom: 10 }}>{icon}</div>
      <div style={{ fontSize: 13, color: T.textSub, fontWeight: 600 }}>{msg}</div>
      {sub && <div style={{ fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

// ── Skeleton loader ────────────────────────────────────────────────────────
function Skel({ n: count = 3 }: { n?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ height: 56, background: `#F3F4F6`, margin: "1px 0", opacity: 0.6 + i * 0.1 }} />
      ))}
    </>
  )
}

// ── Main component ──────────────────────────────────────────────────────────
export function StocksDiscovery({ onStockSelect }: { onStockSelect: (s: string) => void }) {
  const [signals,   setSignals]   = useState<any[]>([])
  const [bw,        setBw]        = useState<any[]>([])
  const [sectors,   setSectors]   = useState<any[]>([])
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [loading,   setLoading]   = useState(true)
  const [filter,    setFilter]    = useState("all")
  const [query,     setQuery]     = useState("")
  const [lastUpdate, setLastUpdate] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [sRes, bwRes, secRes, wlRes] = await Promise.all([
        fetch("/api/technical/screener?limit=50", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/breakout-watch", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/sector-rotation?view=hot", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/watchlists", { cache: "no-store" }).then(r => r.json()).catch(() => null),
      ])
      setSignals((sRes?.data ?? []).filter((x: any) => x.symbol && !/^(ANTELOP|ACUTAAS)/i.test(x.symbol)))
      setBw((bwRes?.data ?? []).filter((x: any) => x.breakout_watch_tier))
      setSectors((secRes?.hot_sectors ?? secRes?.sectors ?? []).slice(0, 8))
      setWatchlist((wlRes?.stocks ?? []).map((s: any) => s.symbol))
      setLastUpdate(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }))
    } catch { /* silent */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const toggleWatchlist = useCallback(async (sym: string, add: boolean) => {
    setWatchlist(prev => add ? [...prev, sym] : prev.filter(s => s !== sym))
    try {
      await fetch("/api/watchlists", {
        method: add ? "POST" : "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym }),
      })
    } catch { /* revert if needed */ }
  }, [])

  // ── Derived lists ──────────────────────────────────────────────────────────
  const q = query.trim().toLowerCase()

  const actNow = signals
    .filter(s => (n(s.buy_zone_score ?? s.mb_score) >= 70 || s.nr7 || s.is_nr7)
      && (!q || s.symbol?.toLowerCase().includes(q) || (s.company_name ?? "").toLowerCase().includes(q)))
    .sort((a, b) => n(b.buy_zone_score ?? b.mb_score) - n(a.buy_zone_score ?? a.mb_score))
    .slice(0, 12)

  const coiling = bw
    .filter(s => !q || s.symbol?.toLowerCase().includes(q) || (s.company_name ?? "").toLowerCase().includes(q))
    .slice(0, 10)

  const earnings = signals
    .filter(s => n(s.earnings_score ?? s.earnings ?? 0) >= 60
      && (!q || s.symbol?.toLowerCase().includes(q)))
    .slice(0, 8)

  const wlStocks = signals
    .filter(s => watchlist.includes(s.symbol))
    .concat(
      watchlist
        .filter(sym => !signals.some(s => s.symbol === sym))
        .map(sym => ({ symbol: sym }))
    )
    .filter(s => !q || s.symbol?.toLowerCase().includes(q))

  const filteredSectors = sectors.filter(s =>
    !q || (s.industry_group ?? "").toLowerCase().includes(q)
  )

  const FILTERS = [
    { id: "all",      label: "All",            count: actNow.length + coiling.length },
    { id: "actnow",   label: "🔥 Act Now",     count: actNow.length },
    { id: "coiling",  label: "⚡ Coiling",     count: coiling.length },
    { id: "sectors",  label: "📊 Sectors",     count: filteredSectors.length },
    { id: "watchlist",label: "⭐ Watchlist",   count: wlStocks.length },
  ]

  const show = (section: string) =>
    filter === "all" || filter === section

  const props = (stock: any) => ({
    stock,
    onSelect:    onStockSelect,
    onWatchlist: toggleWatchlist,
    inWatchlist: watchlist.includes(stock.symbol ?? stock.tradingsymbol),
  })

  return (
    <div style={{ background: T.bg, minHeight: "100vh", paddingBottom: 80 }}>

      {/* ── Search bar ─────────────────────────────────────────────────── */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "10px 14px", position: "sticky", top: 44, zIndex: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: T.grayBg,
          borderRadius: 10, padding: "7px 12px" }}>
          <Search size={14} color={T.meta} />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && query.trim()) onStockSelect(query.trim().toUpperCase())
            }}
            placeholder="Search or type symbol + Enter to open"
            style={{ flex: 1, background: "none", border: "none", outline: "none",
              fontSize: 13, color: T.text }}
          />
          {query && (
            <button onClick={() => setQuery("")}
              style={{ background: "none", border: "none", cursor: "pointer", color: T.meta, fontSize: 14 }}>
              ×
            </button>
          )}
          <button onClick={load}
            style={{ background: "none", border: "none", cursor: "pointer", color: T.meta }}>
            <RefreshCw size={13} />
          </button>
        </div>

        {/* Filter pills */}
        <div style={{ display: "flex", gap: 6, marginTop: 8, overflowX: "auto", paddingBottom: 2 }}>
          {FILTERS.map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)} style={{
              padding: "4px 12px", borderRadius: 20, fontSize: 11, cursor: "pointer",
              border: `1px solid ${filter === f.id ? T.blue : T.border}`,
              background: filter === f.id ? T.blueBg : "transparent",
              color: filter === f.id ? T.blue : T.meta,
              fontWeight: filter === f.id ? 700 : 400, whiteSpace: "nowrap",
            }}>
              {f.label} {f.count > 0 && <span style={{ opacity: 0.7 }}>({f.count})</span>}
            </button>
          ))}
          {lastUpdate && (
            <span style={{ fontSize: 10, color: T.meta, marginLeft: "auto",
              alignSelf: "center", whiteSpace: "nowrap" }}>
              {lastUpdate} IST
            </span>
          )}
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────────────── */}
      <div style={{ maxWidth: 800, margin: "0 auto" }}>

        {/* Act Now */}
        {show("actnow") && (
          <Section title="🔥 Act Now" count={actNow.length}>
            {loading ? <Skel /> : actNow.length === 0
              ? <Empty icon={<TrendingUp size={24} color={T.meta}/>}
                  msg="No high-conviction setups right now"
                  sub="Run generate_signals.py to refresh" />
              : actNow.map(s => <StockRow key={s.symbol} {...props(s)} />)
            }
          </Section>
        )}

        {/* Coiling / Breakout Watch */}
        {show("coiling") && (
          <Section title="⚡ Coiling — pre-breakout" count={coiling.length}>
            {loading ? <Skel /> : coiling.length === 0
              ? <Empty icon={<Zap size={24} color={T.meta}/>}
                  msg="No breakout setups detected"
                  sub="Scores refresh daily after market close" />
              : coiling.map(s => <StockRow key={s.symbol} {...props(s)} />)
            }
          </Section>
        )}

        {/* Sector Leaders */}
        {show("sectors") && filteredSectors.length > 0 && (
          <Section title="📊 Leading Sectors" count={filteredSectors.length}>
            {loading ? <Skel n={4} />
              : filteredSectors.map((s, i) => <SectorRow key={i} s={s} />)
            }
          </Section>
        )}

        {/* Watchlist */}
        {show("watchlist") && (
          <Section title="⭐ Your Watchlist" count={wlStocks.length}>
            {loading ? <Skel n={2} /> : wlStocks.length === 0
              ? <Empty icon={<Star size={24} color={T.meta}/>}
                  msg="No stocks in watchlist"
                  sub="Tap ⭐ on any stock to add it here" />
              : wlStocks.map(s => <StockRow key={s.symbol} {...props(s)} />)
            }
          </Section>
        )}

        {/* Empty overall */}
        {!loading && actNow.length === 0 && coiling.length === 0 && query && (
          <Empty icon={<Search size={28} color={T.meta}/>}
            msg={`No results for "${query}"`}
            sub="Press Enter to open the stock directly" />
        )}
      </div>
    </div>
  )
}
