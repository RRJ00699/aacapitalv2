"use client"
import { useState, useEffect, useRef } from "react"

const C = {
  green:"#15803d", greenBg:"#f0fdf4",
  amber:"#b45309", amberBg:"#fefce8",
  red:"#b91c1c",   redBg:"#fef2f2",
  blue:"#1d4ed8",  blueBg:"#eff6ff",
  gray:"#6b7280",  grayBg:"#f9fafb",
}

function scoreColor(v: number) {
  return v >= 65 ? C.green : v >= 50 ? C.amber : C.red
}

// ── Metric box ────────────────────────────────────────────────────────────
function Metric({ label, value, sub, highlight }: { label:string; value:string|number; sub?:string; highlight?: "green"|"amber"|"red" }) {
  const bg = highlight ? (highlight==="green"?C.greenBg:highlight==="amber"?C.amberBg:C.redBg) : C.grayBg
  const fg = highlight ? (highlight==="green"?C.green:highlight==="amber"?C.amber:C.red) : "#374151"
  return (
    <div style={{ background:bg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
      <div style={{ fontSize:8, color:C.gray, textTransform:"uppercase", marginBottom:2, letterSpacing:"0.05em" }}>{label}</div>
      <div style={{ fontSize:14, fontWeight:900, color:fg }}>{value}</div>
      {sub && <div style={{ fontSize:8, color:C.gray, marginTop:1 }}>{sub}</div>}
    </div>
  )
}

// ── Signal pill ───────────────────────────────────────────────────────────
function Signal({ text, type }: { text:string; type:"green"|"red"|"amber" }) {
  const [bg,fg] = type==="green"?[C.greenBg,C.green]:type==="red"?[C.redBg,C.red]:[C.amberBg,C.amber]
  return <div style={{ padding:"4px 10px", borderRadius:7, background:bg, fontSize:10, color:fg, fontWeight:600, marginBottom:3 }}>{text}</div>
}

// ── Mini sparkline ────────────────────────────────────────────────────────
function Spark({ data, color }: { data:number[]; color:string }) {
  if (data.length < 2) return null
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const w = 120, h = 30
  const pts = data.map((v,i) => `${(i/(data.length-1))*w},${h-(((v-min)/range)*h)}`).join(" ")
  return (
    <svg width={w} height={h} style={{ overflow:"visible" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={(data.length-1)/(data.length-1)*w} cy={h-(((data[data.length-1]-min)/range)*h)} r="3" fill={color} />
    </svg>
  )
}

// ── Order Book Ladder (Phase 1 simplified) ────────────────────────────────
function OrderLadder({ ltp, bidPrice, askPrice, bidQty, askQty }: any) {
  const levels = [2,1,0,-1,-2]
  return (
    <div style={{ fontFamily:"monospace" }}>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", fontSize:9, color:C.gray, marginBottom:4, textTransform:"uppercase" }}>
        <div>Bid Qty</div><div style={{ textAlign:"center" }}>Price</div><div style={{ textAlign:"right" }}>Ask Qty</div>
      </div>
      {levels.map(l => {
        const price = Math.round((ltp + l * ltp * 0.001) * 100) / 100
        const isBid = l >= 0
        const isAsk = l <= 0
        const qty = isBid && isAsk ? null : isBid ? Math.round(bidQty * (1 - l * 0.15)) : Math.round(askQty * (1 + l * 0.15))
        const isLtp = l === 0
        return (
          <div key={l} style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", padding:"2px 0", background:isLtp?"rgba(59,130,246,0.06)":undefined, borderRadius:3 }}>
            <div style={{ fontSize:10, color:C.green, fontWeight: isLtp?"800":"400" }}>{!isAsk ? qty?.toLocaleString("en-IN") : ""}</div>
            <div style={{ fontSize:10, fontWeight:800, color:isLtp?C.blue:"#374151", textAlign:"center" }}>₹{price}</div>
            <div style={{ fontSize:10, color:C.red, fontWeight: isLtp?"800":"400", textAlign:"right" }}>{isAsk && !isBid ? qty?.toLocaleString("en-IN") : ""}</div>
          </div>
        )
      })}
      <div style={{ fontSize:8, color:C.gray, marginTop:4 }}>Phase 2: 20-depth live order book via Zerodha WebSocket</div>
    </div>
  )
}

// ── Main Live Tape Component ──────────────────────────────────────────────
export default function LiveTape({ ipo }: { ipo: any }) {
  const [state, setState] = useState<any>(null)
  const [polling, setPolling] = useState(false)
  const [simulated, setSimulated] = useState(true)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState("")
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const tickRef = useRef(0)

  const ip = ipo.priceBandHigh || ipo.priceBandLow || 192
  const gmpEntry = ipo.gmpPrice ? ip + ipo.gmpPrice : ip * 1.15
  const listingPrice = ipo.listingPrice || ipo.gmpPrice ? Math.round(ip + (ipo.gmpPrice || 0) * 0.65) : ip * 1.12

  // Check Zerodha connection
  useEffect(() => {
    fetch("/api/auth/zerodha/status").then(r => r.json()).then(d => setConnected(d.connected || false))
  }, [])

  const fetchTape = async () => {
    const sym = ipo.symbol || ipo.name?.split(" ")[0]?.toUpperCase().slice(0,10)
    try {
      const res = await fetch(
        `/api/ipo/tape?ipo=${encodeURIComponent(ipo.name)}&symbol=${sym}&issuePrice=${ip}&gmpEntry=${Math.round(gmpEntry)}&listingPrice=${Math.round(listingPrice)}`
      )
      const d = await res.json()
      if (d.ok) {
        setState(d.state)
        setSimulated(d.simulated)
        tickRef.current++
      } else setError(d.error || "Failed")
    } catch (e: any) { setError(e.message) }
  }

  const startPolling = () => {
    setPolling(true)
    fetchTape()
    intervalRef.current = setInterval(fetchTape, 5000) // Phase 2: 5s fast poll
  }
  const stopPolling = () => {
    setPolling(false)
    if (intervalRef.current) clearInterval(intervalRef.current)
  }
  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current) }, [])

  const s = state
  const actionBg = s?.actionColor==="green"?C.greenBg:s?.actionColor==="amber"?C.amberBg:C.redBg
  const actionFg = s?.actionColor==="green"?C.green:s?.actionColor==="amber"?C.amber:C.red
  const ltpColor = s && s.snapshots?.length > 1
    ? (s.snapshots[s.snapshots.length-1]?.ltp > s.snapshots[s.snapshots.length-2]?.ltp ? C.green : C.red)
    : "#374151"

  return (
    <div style={{ border:"1px solid #e5e7eb", borderRadius:14, overflow:"hidden", background:"#fff", marginBottom:12 }}>
      {/* Header */}
      <div style={{ background:"#0f172a", padding:"12px 16px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <div>
          <div style={{ fontSize:11, fontWeight:900, color:"#f8fafc", letterSpacing:"0.06em" }}>LISTING-DAY LIVE TAPE ENGINE</div>
          <div style={{ fontSize:9, color:"#475569", marginTop:1 }}>
            {simulated ? "🔵 Demo mode — " : "🟢 Live — "}
            {connected ? "Zerodha connected" : "Zerodha not connected"}
            {" · Phase 2: full WebSocket depth"}
          </div>
        </div>
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          {!connected && (
            <a href="/api/auth/zerodha" style={{ padding:"5px 10px", background:"#ff6600", borderRadius:7, fontSize:10, fontWeight:700, color:"#fff", textDecoration:"none" }}>
              Connect Zerodha
            </a>
          )}
          <button onClick={polling ? stopPolling : startPolling}
            style={{ padding:"5px 12px", background:polling?"#b91c1c":"#15803d", border:"none", borderRadius:7, fontSize:10, fontWeight:700, color:"#fff", cursor:"pointer" }}>
            {polling ? "⏹ Stop" : "▶ Start Live Tape"}
          </button>
        </div>
      </div>

      {!s && !polling && (
        <div style={{ padding:"24px 16px", textAlign:"center", color:C.gray }}>
          <div style={{ fontSize:20, marginBottom:8 }}>📡</div>
          <div style={{ fontSize:12, marginBottom:4 }}>Live Tape Engine ready</div>
          <div style={{ fontSize:10, color:"#9ca3af" }}>
            Click Start to begin {connected ? "live Zerodha feed" : "demo simulation"}.<br/>
            Polls every 30 seconds. Phase 2 upgrades to true WebSocket.
          </div>
        </div>
      )}

      {error && (
        <div style={{ padding:"10px 16px", background:C.redBg, fontSize:11, color:C.red }}>⚠ {error}</div>
      )}

      {s && (
        <div style={{ padding:"14px 16px" }}>
          {/* Alert banner */}
          {s.liveTapeScore < 35 && (
            <div style={{ background:C.redBg, border:`2px solid ${C.red}`, borderRadius:9, padding:"10px 14px", marginBottom:12 }}>
              <div style={{ fontSize:13, fontWeight:900, color:C.red }}>🚨 EXIT ALERT — Tape Score {s.liveTapeScore}/100</div>
              <div style={{ fontSize:11, color:"#7f1d1d", marginTop:2 }}>Live tape overrides pre-IPO score. HARD EXIT — no averaging.</div>
            </div>
          )}
          {s.openingRangeBreakout && (
            <div style={{ background:C.greenBg, border:`1px solid ${C.green}30`, borderRadius:9, padding:"8px 12px", marginBottom:10 }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.green }}>🚀 Opening Range Breakout — ADD ABOVE HIGH signal active</div>
            </div>
          )}
          {s.openingRangeBreakdown && (
            <div style={{ background:C.redBg, border:`1px solid ${C.red}30`, borderRadius:9, padding:"8px 12px", marginBottom:10 }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.red }}>📉 Opening Range Breakdown — EXIT signal active</div>
            </div>
          )}

          {/* Score + action */}
          <div style={{ display:"flex", gap:12, alignItems:"center", marginBottom:14 }}>
            <div style={{ textAlign:"center", background:actionBg, border:`2px solid ${actionFg}30`, borderRadius:14, padding:"10px 18px" }}>
              <div style={{ fontSize:36, fontWeight:900, color:actionFg, lineHeight:1 }}>{s.liveTapeScore}</div>
              <div style={{ fontSize:8, color:C.gray, marginTop:2 }}>LIVE TAPE SCORE</div>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:14, fontWeight:900, color:actionFg, marginBottom:4 }}>{s.action}</div>
              <div style={{ fontSize:10, color:C.gray, lineHeight:1.6 }}>
                Pre-IPO Score: {ipo.score?.listingScore||0}/100 → Live overrides prediction
              </div>
              {simulated && <div style={{ fontSize:9, color:"#9ca3af", marginTop:2 }}>Demo simulation · Connect Zerodha for real data</div>}
            </div>
            {/* LTP */}
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:9, color:C.gray }}>LTP</div>
              <div style={{ fontSize:26, fontWeight:900, color:ltpColor }}>
                ₹{s.snapshots?.[s.snapshots.length-1]?.ltp.toFixed(2) || "—"}
              </div>
              <Spark
                data={(s.snapshots||[]).map((x:any) => x.ltp)}
                color={ltpColor}
              />
            </div>
          </div>

          {/* Key metrics grid */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6, marginBottom:12 }}>
            {(() => {
              const snap = s.snapshots?.[s.snapshots.length-1]
              if (!snap) return null
              const pvwap = Number(snap.priceVsVwapPct).toFixed(2)
              const pvwapH = parseFloat(pvwap) >= 0.5 ? "green" : parseFloat(pvwap) >= -0.5 ? "amber" : "red"
              const imbH   = snap.bidAskImbalance >= 0.55 ? "green" : snap.bidAskImbalance >= 0.45 ? "amber" : "red"
              return <>
                <Metric label="VWAP"          value={`₹${Number(snap.vwap).toFixed(2)}`} />
                <Metric label="Price vs VWAP" value={`${pvwap}%`}                highlight={pvwapH} />
                <Metric label="Bid/Ask Imb"   value={`${(snap.bidAskImbalance*100).toFixed(1)}%`} highlight={imbH} />
                <Metric label="Spread %"      value={`${Number(snap.spreadPct).toFixed(3)}%`} />
                <Metric label="Bid Qty"       value={snap.bidQty?.toLocaleString("en-IN") || "—"} highlight="green" />
                <Metric label="Ask Qty"       value={snap.askQty?.toLocaleString("en-IN") || "—"} highlight="red" />
                <Metric label="Vol Velocity"  value={`${s.volumeVelocity}x`} highlight={s.volumeVelocity>=1.3?"green":s.volumeVelocity>=0.8?"amber":"red"} />
                <Metric label="Volume"        value={(snap.volume/1000).toFixed(0)+"K"} />
                <Metric label="5-Min High"    value={s.first5MinHigh ? `₹${s.first5MinHigh}` : "Building..."} />
                <Metric label="5-Min Low"     value={s.first5MinLow  ? `₹${s.first5MinLow}`  : "Building..."} />
                <Metric label="Cont. Prob"    value={`${s.continuationProb}%`}  highlight={s.continuationProb>=60?"green":s.continuationProb>=40?"amber":"red"} />
                <Metric label="PB Prob"       value={`${s.profitBookingProb}%`} highlight={s.profitBookingProb>=60?"red":s.profitBookingProb>=40?"amber":"green"} />
              </>
            })()}
          </div>

          {/* Signals */}
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12 }}>
            <div>
              <div style={{ fontSize:9, fontWeight:800, color:C.green, marginBottom:6, letterSpacing:"0.06em" }}>▲ CONTINUATION SIGNALS</div>
              {s.continuationSignals?.length > 0
                ? s.continuationSignals.map((sig:string,i:number) => <Signal key={i} text={sig} type="green" />)
                : <div style={{ fontSize:10, color:C.gray }}>No continuation signals yet</div>}
            </div>
            <div>
              <div style={{ fontSize:9, fontWeight:800, color:C.red, marginBottom:6, letterSpacing:"0.06em" }}>▼ PROFIT BOOKING SIGNALS</div>
              {s.profitBookingSignals?.length > 0
                ? s.profitBookingSignals.map((sig:string,i:number) => <Signal key={i} text={sig} type="red" />)
                : <div style={{ fontSize:10, color:C.gray }}>No profit booking signals</div>}
            </div>
          </div>

          {/* Order ladder */}
          {(() => {
            const snap = s.snapshots?.[s.snapshots.length-1]
            if (!snap) return null
            return (
              <div>
                <div style={{ fontSize:9, fontWeight:800, color:"#374151", marginBottom:8, letterSpacing:"0.06em" }}>
                  ORDER BOOK LADDER <span style={{ fontSize:8, color:C.gray, fontWeight:400 }}>Phase 1 · 5-level simulated · Phase 2: live 20-depth</span>
                </div>
                <OrderLadder ltp={snap.ltp} bidPrice={snap.bidPrice} askPrice={snap.askPrice} bidQty={snap.bidQty} askQty={snap.askQty} />
              </div>
            )
          })()}
        </div>
      )}

      {/* Phase 2 teaser */}
      <div style={{ background:"#0f172a", padding:"8px 16px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <div style={{ fontSize:9, color:"#475569" }}>
          Phase 2: True WebSocket · 20-depth order book · Bid VWAP · Ask VWAP · Tick-by-tick tape
        </div>
        <div style={{ fontSize:9, color:"#64748b", background:"rgba(255,255,255,0.05)", padding:"3px 8px", borderRadius:5 }}>
          Coming in paid tier
        </div>
      </div>
    </div>
  )
}



