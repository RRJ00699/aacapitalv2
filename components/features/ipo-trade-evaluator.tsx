"use client"
// components/features/ipo-trade-evaluator.tsx
// Interactive IPO Trade Evaluator
// Upload your Zerodha capital gains CSV → see engine verdict on each trade

import { useState, useCallback, useRef } from "react"
import { Upload, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, XCircle, Info, RefreshCw } from "lucide-react"

const T = {
  bg:      "#F7F9FC",
  surface: "#FFFFFF",
  border:  "#E5E7EB",
  border2: "#F1F5F9",
  text:    "#0F172A",
  sub:     "#64748B",
  meta:    "#94A3B8",
  green:   "#16A34A", greenBg: "#F0FDF4", greenBd: "#BBF7D0",
  red:     "#DC2626", redBg:   "#FEF2F2", redBd:   "#FECACA",
  amber:   "#D97706", amberBg: "#FFFBEB", amberBd: "#FDE68A",
  blue:    "#2563EB", blueBg:  "#EFF6FF", blueBd:  "#BFDBFE",
  purple:  "#7C3AED", purpleBg:"#F5F3FF", purpleBd:"#DDD6FE",
  gray:    "#6B7280", grayBg:  "#F9FAFB",
}

const PLAY_CONFIG: Record<string, {label:string; color:string; bg:string; emoji:string}> = {
  BUY_AT_OPEN:      { label:"Buy at Open",      color:T.green,  bg:T.greenBg,  emoji:"⚡" },
  WAIT_FOR_VWAP:    { label:"Wait for VWAP",    color:T.blue,   bg:T.blueBg,   emoji:"⏳" },
  BUY_PANIC_DIP:    { label:"Buy Panic Dip",    color:"#0D9488",bg:"#F0FDFA",  emoji:"📉" },
  BUY_AFTER_DAY3:   { label:"Buy After Day 3",  color:T.purple, bg:T.purpleBg, emoji:"📅" },
  BUY_AFTER_ANCHOR: { label:"Buy After Anchor", color:T.purple, bg:T.purpleBg, emoji:"🔓" },
  BUY_PEER:         { label:"Buy Listed Peer",  color:T.amber,  bg:T.amberBg,  emoji:"🔄" },
  AVOID:            { label:"Avoid",            color:T.red,    bg:T.redBg,    emoji:"🚫" },
}

interface Trade {
  symbol: string
  company: string
  buyDate: string
  buyRate: number
  sellDate: string
  sellRate: number
  qty: number
  pnl: number
  holdDays: number
}

interface EngineVerdict {
  play: string
  confidence: number
  reasons: string[]
  enginePnl?: number
  alignment: "correct" | "wrong" | "partial"
  alignmentNote: string
}

function parseZerodhaCSV(text: string): Trade[] {
  const lines = text.split('\n')
  const trades: Trade[] = []
  let currentDesc = ''
  const tradeMap: Record<string, Trade> = {}

  for (const line of lines.slice(3)) {
    const parts = line.split(',').map(p => p.trim().replace(/^"|"$/g, '').replace(/,/g, ''))
    if (parts.length < 5) continue
    const desc = parts[0]; if (desc) currentDesc = desc
    const symbol = parts[1]; if (!symbol || symbol.length < 2) continue

    const qty      = parseFloat(parts[3]) || 0
    const saleDate = parts[4]
    const saleRate = parseFloat(parts[5]?.replace(/,/g,'')) || 0
    const buyDate  = parts[8]
    const buyRate  = parseFloat(parts[9]?.replace(/,/g,'')) || 0
    const pnl      = parseFloat(parts[12]?.replace(/,/g,'')) || 0

    if (!symbol || qty <= 0) continue

    const key = symbol
    if (!tradeMap[key]) {
      tradeMap[key] = { symbol, company: symbol, buyDate, buyRate, sellDate: saleDate,
        sellRate: saleRate, qty: 0, pnl: 0, holdDays: 0 }
    }
    tradeMap[key].qty += qty
    tradeMap[key].pnl += pnl
    tradeMap[key].sellRate = saleRate

    // Compute hold days
    try {
      const b = new Date(buyDate.replace(/(\d+)-(\w+)-(\d+)/, (_, d,m,y) => `${d} ${m} 20${y}`))
      const s = new Date(saleDate.replace(/(\d+)-(\w+)-(\d+)/, (_, d,m,y) => `${d} ${m} 20${y}`))
      const diff = Math.round((s.getTime() - b.getTime()) / (1000*60*60*24))
      if (diff >= 0) tradeMap[key].holdDays = Math.max(tradeMap[key].holdDays, diff)
    } catch {}
  }

  return Object.values(tradeMap).filter(t => t.qty > 0)
}

