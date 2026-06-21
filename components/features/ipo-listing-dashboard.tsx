"use client"
// components/features/ipo-listing-dashboard.tsx
// Live listing day dashboard — 10:00 to 10:30 AM
// Shows Kite signals: price vs VWAP, volume absorption, bid/ask, hold/exit verdict

import { useState, useEffect, useCallback, useRef } from "react"
import { RefreshCw, TrendingUp, TrendingDown, AlertTriangle, Clock, Zap } from "lucide-react"

const T = {
  bg: "#F7F9FC", surface: "#FFFFFF", border: "#E5E7EB", border2: "#F1F5F9",
  text: "#0F172A", sub: "#64748B", meta: "#94A3B8",
  green: "#16A34A", greenBg: "#F0FDF4", greenBd: "#BBF7D0",
  red: "#DC2626", redBg: "#FEF2F2", redBd: "#FECACA",
  amber: "#D97706", amberBg: "#FFFBEB", amberBd: "#FDE68A",
  blue: "#2563EB", blueBg: "#EFF6FF", blueBd: "#BFDBFE",
}

const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const pct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`

interface LiveSignals {
  symbol:         string
  company:        string
  issue_price:    number
  listing_open:   number
  current_price:  number
  vwap:           number
  volume:         number
  day1_float:     number
  bid_depth:      number
  ask_depth:      number
  high:           number
  low:            number
  oi:             number
  timestamp:      string
  // computed
  price_vs_vwap:  number
  price_vs_open:  number
  ftr:            number
  uc_threshold:   number
  lc_threshold:   number
  hold_signal:    "HOLD" | "EXIT" | "WATCH"
  hold_reason:    string
}

function HoldVerdict({ signals }: { signals: LiveSignals }) {
  const isHold = signals.hold_signal === "HOLD"
  const isExit = signals.hold_signal === "EXIT"
  const color  = isHold ? T.green : isExit ? T.red : T.amber
  const bg     = isHold ? T.greenBg : isExit ? T.redBg : T.amberBg
  const bd     = isHold ? T.greenBd : isExit ? T.redBd : T.amberBd
  const emoji  = isHold ? "✅" : isExit ? "🚨" : "⏳"

  return (
    <div style={{ background: bg, border: `2px solid ${color}`, borderRadius: 16,
      padding: "20px 24px", textAlign: "center" as const, marginBottom: 16 }}>
      <div style={{ fontSize: 40, marginBottom: 8 }}>{emoji}</div>
      <div style={{ fontSize: 28, fontWeight: 900, color }}>
        {signals.hold_signal === "HOLD" ? "HOLD 7 DAYS" :
         signals.hold_signal === "EXIT" ? "EXIT NOW" : "WATCH"}
      </div>
      <div style={{ fontSize: 13, color: T.sub, marginTop: 6, maxWidth: 320, margin: "6px auto 0" }}>
        {signals.hold_reason}
      </div>
    </div>
  )
}

function SignalRow({ label, value, color, detail }: {
  label: string; value: string; color: string; detail?: string
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "10px 0", borderBottom: `1px solid ${T.border2}` }}>
      <div>
        <div style={{ fontSize: 13, color: T.sub }}>{label}</div>
        {detail && <div style={{ fontSize: 11, color: T.meta }}>{detail}</div>}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}

function PriceBar({ current, open, vwap, uc, lc }: {
  current: number; open: number; vwap: number; uc: number; lc: number
}) {
  const min = lc * 0.98
  const max = uc * 1.02
  const range = max - min
  const pos = (v: number) => Math.max(0, Math.min(100, (v - min) / range * 100))

  return (
    <div style={{ margin: "16px 0" }}>
      <div style={{ position: "relative", height: 40, background: T.border2,
        borderRadius: 8, overflow: "hidden" }}>
        {/* LC zone */}
        <div style={{ position: "absolute", left: 0, top: 0, width: `${pos(lc)}%`,
          height: "100%", background: "#fecaca44" }}/>
        {/* UC zone */}
        <div style={{ position: "absolute", right: 0, top: 0,
          width: `${100 - pos(uc)}%`, height: "100%", background: "#bbf7d044" }}/>
        {/* VWAP line */}
        <div style={{ position: "absolute", left: `${pos(vwap)}%`, top: 0,
          width: 2, height: "100%", background: T.blue }}/>
        {/* Open line */}
        <div style={{ position: "absolute", left: `${pos(open)}%`, top: 0,
          width: 2, height: "100%", background: T.amber }}/>
        {/* Current price */}
        <div style={{ position: "absolute", left: `${pos(current)}%`, top: "50%",
          transform: "translate(-50%,-50%)",
          width: 16, height: 16, borderRadius: "50%",
          background: current > vwap ? T.green : T.red,
          border: "2px solid white", zIndex: 2 }}/>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between",
        fontSize: 10, color: T.meta, marginTop: 4 }}>
        <span>LC ₹{lc.toFixed(0)}</span>
        <span style={{ color: T.amber }}>Open ₹{open.toFixed(0)}</span>
        <span style={{ color: T.blue }}>VWAP ₹{vwap.toFixed(0)}</span>
        <span>UC ₹{uc.toFixed(0)}</span>
      </div>
    </div>
  )
}

export function IpoListingDashboard() {
  const [signals, setSignals]   = useState<LiveSignals | null>(null)
  const [loading, setLoading]   = useState(false)
  const [symbol, setSymbol]     = useState("")
  const [inputSym, setInputSym] = useState("")
  const [lastUpdate, setLast]   = useState<Date | null>(null)
  const [autoRefresh, setAuto]  = useState(false)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  const fetch = useCallback(async (sym: string) => {
    if (!sym) return
    setLoading(true)
    try {
      const r = await window.fetch(`/api/ipo/listing-day?symbol=${sym.toUpperCase()}`)
      if (r.ok) {
        const d = await r.json()
        if (d.signals) {
          setSignals(d.signals)
          setLast(new Date())
        }
      }
    } catch {}
    setLoading(false)
  }, [])

  // Auto-refresh every 5 minutes
  useEffect(() => {
    if (autoRefresh && symbol) {
      intervalRef.current = setInterval(() => fetch(symbol), 5 * 60 * 1000)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [autoRefresh, symbol, fetch])

  const onSearch = () => {
    setSymbol(inputSym.toUpperCase())
    fetch(inputSym.toUpperCase())
  }

  const now = new Date()
  const isListingWindow = now.getHours() === 10 && now.getMinutes() < 30

  return (
    <div style={{ background: T.bg, minHeight: "100vh", paddingBottom: 60 }}>

      {/* Header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "14px 20px", position: "sticky", top: 52, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: T.text }}>
              ⚡ Listing Day Dashboard
            </div>
            <div style={{ fontSize: 11, color: T.meta }}>
              {isListingWindow
                ? "🟢 Live window: 10:00–10:30 AM"
                : "Outside listing window — signals still valid for analysis"}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {lastUpdate && (
              <div style={{ fontSize: 11, color: T.meta }}>
                {lastUpdate.toLocaleTimeString("en-IN")}
              </div>
            )}
            <button onClick={() => setAuto(!autoRefresh)}
              style={{ padding: "5px 10px", borderRadius: 8, fontSize: 11,
                border: `1px solid ${autoRefresh ? T.green : T.border}`,
                background: autoRefresh ? T.greenBg : T.surface,
                color: autoRefresh ? T.green : T.sub, cursor: "pointer" }}>
              {autoRefresh ? "Auto ✓" : "Auto"}
            </button>
            {symbol && (
              <button onClick={() => fetch(symbol)} disabled={loading}
                style={{ display: "flex", alignItems: "center", gap: 5,
                  padding: "7px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
                  background: T.surface, fontSize: 12, color: T.sub, cursor: "pointer" }}>
                <RefreshCw size={12} className={loading ? "animate-spin" : ""}/>
                Refresh
              </button>
            )}
          </div>
        </div>

        {/* Symbol input */}
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <input
            value={inputSym}
            onChange={e => setInputSym(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && onSearch()}
            placeholder="Enter NSE symbol (e.g. BAJAJHFL)"
            style={{ flex: 1, padding: "8px 12px", borderRadius: 8,
              border: `1px solid ${T.border}`, fontSize: 14,
              fontFamily: "inherit", outline: "none" }}/>
          <button onClick={onSearch}
            style={{ padding: "8px 20px", borderRadius: 8,
              background: T.blue, color: "#fff", border: "none",
              fontSize: 14, fontWeight: 600, cursor: "pointer" }}>
            Load
          </button>
        </div>
      </div>

      <div style={{ maxWidth: 600, margin: "0 auto", padding: "16px" }}>

        {/* Empty state */}
        {!signals && !loading && (
          <div style={{ textAlign: "center" as const, padding: "60px 20px",
            color: T.meta }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
            <div style={{ fontSize: 15, fontWeight: 600, color: T.sub, marginBottom: 6 }}>
              Enter the NSE symbol of the IPO listing today
            </div>
            <div style={{ fontSize: 12 }}>
              The engine will show VWAP, volume absorption, bid/ask signals
            </div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              and tell you HOLD 7 DAYS or EXIT by 10:30 AM
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ textAlign: "center" as const, padding: "40px 0", color: T.meta }}>
            Loading Kite signals...
          </div>
        )}

        {/* Signals */}
        {signals && !loading && (
          <>
            {/* Company header */}
            <div style={{ background: T.surface, borderRadius: 12, padding: "14px 16px",
              marginBottom: 12, border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: T.text }}>
                {signals.company || signals.symbol}
              </div>
              <div style={{ fontSize: 12, color: T.meta }}>
                Issue price: ₹{signals.issue_price} · Listed open: ₹{signals.listing_open}
                · Float: {(signals.day1_float / 1e6).toFixed(1)}M shares
              </div>
            </div>

            {/* HOLD/EXIT verdict */}
            <HoldVerdict signals={signals}/>

            {/* Price bar */}
            <div style={{ background: T.surface, borderRadius: 12, padding: "14px 16px",
              marginBottom: 12, border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.sub,
                marginBottom: 8, textTransform: "uppercase" as const,
                letterSpacing: "0.08em" }}>Price map</div>
              <PriceBar
                current={signals.current_price}
                open={signals.listing_open}
                vwap={signals.vwap}
                uc={signals.uc_threshold}
                lc={signals.lc_threshold}/>
            </div>

            {/* Key signals */}
            <div style={{ background: T.surface, borderRadius: 12, padding: "14px 16px",
              marginBottom: 12, border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.sub,
                marginBottom: 4, textTransform: "uppercase" as const,
                letterSpacing: "0.08em" }}>Signals</div>

              <SignalRow
                label="Current price"
                value={`₹${signals.current_price.toFixed(1)} (${pct(signals.price_vs_open)})`}
                color={signals.current_price > signals.listing_open ? T.green : T.red}
                detail="vs listing open"/>

              <SignalRow
                label="Price vs VWAP"
                value={`₹${(signals.current_price - signals.vwap).toFixed(1)} (${pct(signals.price_vs_vwap)})`}
                color={signals.price_vs_vwap > 0 ? T.green : T.red}
                detail={signals.price_vs_vwap > 0 ? "Above VWAP → institutions accumulating" : "Below VWAP → distribution"}/>

              <SignalRow
                label="Float Turnover Ratio"
                value={`${(signals.ftr * 100).toFixed(0)}%`}
                color={signals.ftr > 0.8 ? T.green : signals.ftr > 0.5 ? T.amber : T.sub}
                detail={signals.ftr > 0.8 ? "Weak hands flushed → HOLD signal" : signals.ftr > 0.5 ? "Flushing in progress" : "Still early — watch"}/>

              <SignalRow
                label="Bid/Ask ratio"
                value={`${(signals.bid_depth / Math.max(signals.ask_depth, 1)).toFixed(1)}x`}
                color={signals.bid_depth > signals.ask_depth * 1.2 ? T.green : T.red}
                detail={signals.bid_depth > signals.ask_depth * 1.2 ? "More buyers than sellers" : "Selling pressure dominant"}/>

              <SignalRow
                label="UC distance"
                value={pct((signals.uc_threshold / signals.current_price - 1) * 100)}
                color={signals.current_price > signals.uc_threshold * 0.98 ? T.green : T.sub}
                detail={signals.current_price > signals.uc_threshold * 0.98 ? "🔴 Near UC — momentum strong" : "Room to UC"}/>

              <SignalRow
                label="Volume"
                value={`${(signals.volume / 1e5).toFixed(1)}L shares`}
                color={T.sub}
                detail={`${(signals.ftr * 100).toFixed(0)}% of day1 float traded`}/>
            </div>

            {/* Decision rules reminder */}
            <div style={{ background: T.border2, borderRadius: 10, padding: "12px 14px",
              fontSize: 12, color: T.sub, lineHeight: 1.8 }}>
              <div style={{ fontWeight: 600, color: T.text, marginBottom: 6 }}>
                10:30 AM decision rules (data-proven)
              </div>
              <div>✅ Price &gt; VWAP + FTR &gt; 80% + QIB 20-50x → <strong>HOLD 7 days</strong></div>
              <div>🚨 Price &lt; VWAP or FTR &lt; 40% → <strong>EXIT by EOD</strong></div>
              <div>🔴 Hit UC Day 1 → <strong>HOLD — +25.9% avg next 7 days</strong></div>
              <div>🔵 Hit LC Day 1 → <strong>EXIT immediately — -19.2% avg next 7 days</strong></div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