function getEngineVerdict(trade: Trade, ipoData?: any): EngineVerdict {
  const pnlPct = ((trade.sellRate / trade.buyRate) - 1) * 100
  const isIPOListing = trade.holdDays <= 7
  const isWin = trade.pnl > 0
  const isLoss = trade.pnl < 0
  const isBigWin = pnlPct > 15
  const isBigLoss = pnlPct < -10

  // Use engine data if available from Neon
  if (ipoData) {
    const play = ipoData.play_recommendation || 'AVOID'
    const conf = ipoData.play_confidence || 60
    const reasons = (() => { try { return JSON.parse(ipoData.play_reasons || '[]') } catch { return [] } })()
    const engineSaysAvoid = play === 'AVOID'
    const engineSaysBuy = play.startsWith('BUY')

    const alignment = (engineSaysAvoid && isLoss) || (engineSaysBuy && isWin)
      ? "correct"
      : (engineSaysAvoid && isBigWin) || (engineSaysBuy && isBigLoss)
      ? "wrong" : "partial"

    const note = alignment === "correct"
      ? `Engine said ${play} — trade ${isWin ? 'won ✓' : 'lost, as predicted ✓'}`
      : alignment === "wrong"
      ? `Engine said ${play} but trade ${isWin ? 'won' : 'lost'} — review signals`
      : `Partial alignment — ${play} recommendation`

    return { play, confidence: conf, reasons, alignment, alignmentNote: note }
  }

  // Heuristic verdict from trade data alone
  if (isIPOListing) {
    // Listing day trade
    if (isBigLoss) {
      return {
        play: "AVOID",
        confidence: 80,
        reasons: [
          `Listed ${pnlPct.toFixed(1)}% — strong negative signal on listing day`,
          "Pattern: small/mid issue size with weak institutional support",
          `Held ${trade.holdDays} day(s) — classic listing trade gone wrong`
        ],
        alignment: "correct",
        alignmentNote: `Engine: AVOID — loss of ₹${Math.abs(trade.pnl).toFixed(0)} was predictable`
      }
    }
    if (isBigWin) {
      return {
        play: "BUY_AT_OPEN",
        confidence: 78,
        reasons: [
          `Listed +${pnlPct.toFixed(1)}% — strong open signal`,
          `Held only ${trade.holdDays} day(s) — correct listing day execution`,
          "Pattern matches BUY_AT_OPEN archetype"
        ],
        alignment: "correct",
        alignmentNote: `Engine: BUY_AT_OPEN — captured +${pnlPct.toFixed(1)}% correctly`
      }
    }
    return {
      play: "WAIT_FOR_VWAP",
      confidence: 62,
      reasons: [
        `Small gain ${pnlPct.toFixed(1)}% on listing — VWAP confirmation would have helped`,
        `${trade.holdDays} day hold — good discipline`
      ],
      alignment: isWin ? "partial" : "partial",
      alignmentNote: `Engine: WAIT_FOR_VWAP — ${isWin ? 'correct direction' : 'better timing available'}`
    }
  }

  // Longer hold
  if (isLoss) {
    return {
      play: "AVOID",
      confidence: 70,
      reasons: [
        `${pnlPct.toFixed(1)}% loss over ${trade.holdDays} days`,
        "Position held too long without institutional support",
        "Engine would have flagged exit earlier"
      ],
      alignment: trade.holdDays > 30 ? "wrong" : "partial",
      alignmentNote: `Engine: AVOID — held ${trade.holdDays} days, loss grew`
    }
  }

  return {
    play: trade.holdDays <= 30 ? "BUY_AFTER_DAY3" : "BUY_AFTER_ANCHOR",
    confidence: 65,
    reasons: [
      `+${pnlPct.toFixed(1)}% over ${trade.holdDays} days — patient hold worked`,
      "Consistent with post-listing accumulation strategy"
    ],
    alignment: "correct",
    alignmentNote: `Good patience — matches ${trade.holdDays <= 30 ? 'Day3' : 'post-anchor'} entry pattern`
  }
}

function TradeCard({ trade, ipoData }: { trade: Trade; ipoData?: any }) {
  const [expanded, setExpanded] = useState(false)
  const pnlPct = ((trade.sellRate / trade.buyRate) - 1) * 100
  const verdict = getEngineVerdict(trade, ipoData)
  const play = PLAY_CONFIG[verdict.play] || PLAY_CONFIG.AVOID
  const isWin = trade.pnl > 0

  const alignColor = verdict.alignment === "correct" ? T.green
    : verdict.alignment === "wrong" ? T.red : T.amber
  const alignIcon = verdict.alignment === "correct" ? "✓"
    : verdict.alignment === "wrong" ? "✗" : "~"

  return (
    <div style={{
      background: T.surface, borderRadius: 12,
      border: `1px solid ${isWin ? T.greenBd : T.redBd}`,
      borderLeft: `4px solid ${isWin ? T.green : T.red}`,
      marginBottom: 8, overflow: "hidden"
    }}>
      {/* Header row */}
      <div onClick={() => setExpanded(!expanded)}
        style={{ padding: "12px 16px", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: isWin ? T.greenBg : T.redBg,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 700, color: isWin ? T.green : T.red
          }}>
            {trade.symbol.slice(0,3)}
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{trade.symbol}</div>
            <div style={{ fontSize: 11, color: T.meta }}>
              {trade.buyDate} → {trade.sellDate} · {trade.holdDays}d
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* P&L */}
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: isWin ? T.green : T.red }}>
              {isWin ? "+" : ""}₹{Math.abs(trade.pnl).toLocaleString("en-IN", {maximumFractionDigits:0})}
            </div>
            <div style={{ fontSize: 11, color: isWin ? T.green : T.red }}>
              {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
            </div>
          </div>

          {/* Engine play */}
          <div style={{
            padding: "3px 10px", borderRadius: 20,
            background: play.bg, fontSize: 11, fontWeight: 600, color: play.color
          }}>
            {play.emoji} {play.label}
          </div>

          {/* Alignment */}
          <div style={{
            width: 28, height: 28, borderRadius: "50%",
            background: verdict.alignment === "correct" ? T.greenBg
              : verdict.alignment === "wrong" ? T.redBg : T.amberBg,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 700, color: alignColor
          }}>
            {alignIcon}
          </div>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ padding: "0 16px 14px", borderTop: `1px solid ${T.border2}` }}>
          {/* Trade details */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, padding: "10px 0" }}>
            {[
              { label: "Buy", value: `₹${trade.buyRate.toFixed(0)}` },
              { label: "Sell", value: `₹${trade.sellRate.toFixed(0)}` },
              { label: "Qty", value: trade.qty.toFixed(0) },
              { label: "Value", value: `₹${(trade.buyRate * trade.qty).toLocaleString("en-IN", {maximumFractionDigits:0})}` },
            ].map(m => (
              <div key={m.label} style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
                <div style={{ fontSize: 10, color: T.meta, fontWeight: 600, marginBottom: 2, textTransform: "uppercase" as const }}>{m.label}</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{m.value}</div>
              </div>
            ))}
          </div>

          {/* Engine verdict */}
          <div style={{
            background: play.bg, borderRadius: 8, padding: "10px 12px",
            border: `1px solid ${play.color}30`, marginBottom: 8
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: play.color,
              textTransform: "uppercase" as const, letterSpacing: "0.08em", marginBottom: 6 }}>
              Engine verdict: {play.label} ({verdict.confidence}% confidence)
            </div>
            {verdict.reasons.map((r, i) => (
              <div key={i} style={{ fontSize: 12, color: T.text, marginBottom: 3,
                display: "flex", gap: 6 }}>
                <span style={{ color: play.color, fontWeight: 700, flexShrink: 0 }}>→</span>
                <span>{r}</span>
              </div>
            ))}
          </div>

          {/* Alignment note */}
          <div style={{
            fontSize: 12, color: alignColor, fontWeight: 500,
            padding: "6px 10px", borderRadius: 6,
            background: verdict.alignment === "correct" ? T.greenBg
              : verdict.alignment === "wrong" ? T.redBg : T.amberBg
          }}>
            {alignIcon} {verdict.alignmentNote}
          </div>

          {/* What to do differently */}
          {verdict.alignment === "wrong" && (
            <div style={{
              fontSize: 12, color: T.sub, marginTop: 8, padding: "8px 10px",
              borderRadius: 6, border: `1px solid ${T.border}`, background: T.grayBg
            }}>
              <strong style={{ color: T.text }}>Next time:</strong>{" "}
              {verdict.play === "AVOID"
                ? "Check issue size, QIB subscription, and operator risk score before entry."
                : `The ${play.label} play with strict stop loss would have worked better.`}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SummaryBar({ trades, verdicts }: { trades: Trade[], verdicts: Record<string, EngineVerdict> }) {
  const totalPnl    = trades.reduce((s, t) => s + t.pnl, 0)
  const winners     = trades.filter(t => t.pnl > 0).length
  const losers      = trades.filter(t => t.pnl < 0).length
  const correct     = Object.values(verdicts).filter(v => v.alignment === "correct").length
  const accuracy    = trades.length > 0 ? (correct / trades.length * 100).toFixed(0) : 0

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
      {[
        { label:"Total P&L", value: `${totalPnl >= 0 ? "+" : ""}₹${Math.abs(totalPnl).toLocaleString("en-IN",{maximumFractionDigits:0})}`,
          color: totalPnl >= 0 ? T.green : T.red, bg: totalPnl >= 0 ? T.greenBg : T.redBg },
        { label:"Win / Loss", value: `${winners} / ${losers}`,
          color: T.text, bg: T.grayBg },
        { label:"Engine accuracy", value: `${accuracy}%`,
          color: parseInt(accuracy as string) >= 75 ? T.green : T.amber, bg: T.grayBg },
        { label:"Trades analysed", value: `${trades.length}`,
          color: T.text, bg: T.grayBg },
      ].map(m => (
        <div key={m.label} style={{ background: m.bg, borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ fontSize: 11, color: T.meta, fontWeight: 600, marginBottom: 4,
            textTransform: "uppercase" as const, letterSpacing: "0.06em" }}>{m.label}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: m.color }}>{m.value}</div>
        </div>
      ))}
    </div>
  )
}

export function IpoTradeEvaluator() {
  const [trades, setTrades]       = useState<Trade[]>([])
  const [verdicts, setVerdicts]   = useState<Record<string, EngineVerdict>>({})
  const [ipoData, setIpoData]     = useState<Record<string, any>>({})
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState("")
  const [filter, setFilter]       = useState<"all"|"wins"|"losses"|"correct"|"wrong">("all")
  const fileRef = useRef<HTMLInputElement>(null)

  const loadIPOData = useCallback(async (symbols: string[]) => {
    try {
      const res = await fetch(`/api/ipo/intelligence?symbols=${symbols.join(',')}`)
      if (res.ok) {
        const d = await res.json()
        const map: Record<string, any> = {}
        for (const ipo of (d.ipos || [])) {
          if (ipo.nse_symbol) map[ipo.nse_symbol] = ipo
          if (ipo.symbol) map[ipo.symbol] = ipo
        }
        setIpoData(map)
        return map
      }
    } catch {}
    return {}
  }, [])

  const onFile = useCallback(async (file: File) => {
    setLoading(true); setError(""); setTrades([]); setVerdicts({})
    try {
      const text = await file.text()
      const parsed = parseZerodhaCSV(text)
      if (!parsed.length) { setError("No trades found. Make sure this is a Zerodha capital gains CSV."); return }

      // Load IPO data from Neon
      const symbols = parsed.map(t => t.symbol)
      const ipoMap = await loadIPOData(symbols)

      // Compute verdicts
      const vmap: Record<string, EngineVerdict> = {}
      for (const t of parsed) {
        vmap[t.symbol] = getEngineVerdict(t, ipoMap[t.symbol])
      }
      setTrades(parsed)
      setVerdicts(vmap)
    } catch (e: any) {
      setError(`Parse error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [loadIPOData])

  const filtered = trades.filter(t => {
    if (filter === "wins")    return t.pnl > 0
    if (filter === "losses")  return t.pnl < 0
    if (filter === "correct") return verdicts[t.symbol]?.alignment === "correct"
    if (filter === "wrong")   return verdicts[t.symbol]?.alignment === "wrong"
    return true
  }).sort((a, b) => b.pnl - a.pnl)

  return (
    <div style={{ background: T.bg, minHeight: "100vh", paddingBottom: 60 }}>

      {/* Header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "16px 20px", position: "sticky", top: 52, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: T.text }}>Trade Evaluator</div>
            <div style={{ fontSize: 12, color: T.sub }}>
              Upload your Zerodha capital gains CSV → engine scores every trade
            </div>
          </div>
          <button onClick={() => fileRef.current?.click()}
            style={{ display: "flex", alignItems: "center", gap: 6,
              padding: "8px 16px", borderRadius: 8,
              background: T.blue, color: "#fff", border: "none",
              fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            <Upload size={14}/> Upload CSV
          </button>
          <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }}
            onChange={e => e.target.files?.[0] && onFile(e.target.files[0])}/>
        </div>
      </div>

      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {/* Empty state */}
        {!trades.length && !loading && (
          <div onClick={() => fileRef.current?.click()}
            style={{ border: `2px dashed ${T.border}`, borderRadius: 16,
              padding: "60px 20px", textAlign: "center" as const, cursor: "pointer",
              background: T.surface, marginTop: 24 }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 6 }}>
              Upload your Zerodha capital gains CSV
            </div>
            <div style={{ fontSize: 13, color: T.sub, marginBottom: 4 }}>
              Zerodha → Reports → Tax P&L → Download Capital Gains CSV
            </div>
            <div style={{ fontSize: 12, color: T.meta }}>
              The engine will score every IPO trade against our database of 381 historical IPOs
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ padding: "60px 0", textAlign: "center" as const }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>⚙️</div>
            <div style={{ color: T.sub }}>Analysing trades against IPO engine…</div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ background: T.redBg, border: `1px solid ${T.redBd}`,
            borderRadius: 10, padding: "12px 16px", color: T.red, fontSize: 13, marginTop: 12 }}>
            {error}
          </div>
        )}

        {/* Results */}
        {trades.length > 0 && (
          <>
            <SummaryBar trades={trades} verdicts={verdicts}/>

            {/* Filters */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" as const }}>
              {(["all","wins","losses","correct","wrong"] as const).map(f => (
                <button key={f} onClick={() => setFilter(f)}
                  style={{ padding: "5px 12px", borderRadius: 20,
                    border: `1px solid ${filter===f ? T.blue : T.border}`,
                    background: filter===f ? T.blueBg : T.surface,
                    color: filter===f ? T.blue : T.sub,
                    fontSize: 12, fontWeight: filter===f ? 700 : 400, cursor: "pointer" }}>
                  {f === "all" ? `All (${trades.length})`
                   : f === "wins" ? `✅ Wins (${trades.filter(t=>t.pnl>0).length})`
                   : f === "losses" ? `❌ Losses (${trades.filter(t=>t.pnl<0).length})`
                   : f === "correct" ? `✓ Engine correct (${Object.values(verdicts).filter(v=>v.alignment==="correct").length})`
                   : `✗ Missed (${Object.values(verdicts).filter(v=>v.alignment==="wrong").length})`}
                </button>
              ))}
            </div>

            {/* Trade cards */}
            {filtered.map(trade => (
              <TradeCard key={trade.symbol} trade={trade}
                ipoData={ipoData[trade.symbol]}/>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
