"use client"
import { useState, useEffect } from "react"

const C = {
  green:  "#15803d", greenBg:  "#f0fdf4", greenBd: "#bbf7d0",
  blue:   "#1d4ed8", blueBg:   "#eff6ff", blueBd:  "#bfdbfe",
  amber:  "#b45309", amberBg:  "#fefce8", amberBd: "#fde68a",
  red:    "#b91c1c", redBg:    "#fef2f2", redBd:   "#fecaca",
  purple: "#7c3aed", purpleBg: "#f5f3ff", purpleBd:"#e9d5ff",
  cyan:   "#0891b2", cyanBg:   "#ecfeff", cyanBd:  "#cffafe",
  gray:   "#6b7280", grayBg:   "#f9fafb", grayBd:  "#e5e7eb",
}
export function Card({ children, style={} }: { children:any; style?:any }) {
  return <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:20, marginBottom:24, ...style }}>{children}</div>
}
export function SectionTitle({ text }: { text:string }) {
  return <div style={{ fontSize:11, fontWeight:500, color:"#94a3b8", letterSpacing:"0.05em", marginBottom:16, textTransform:"uppercase" as const }}>{text}</div>
}

// ═══════════════════════════════════════════════════════════════════

// ── Pure scoring functions (no React) ────────────────────────────────────────

export function calcConviction(s: any): number {
  if (!s) return 0
  const listing  = s.listingScore    || 0
  const business = s.businessScore   || 0
  const mgmt     = s.managementScore || 0
  const risk     = s.risk?.score     || 50
  const anchor   = s.anchorScore     || 0
  const mb       = s.multibaggerProb || 0
  return Math.round(
    listing  * 0.30 +
    business * 0.20 +
    mgmt     * 0.15 +
    (100 - risk) * 0.15 +
    anchor   * 0.10 +
    mb       * 0.10
  )
}

export function calcEV(ipo: any): { p: number; gain: number; loss: number; ev: number } {
  const s     = ipo.score || {}
  const ls    = s.listingScore || 0
  const ip    = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmp   = ipo.gmpPrice || 0
  const gmpPct = ip > 0 ? (gmp / ip * 100) : 0
  const regime = s.regime?.label || "COLD"

  // P(success) calibrated to 2024 data, adjusted for market regime
  const regimeMult = regime === "HOT" ? 1.0 : regime === "NORMAL" ? 0.85 : 0.70
  const baseP = ls >= 85 ? 0.87 : ls >= 70 ? 0.71 : ls >= 55 ? 0.55 : 0.38
  const p = +(baseP * regimeMult).toFixed(2)

  // Expected gain
  const gmpEff  = regime === "HOT" ? 0.70 : regime === "NORMAL" ? 0.60 : 0.50
  const gmpGain  = gmpPct * gmpEff
  const scoreGain = ls * 0.30
  const gain = gmp > 0 ? +(gmpGain * 0.6 + scoreGain * 0.4).toFixed(1) : +scoreGain.toFixed(1)

  // Expected loss = hard stop (non-negotiable rule)
  const loss = 10

  const ev = +(p * gain - (1 - p) * loss).toFixed(1)
  return { p, gain, loss, ev }
}

export function allocPct(conviction: number): number {
  if (conviction >= 90) return 25
  if (conviction >= 80) return 15
  if (conviction >= 70) return 8
  return 0
}

// ── Conviction + EV Panel (add to IpoDetail after HeroPanel) ─────────────────

export function ConvictionPanel({ ipo }: { ipo: any }) {
  const s          = ipo.score || {}
  const conviction = calcConviction(s)
  const ev         = calcEV(ipo)
  const alloc      = allocPct(conviction)
  const passes20   = conviction >= 80 && ev.ev > 0 && (s.listingScore || 0) >= 75

  const tier =
    conviction >= 90 ? { label: "Highest Conviction", c: C.green,  bg: C.greenBg  } :
    conviction >= 80 ? { label: "High Conviction",    c: C.blue,   bg: C.blueBg   } :
    conviction >= 70 ? { label: "Medium Conviction",  c: C.amber,  bg: C.amberBg  } :
                       { label: "Watchlist Only",     c: C.gray,   bg: C.grayBg   }

  const regime = s.regime?.label || "COLD"

  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14 }}>
        <SectionTitle text="Capital Compounding Engine" />
        <div style={{
          padding:"3px 10px", borderRadius:20, fontSize:11, fontWeight:700,
          background: passes20 ? C.greenBg : C.grayBg,
          color: passes20 ? C.green : C.gray,
          border: `1px solid ${passes20 ? C.greenBd : C.grayBd}`
        }}>
          {passes20 ? "✓ Top 20 Qualifier" : "Does not qualify — Top 20"}
        </div>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:14 }}>

        {/* Conviction block */}
        <div style={{ background:tier.bg, border:`1px solid ${tier.c}30`, borderRadius:12, padding:"14px 16px" }}>
          <div style={{ fontSize:11, color:C.gray, marginBottom:4 }}>Conviction Score</div>
          <div style={{ fontSize:38, fontWeight:700, color:tier.c, lineHeight:1, marginBottom:4 }}>{conviction}</div>
          <div style={{ fontSize:12, fontWeight:700, color:tier.c, marginBottom:12 }}>{tier.label}</div>
          {[
            { l:"Listing",    v: s.listingScore    || 0, w:30 },
            { l:"Business",   v: s.businessScore   || 0, w:20 },
            { l:"Management", v: s.managementScore || 0, w:15 },
            { l:"Safety",     v: 100-(s.risk?.score||50), w:15 },
            { l:"Anchor",     v: s.anchorScore     || 0, w:10 },
            { l:"Multibagger",v: s.multibaggerProb || 0, w:10 },
          ].map(row => (
            <div key={row.l} style={{ display:"flex", alignItems:"center", gap:6, marginBottom:4 }}>
              <span style={{ fontSize:10, color:C.gray, width:80 }}>{row.l} {row.w}%</span>
              <div style={{ flex:1, height:3, background:"#e5e7eb", borderRadius:2 }}>
                <div style={{ width:`${row.v}%`, height:"100%", background:tier.c, borderRadius:2, opacity:0.7 }} />
              </div>
              <span style={{ fontSize:10, fontWeight:700, color:tier.c, width:24, textAlign:"right" }}>{row.v}</span>
            </div>
          ))}
        </div>

        {/* EV block */}
        <div style={{
          background: ev.ev > 0 ? C.greenBg : C.redBg,
          border:`1px solid ${ev.ev > 0 ? C.greenBd : C.redBd}`,
          borderRadius:12, padding:"14px 16px"
        }}>
          <div style={{ fontSize:11, color:C.gray, marginBottom:4 }}>Expected Value (EV)</div>
          <div style={{ fontSize:38, fontWeight:700, color:ev.ev > 0 ? C.green : C.red, lineHeight:1, marginBottom:4 }}>
            {ev.ev > 0 ? "+" : ""}{ev.ev}%
          </div>
          <div style={{ fontSize:11, fontWeight:700, color:ev.ev > 0 ? C.green : C.red, marginBottom:12 }}>
            {ev.ev > 0 ? "✅ Positive EV — deploy capital" : "❌ Negative EV — skip"}
          </div>
          <div style={{ fontSize:10, color:C.gray, fontFamily:"monospace", marginBottom:10, padding:"6px 8px", background:"rgba(0,0,0,0.04)", borderRadius:6 }}>
            EV = P×gain − (1−P)×loss
          </div>
          {[
            { l:"P(success)",      v:`${(ev.p*100).toFixed(0)}%`,   c:C.blue  },
            { l:"Expected gain",   v:`+${ev.gain.toFixed(1)}%`,     c:C.green },
            { l:"Hard stop",       v:`−${ev.loss}%`,                c:C.red   },
            { l:"Regime",          v:regime,                        c:C.gray  },
          ].map(row => (
            <div key={row.l} style={{ display:"flex", justifyContent:"space-between", padding:"5px 0", borderBottom:`1px solid #f1f5f9` }}>
              <span style={{ fontSize:11, color:C.gray }}>{row.l}</span>
              <span style={{ fontSize:11, fontWeight:700, color:row.c }}>{row.v}</span>
            </div>
          ))}
          <div style={{ marginTop:12, padding:"8px 10px", background: alloc > 0 ? C.blueBg : C.grayBg, borderRadius:8 }}>
            <div style={{ fontSize:10, color:C.gray, marginBottom:2 }}>Recommended allocation</div>
            <div style={{ fontSize:15, fontWeight:700, color: alloc > 0 ? C.blue : C.gray }}>
              {alloc > 0 ? `${alloc}% of available capital` : "Skip — low conviction"}
            </div>
          </div>
        </div>
      </div>

      {/* Strategy instruction */}
      <div style={{ background:"#0f172a", borderRadius:10, padding:"10px 14px", fontSize:11, color:"#94a3b8", lineHeight:1.8 }}>
        <span style={{ color:"#4ade80", fontWeight:700 }}>Play: </span>
        {ev.ev > 5 && conviction >= 80
          ? `Apply ${alloc}% of capital. Buy at open via Live Tape. Sell D1–Week 1 at +20–30%. Hard stop −10% — no exceptions, no averaging.`
          : ev.ev > 0 && conviction >= 70
          ? `Low conviction. Retail only. Half position. Take profit at +15% quickly.`
          : `Negative EV or insufficient conviction. Skip. Preserve capital for better asymmetric opportunities.`}
      </div>
    </Card>
  )
}

// ── Capital Goal Engine ───────────────────────────────────────────────────────

export function CapitalGoalEngine() {
  const [startCap, setStartCap] = useState(100000)
  const [targetCap, setTargetCap] = useState(10000000)
  const [years, setYears]         = useState(10)

  const cagr = +(( Math.pow(targetCap / startCap, 1 / years) - 1 ) * 100).toFixed(1)
  const iposNeeded = Math.ceil(cagr / 25) // at avg 25% per IPO

  const fmt = (n: number) =>
    n >= 10000000 ? `₹${(n/10000000).toFixed(1)}Cr` :
    n >= 100000   ? `₹${(n/100000).toFixed(1)}L`    :
                    `₹${n.toLocaleString("en-IN")}`

  // Mini chart
  const W = 300, H = 64
  const pts = Array.from({ length: years + 1 }, (_, i) => {
    const v = startCap * Math.pow(1 + cagr/100, i)
    const x = (i / years) * W
    const y = H - ((v - startCap) / (targetCap - startCap || 1)) * (H - 6)
    return `${x.toFixed(1)},${Math.max(4, y).toFixed(1)}`
  }).join(" ")

  return (
    <Card>
      <SectionTitle text="Capital Goal Engine" />
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:10, marginBottom:14 }}>
        {[
          { l:"Starting capital",  val:startCap, set:setStartCap, min:10000,    max:10000000,  step:10000 },
          { l:"Target capital",    val:targetCap,set:setTargetCap,min:100000,   max:100000000, step:100000 },
          { l:"Years to target",   val:years,    set:setYears,    min:1,         max:30,        step:1 },
        ].map(f => (
          <div key={f.l}>
            <div style={{ fontSize:11, color:C.gray, marginBottom:4 }}>{f.l}</div>
            <div style={{ fontSize:15, fontWeight:700, color:"#0f172a", marginBottom:6 }}>
              {f.l === "Years to target" ? `${f.val} yrs` : fmt(f.val)}
            </div>
            <input type="range" min={f.min} max={f.max} step={f.step} value={f.val}
              onChange={e => f.set(+e.target.value)}
              style={{ width:"100%", accentColor:C.blue }} />
          </div>
        ))}
      </div>

      <div style={{ background:"#0f172a", borderRadius:12, padding:"14px 18px", marginBottom:12 }}>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:10, marginBottom:12 }}>
          <div>
            <div style={{ fontSize:10, color:"#475569", marginBottom:3 }}>Required CAGR</div>
            <div style={{ fontSize:28, fontWeight:700, lineHeight:1, color: cagr<=25?"#4ade80":cagr<=35?"#fbbf24":"#f87171" }}>{cagr}%</div>
            <div style={{ fontSize:10, color:"#64748b", marginTop:3 }}>{cagr<=25?"Achievable ✓":cagr<=35?"Aggressive":"Very ambitious"}</div>
          </div>
          <div>
            <div style={{ fontSize:10, color:"#475569", marginBottom:3 }}>Target</div>
            <div style={{ fontSize:22, fontWeight:700, color:"#c084fc", lineHeight:1 }}>{fmt(targetCap)}</div>
            <div style={{ fontSize:10, color:"#64748b", marginTop:3 }}>in {years} years</div>
          </div>
          <div>
            <div style={{ fontSize:10, color:"#475569", marginBottom:3 }}>IPOs/year needed</div>
            <div style={{ fontSize:22, fontWeight:700, color:"#60a5fa", lineHeight:1 }}>{iposNeeded}</div>
            <div style={{ fontSize:10, color:"#64748b", marginTop:3 }}>at avg 25% each</div>
          </div>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width:"100%", height:H, display:"block" }}>
          <polyline points={pts} fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={W} cy={4} r={3} fill="#4ade80" />
        </svg>
        <div style={{ display:"flex", justifyContent:"space-between", marginTop:4 }}>
          <span style={{ fontSize:10, color:"#475569" }}>Today: {fmt(startCap)}</span>
          <span style={{ fontSize:10, color:"#4ade80", fontWeight:700 }}>Year {years}: {fmt(targetCap)}</span>
        </div>
      </div>

      {/* Milestones */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:8 }}>
        {[2, 5, 10].map(mult => {
          const milestoneCap = startCap * mult
          const milestoneYrs = milestoneCap <= targetCap
            ? +(Math.log(mult) / Math.log(1 + cagr/100)).toFixed(1)
            : null
          return (
            <div key={mult} style={{ background:C.grayBg, border:`1px solid ${C.grayBd}`, borderRadius:9, padding:"9px 11px", textAlign:"center" }}>
              <div style={{ fontSize:16, fontWeight:700, color:C.blue }}>{mult}×</div>
              <div style={{ fontSize:12, fontWeight:700, color:C.green }}>{fmt(milestoneCap)}</div>
              <div style={{ fontSize:10, color:C.gray, marginTop:2 }}>
                {milestoneYrs ? `Year ${milestoneYrs}` : "Beyond goal"}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

// ── Mode Tracker: IPO Mode ↔ Recovery Mode ───────────────────────────────────

export function ModeTracker() {
  const [mode, setMode]         = useState<"IPO"|"RECOVERY">("IPO")
  const [lossAmt, setLossAmt]   = useState(8000)
  const [capital, setCapital]   = useState(100000)
  const [strikes, setStrikes]   = useState(0)

  const recoveryTarget  = lossAmt + capital * 0.05
  const recoveryNeeded  = +(recoveryTarget / capital * 100).toFixed(1)
  const fmt = (n: number) => `₹${n.toLocaleString("en-IN")}`

  return (
    <Card style={{ border:`2px solid ${mode==="IPO"?C.blue:C.amber}` }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14 }}>
        <SectionTitle text="Strategy Mode" />
        <div style={{ display:"flex", gap:6 }}>
          <button onClick={()=>setMode("IPO")}
            style={{ padding:"5px 12px", borderRadius:7, border:"none", cursor:"pointer", fontSize:11, fontWeight:700,
              background:mode==="IPO"?C.blue:"#e5e7eb", color:mode==="IPO"?"#fff":"#6b7280" }}>
            IPO Mode
          </button>
          <button onClick={()=>setMode("RECOVERY")}
            style={{ padding:"5px 12px", borderRadius:7, border:"none", cursor:"pointer", fontSize:11, fontWeight:700,
              background:mode==="RECOVERY"?C.amber:"#e5e7eb", color:mode==="RECOVERY"?"#fff":"#6b7280" }}>
            Recovery Mode
          </button>
        </div>
      </div>

      {mode==="IPO" && (
        <>
          <div style={{ background:C.blueBg, border:`1px solid ${C.blueBd}`, borderRadius:10, padding:"12px 14px", marginBottom:10 }}>
            <div style={{ fontSize:13, fontWeight:700, color:C.blue, marginBottom:8 }}>Active — Hunting Top 20 IPOs</div>
            {[
              "Apply only to Conviction ≥ 80 with Positive EV",
              "Buy at open using Live Tape Engine score",
              "Target exit: D1–Week 1 at +20–30%",
              "Hard stop: −10% if opens weak — no exceptions",
              "No averaging down. Ever.",
            ].map((rule, i) => (
              <div key={i} style={{ fontSize:11, color:"#374151", marginBottom:4 }}>✓ {rule}</div>
            ))}
          </div>

          {/* 3-Strike tracker */}
          <div style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 10px", background:C.grayBg, borderRadius:8, marginBottom:8 }}>
            <span style={{ fontSize:11, color:C.gray }}>Consecutive losses:</span>
            <div style={{ display:"flex", gap:4 }}>
              {[0,1,2].map(i => (
                <button key={i} onClick={()=>setStrikes(i+1===strikes?0:i+1)}
                  style={{ width:24, height:24, borderRadius:4, border:"1px solid #e5e7eb", cursor:"pointer", fontSize:14, lineHeight:"22px", textAlign:"center",
                    background: i < strikes ? "#fee2e2" : "#fff", color: i < strikes ? C.red : C.gray }}>
                  ×
                </button>
              ))}
            </div>
            {strikes >= 3 && (
              <span style={{ fontSize:11, fontWeight:700, color:C.red }}>3-strike rule: pause IPO mode until regime improves</span>
            )}
          </div>
          <div style={{ fontSize:11, color:C.gray, lineHeight:1.6, padding:"8px 10px", background:C.grayBg, borderRadius:8 }}>
            Loss on any trade → switch to Recovery Mode immediately. Return only when recovered + 5%.
          </div>
        </>
      )}

      {mode==="RECOVERY" && (
        <>
          <div style={{ background:C.amberBg, border:`1px solid ${C.amberBd}`, borderRadius:10, padding:"12px 14px", marginBottom:10 }}>
            <div style={{ fontSize:13, fontWeight:700, color:C.amber, marginBottom:10 }}>Recovery Mode — Guru Screener Active</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginBottom:10 }}>
              <div>
                <div style={{ fontSize:10, color:C.gray, marginBottom:4 }}>IPO loss amount</div>
                <input type="number" value={lossAmt} onChange={e=>setLossAmt(+e.target.value)}
                  style={{ width:"100%", border:`1px solid ${C.amberBd}`, borderRadius:6, padding:"6px 8px", fontSize:13, fontWeight:700 }} />
              </div>
              <div>
                <div style={{ fontSize:10, color:C.gray, marginBottom:4 }}>Current capital</div>
                <input type="number" value={capital} onChange={e=>setCapital(+e.target.value)}
                  style={{ width:"100%", border:`1px solid ${C.amberBd}`, borderRadius:6, padding:"6px 8px", fontSize:13, fontWeight:700 }} />
              </div>
            </div>
            <div style={{ background:"#fff", borderRadius:8, padding:"10px 12px", border:`1px solid ${C.amberBd}` }}>
              <div style={{ fontSize:10, color:C.gray, marginBottom:3 }}>Recovery target</div>
              <div style={{ fontSize:22, fontWeight:700, color:C.amber }}>{fmt(Math.round(recoveryTarget))} ({recoveryNeeded}%)</div>
              <div style={{ fontSize:10, color:C.gray, marginTop:3 }}>
                Loss {fmt(lossAmt)} + 5% buffer {fmt(Math.round(capital * 0.05))}
              </div>
            </div>
          </div>
          <div style={{ fontSize:11, color:"#374151", lineHeight:1.9, padding:"10px 12px", background:C.grayBg, borderRadius:8 }}>
            <strong style={{ color:C.amber }}>Recovery plan:</strong><br />
            1. Screener tab → run Buffett or Kutumbarao filter<br />
            2. Pick only Tier 1A stocks with Buy Zone ≥ 75<br />
            3. Allocate 5–8% per stock, max 3 stocks at once<br />
            4. Target: recover {fmt(Math.round(recoveryTarget))} then exit → IPO Mode<br />
            5. Do not apply to any IPOs while in Recovery Mode
          </div>
        </>
      )}
    </Card>
  )
}

// ── Compound Tab (full page) ──────────────────────────────────────────────────

export function CompoundTab() {
  const [ipos, setIpos]   = useState<any[]>([])
  const [loading, setLoad] = useState(true)

  useEffect(() => {
    fetch("/api/ipo").then(r=>r.json()).then(d=>{
      setIpos(d.ipos||[])
      setLoad(false)
    }).catch(()=>setLoad(false))
  }, [])

  const ranked = [...ipos]
    .map(ipo => ({ ...ipo, conviction: calcConviction(ipo.score||{}), ev: calcEV(ipo) }))
    .filter(ipo => ipo.ev.ev > 0)
    .sort((a, b) => b.ev.ev - a.ev.ev)

  return (
    <div style={{ maxWidth:960, margin:"0 auto", padding:"16px 20px" }}>

      {/* Philosophy banner */}
      <div style={{ background:"#0f172a", borderRadius:14, padding:"16px 20px", marginBottom:16 }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", flexWrap:"wrap", gap:12 }}>
          <div>
            <div style={{ fontSize:10, color:"#475569", letterSpacing:"0.08em", textTransform:"uppercase" as const, marginBottom:6 }}>Capital Compounding Engine</div>
            <div style={{ fontSize:18, fontWeight:700, color:"#f8fafc", marginBottom:6 }}>Not activity. Compounding.</div>
            <div style={{ fontSize:12, color:"#64748b", lineHeight:1.8, maxWidth:500 }}>
              20 high-conviction IPOs → buy at open → cut losses at −10% → recover with Guru stocks → repeat.<br />
              Time + patience + knowledge + engine = financial independence.
            </div>
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
            {[
              { l:"Positive EV IPOs", v:ranked.length,   c:"#4ade80" },
              { l:"Market regime",    v:"COLD ❄",         c:"#f87171" },
              { l:"Regime avg return",v:"+2%",            c:"#fbbf24" },
              { l:"Win rate 2026",    v:"42%",            c:"#fbbf24" },
            ].map(s=>(
              <div key={s.l} style={{ background:"rgba(255,255,255,0.05)", borderRadius:8, padding:"8px 12px", textAlign:"center" }}>
                <div style={{ fontSize:18, fontWeight:700, color:s.c, lineHeight:1 }}>{s.v}</div>
                <div style={{ fontSize:9, color:"#475569", marginTop:3 }}>{s.l}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Mode + Goal side by side */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12 }}>
        <ModeTracker />
        <CapitalGoalEngine />
      </div>

      {/* Opportunity Ranking */}
      <Card>
        <SectionTitle text="Opportunity Ranking — By Expected Value" />
        <div style={{ fontSize:11, color:C.gray, marginBottom:14 }}>
          Ranked by EV then Conviction. Only positive EV opportunities shown. GMP is not a ranking factor.
        </div>

        {loading && (
          <div style={{ textAlign:"center", padding:"30px 0", color:C.gray, fontSize:12 }}>
            <div style={{ width:14, height:14, border:"2px solid #e5e7eb", borderTopColor:C.blue, borderRadius:"50%", animation:"spin .7s linear infinite", margin:"0 auto 8px" }} />
            Loading pipeline...
          </div>
        )}

        {!loading && ranked.length === 0 && (
          <div style={{ textAlign:"center", padding:"32px 20px" }}>
            <div style={{ fontSize:28, marginBottom:8 }}>🔍</div>
            <div style={{ fontSize:13, color:"#374151", fontWeight:600, marginBottom:6 }}>No positive EV opportunities right now</div>
            <div style={{ fontSize:11, color:C.gray, lineHeight:1.7 }}>
              COLD market (2026: +2% avg, 42% positive rate).<br />
              Higher bar is correct. Preserve capital.<br />
              Use Recovery Mode with Guru stocks to compound while waiting.
            </div>
          </div>
        )}

        {ranked.map((ipo, i) => {
          const alloc = allocPct(ipo.conviction)
          const isTop = i === 0
          return (
            <div key={ipo.name} style={{
              display:"flex", alignItems:"center", gap:12, padding:"12px 14px",
              background: isTop ? C.greenBg : C.grayBg,
              border:`1px solid ${isTop ? C.greenBd : C.grayBd}`,
              borderRadius:10, marginBottom:8
            }}>
              <div style={{ fontSize:20, fontWeight:700, color: isTop ? C.green : C.gray, width:28 }}>#{i+1}</div>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:13, fontWeight:700, color:"#0f172a" }}>{ipo.name}</div>
                <div style={{ fontSize:10, color:C.gray }}>{ipo.sector} · {ipo.status}</div>
              </div>
              {[
                { l:"EV",         v:`+${ipo.ev.ev}%`,              c:C.green },
                { l:"Conviction", v:`${ipo.conviction}`,            c: ipo.conviction>=80?C.blue:C.amber },
                { l:"P(win)",     v:`${(ipo.ev.p*100).toFixed(0)}%`, c:"#374141" },
              ].map(s=>(
                <div key={s.l} style={{ textAlign:"center", minWidth:52 }}>
                  <div style={{ fontSize:10, color:C.gray }}>{s.l}</div>
                  <div style={{ fontSize:15, fontWeight:700, color:s.c }}>{s.v}</div>
                </div>
              ))}
              <div style={{ background: alloc>0?C.blueBg:C.grayBg, border:`1px solid ${alloc>0?C.blueBd:C.grayBd}`, borderRadius:8, padding:"6px 12px", textAlign:"center", minWidth:100 }}>
                <div style={{ fontSize:10, color:C.gray }}>Allocate</div>
                <div style={{ fontSize:13, fontWeight:700, color: alloc>0?C.blue:C.gray }}>
                  {alloc>0 ? `${alloc}% of capital` : "Skip"}
                </div>
              </div>
            </div>
          )
        })}

        {/* Compounding insight */}
        {ranked.length > 0 && (
          <div style={{ marginTop:12, padding:"10px 14px", background:"#0f172a", borderRadius:10, fontSize:11, color:"#94a3b8", lineHeight:1.8 }}>
            <span style={{ color:"#4ade80", fontWeight:700 }}>Engine insight: </span>
            In COLD 2026 market, apply only to the #1 ranked IPO with Conviction ≥ 80.
            Smaller position (15%). Take profits faster (+15% not +30%). Patience is edge.
          </div>
        )}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 3 — SUBSCRIPTION DAY TRACKER
// Paste this entire block into AACapitalApp.tsx BEFORE the 
// ═══════════════════════════════════════════════════════════════════
// SPRINT 4 — WEALTH BUILDER TAB
// New homepage. Shows: Capital Journey → Mode → Top Opportunity → Deploy
// Design: Premium warm white, Apple/Wealthfront aesthetic
// Requires: calcConviction(), calcEV(), allocPct() already in file (Sprint 3)
// ═══════════════════════════════════════════════════════════════════

export function WealthBuilderTab() {
  const [ipos,    setIpos]  = useState<any[]>([])
  const [loading, setLoad]  = useState(true)
  const [capital, setCap]   = useState(100000)
  const [target,  setTgt]   = useState(10000000)
  const [years,   setYrs]   = useState(10)
  const [mode,    setMode]  = useState<"IPO"|"RECOVERY">("IPO")
  const [lossAmt, setLoss]  = useState(8000)
  const [strikes, setStr]   = useState(0)

  useEffect(() => {
    fetch("/api/ipo").then(r=>r.json()).then(d=>{
      setIpos(d.ipos||[])
      setLoad(false)
    }).catch(()=>setLoad(false))
  }, [])

  const ranked = [...ipos]
    .map(ipo => ({ ...ipo, conviction: calcConviction(ipo.score||{}), ev: calcEV(ipo) }))
    .filter(ipo => ipo.ev.ev > 0)
    .sort((a,b) => b.ev.ev - a.ev.ev)

  const top = ranked[0]
  const cagr = +(( Math.pow(target / Math.max(capital,1), 1/years) - 1 ) * 100).toFixed(1)
  const progressPct = Math.min(100, +(capital/target * 100).toFixed(2))
  const recoveryTarget = Math.round(lossAmt + capital * 0.05)

  const topAllocs = ranked.slice(0,3).map(ipo => ({
    name: ipo.name, sector: ipo.sector,
    pct:    allocPct(ipo.conviction),
    amount: Math.round(capital * allocPct(ipo.conviction) / 100),
    conviction: ipo.conviction, ev: ipo.ev.ev
  })).filter(a => a.pct > 0)

  const deployedPct = topAllocs.reduce((s,a) => s+a.pct, 0)
  const reserve     = capital - topAllocs.reduce((s,a) => s+a.amount, 0)

  const fC = (n: number) =>
    n >= 10000000 ? `₹${(n/10000000).toFixed(1)}Cr` :
    n >= 100000   ? `₹${(n/100000).toFixed(1)}L`    :
    n >= 1000     ? `₹${(n/1000).toFixed(0)}K`      :
    `₹${n.toLocaleString("en-IN")}`

  const WCard = ({ children, style={} }: { children:any; style?:any }) => (
    <div style={{
      background:"#FFFFFF", border:"1px solid #F0EDE8",
      borderRadius:16, padding:"20px 24px", marginBottom:16,
      boxShadow:"0 2px 8px rgba(0,0,0,0.05)", ...style
    }}>{children}</div>
  )

  const Lbl = ({ t }: { t:string }) => (
    <div style={{ fontSize:10, color:"#9ca3af", marginBottom:6, fontWeight:600,
      textTransform:"uppercase" as const, letterSpacing:"0.06em" }}>{t}</div>
  )

  const milestones = [
    {l:"₹5L",  t:500000},  {l:"₹10L", t:1000000},
    {l:"₹25L", t:2500000}, {l:"₹50L", t:5000000}, {l:"₹1Cr",t:10000000}
  ]

  return (
    <div style={{ background:"#FAFAF8", minHeight:"100vh", paddingBottom:40 }}>
      <div style={{ maxWidth:920, margin:"0 auto", padding:"20px 16px" }}>

        {/* ── Header ─────────────────────────────────────────────── */}
        <div style={{ marginBottom:24 }}>
          <div style={{ fontSize:22, fontWeight:700, color:"#111827", marginBottom:3 }}>
            Your Wealth Dashboard
          </div>
          <div style={{ fontSize:13, color:"#6b7280" }}>
            Personal Investment Operating System · COLD market · Be selective
          </div>
        </div>

        {/* ── Road to ₹1 Crore ───────────────────────────────────── */}
        <WCard>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:20, flexWrap:"wrap", gap:12 }}>
            <div>
              <Lbl t="Your wealth journey" />
              <div style={{ fontSize:30, fontWeight:700, color:"#111827", lineHeight:1, marginBottom:4 }}>{fC(capital)}</div>
              <div style={{ fontSize:13, color:"#6b7280" }}>Target {fC(target)} in {years} years</div>
            </div>
            <div style={{ textAlign:"center", background:"#f9fafb", borderRadius:12, padding:"12px 20px" }}>
              <div style={{ fontSize:10, color:"#9ca3af", marginBottom:3 }}>Required CAGR</div>
              <div style={{ fontSize:34, fontWeight:700, lineHeight:1,
                color: cagr<=25?"#16a34a":cagr<=35?"#d97706":"#dc2626" }}>{cagr}%</div>
              <div style={{ fontSize:11, marginTop:3,
                color: cagr<=25?"#16a34a":cagr<=35?"#d97706":"#dc2626" }}>
                {cagr<=25?"Achievable":cagr<=35?"Aggressive":"Very ambitious"}
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ marginBottom:16 }}>
            <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, color:"#9ca3af", marginBottom:6 }}>
              <span>Progress to goal</span>
              <span style={{ color:"#16a34a", fontWeight:700 }}>{progressPct.toFixed(1)}% complete</span>
            </div>
            <div style={{ height:10, background:"#F0EDE8", borderRadius:5, overflow:"hidden" }}>
              <div style={{ height:"100%", width:`${progressPct}%`,
                background:"#16a34a", borderRadius:5 }} />
            </div>
          </div>

          {/* Sliders */}
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:16, marginBottom:16 }}>
            {[
              {l:"Starting capital", v:capital, set:setCap, min:10000, max:5000000, step:10000, fmt:true},
              {l:"Target capital",   v:target,  set:setTgt, min:500000, max:100000000, step:500000, fmt:true},
              {l:"Years to goal",    v:years,   set:setYrs, min:1, max:25, step:1, fmt:false},
            ].map(f => (
              <div key={f.l}>
                <div style={{ fontSize:11, color:"#9ca3af", marginBottom:3 }}>{f.l}</div>
                <div style={{ fontSize:14, fontWeight:700, color:"#111827", marginBottom:6 }}>
                  {f.fmt ? fC(f.v) : `${f.v} yrs`}
                </div>
                <input type="range" min={f.min} max={f.max} step={f.step} value={f.v}
                  onChange={e => f.set(+e.target.value)}
                  style={{ width:"100%", accentColor:"#16a34a" }} />
              </div>
            ))}
          </div>

          {/* Milestones */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8 }}>
            {milestones.map(m => {
              const done = capital >= m.t
              const yr = m.t > capital && cagr > 0
                ? +(Math.log(m.t/capital) / Math.log(1+cagr/100)).toFixed(1) : 0
              return (
                <div key={m.l} style={{
                  textAlign:"center", padding:"10px 6px", borderRadius:10,
                  background:done?"#f0fdf4":"#f9fafb",
                  border:`1px solid ${done?"#bbf7d0":"#F0EDE8"}`
                }}>
                  <div style={{ fontSize:12, fontWeight:700, color:done?"#16a34a":"#374151" }}>{m.l}</div>
                  <div style={{ fontSize:10, color:done?"#16a34a":"#9ca3af", marginTop:2 }}>
                    {done ? "✓ Done" : yr > 0 ? `Yr ${yr}` : "—"}
                  </div>
                </div>
              )
            })}
          </div>
        </WCard>

        {/* ── Mode + Top Opportunity ──────────────────────────────── */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16, marginBottom:0 }}>

          {/* Strategy Mode */}
          <WCard style={{ border:`2px solid ${mode==="IPO"?"#bbf7d0":"#fde68a"}` }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14 }}>
              <Lbl t="Strategy mode" />
              <div style={{ display:"flex", gap:3, background:"#f9fafb", borderRadius:20, padding:3 }}>
                {([["IPO","IPO Mode"],["RECOVERY","Recovery"]] as const).map(([v,l]) => (
                  <button key={v} onClick={() => setMode(v)}
                    style={{ padding:"4px 10px", borderRadius:16, border:"none", cursor:"pointer",
                      fontSize:11, fontWeight:700,
                      background: mode===v ? (v==="IPO"?"#16a34a":"#d97706") : "transparent",
                      color: mode===v ? "#fff" : "#6b7280" }}>
                    {l}
                  </button>
                ))}
              </div>
            </div>

            {mode==="IPO" ? (
              <div>
                <div style={{ fontSize:15, fontWeight:700, color:"#16a34a", marginBottom:10 }}>IPO Mode Active</div>
                {[
                  "Conviction ≥ 80, Positive EV only",
                  "Buy at open — Live Tape Engine",
                  "Exit D1–Week 1 at +20–30%",
                  "Hard stop −10% · No exceptions",
                  "No averaging down. Ever.",
                ].map((r,i) => (
                  <div key={i} style={{ fontSize:12, color:"#374151", marginBottom:5, display:"flex", gap:6 }}>
                    <span style={{ color:"#16a34a", fontWeight:700, flexShrink:0 }}>✓</span>{r}
                  </div>
                ))}
                {/* 3-strike tracker */}
                <div style={{ marginTop:12, padding:"8px 12px", background:"#f9fafb", borderRadius:8 }}>
                  <div style={{ fontSize:10, color:"#9ca3af", marginBottom:6 }}>Consecutive losses (3-strike rule)</div>
                  <div style={{ display:"flex", gap:6, alignItems:"center" }}>
                    {[0,1,2].map(i => (
                      <button key={i} onClick={() => setStr(i+1===strikes?0:i+1)}
                        style={{ width:28, height:28, borderRadius:6, border:"1px solid #e5e7eb",
                          cursor:"pointer", fontSize:13, background:i<strikes?"#fee2e2":"#fff",
                          color:i<strikes?"#dc2626":"#9ca3af" }}>×</button>
                    ))}
                    {strikes>=3 && (
                      <span style={{ fontSize:11, color:"#dc2626", fontWeight:700, marginLeft:4 }}>
                        Pause IPO Mode — market not cooperating
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize:15, fontWeight:700, color:"#d97706", marginBottom:10 }}>Recovery Mode Active</div>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginBottom:10 }}>
                  <div>
                    <div style={{ fontSize:10, color:"#9ca3af", marginBottom:4 }}>IPO loss amount (₹)</div>
                    <input type="number" value={lossAmt} onChange={e => setLoss(+e.target.value)}
                      style={{ width:"100%", border:"1px solid #F0EDE8", borderRadius:8,
                        padding:"6px 10px", fontSize:14, fontWeight:700, color:"#111827" }} />
                  </div>
                  <div style={{ background:"#fffbeb", borderRadius:8, padding:"8px 10px", border:"1px solid #fde68a" }}>
                    <div style={{ fontSize:10, color:"#9ca3af" }}>Recovery target</div>
                    <div style={{ fontSize:18, fontWeight:700, color:"#d97706" }}>{fC(recoveryTarget)}</div>
                    <div style={{ fontSize:10, color:"#d97706" }}>loss + 5% buffer</div>
                  </div>
                </div>
                {["Guru filter → Tier 1A stocks, Buy Zone ≥ 75",
                  "5–8% per position · max 3 stocks at once",
                  "Exit when target reached → back to IPO Mode",
                  "Do not apply to any IPOs while recovering"
                ].map((r,i) => (
                  <div key={i} style={{ fontSize:11, color:"#6b7280", marginBottom:5, display:"flex", gap:6 }}>
                    <span style={{ color:"#d97706", flexShrink:0 }}>→</span>{r}
                  </div>
                ))}
              </div>
            )}
          </WCard>

          {/* Top Opportunity */}
          <WCard style={{ border:`2px solid ${top && top.ev.ev>5?"#bbf7d0":"#F0EDE8"}` }}>
            <Lbl t="Top opportunity right now" />
            {loading ? (
              <div style={{ padding:"24px 0", textAlign:"center", color:"#9ca3af", fontSize:13 }}>Loading pipeline...</div>
            ) : !top ? (
              <div style={{ textAlign:"center", padding:"24px 0" }}>
                <div style={{ fontSize:32, marginBottom:10 }}>🔍</div>
                <div style={{ fontSize:14, fontWeight:700, color:"#374151", marginBottom:6 }}>No positive EV right now</div>
                <div style={{ fontSize:12, color:"#9ca3af", lineHeight:1.7 }}>
                  COLD 2026 market.<br/>Preserve capital. Use Recovery Mode + Guru stocks.
                </div>
              </div>
            ) : (
              <>
                <div style={{ fontSize:20, fontWeight:700, color:"#111827", marginBottom:2 }}>{top.name}</div>
                <div style={{ fontSize:12, color:"#6b7280", marginBottom:16 }}>{top.sector} · {top.status}</div>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8, marginBottom:14 }}>
                  {[
                    {l:"Expected Value", v:`${top.ev.ev>0?"+":""}${top.ev.ev}%`, c:"#16a34a", bg:"#f0fdf4"},
                    {l:"Conviction",     v:`${top.conviction}/100`, c:top.conviction>=80?"#1d4ed8":"#d97706", bg:top.conviction>=80?"#eff6ff":"#fffbeb"},
                    {l:"Allocate",       v:`${allocPct(top.conviction)}%`, c:"#111827", bg:"#f9fafb"},
                  ].map(s => (
                    <div key={s.l} style={{ background:s.bg, borderRadius:10, padding:"10px 6px", textAlign:"center" }}>
                      <div style={{ fontSize:10, color:"#9ca3af", marginBottom:3 }}>{s.l}</div>
                      <div style={{ fontSize:17, fontWeight:700, color:s.c }}>{s.v}</div>
                    </div>
                  ))}
                </div>
                <div style={{ padding:"8px 12px", background:top.ev.ev>5?"#f0fdf4":"#f9fafb", borderRadius:8,
                  fontSize:11, color:top.ev.ev>5?"#16a34a":"#6b7280", fontWeight:600, lineHeight:1.6 }}>
                  {top.ev.ev>5 && top.conviction>=80
                    ? `Apply ${allocPct(top.conviction)}% at open. Exit D1–Week 1. Hard stop −10%.`
                    : top.ev.ev>0
                    ? `Low conviction. Retail only. Take profit at +15%. Watch carefully.`
                    : "Thin signal. Small position or skip."}
                </div>
              </>
            )}
          </WCard>
        </div>

        {/* ── Capital Deployment Plan ─────────────────────────────── */}
        <WCard>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16, flexWrap:"wrap", gap:8 }}>
            <div>
              <Lbl t="Capital deployment plan" />
              <div style={{ fontSize:16, fontWeight:700, color:"#111827" }}>How to deploy {fC(capital)} today</div>
            </div>
            <div style={{ fontSize:11, color:"#9ca3af" }}>Conviction + EV ranked · Reserve ≥ 25%</div>
          </div>

          {topAllocs.length===0 ? (
            <div style={{ textAlign:"center", padding:"20px", color:"#9ca3af", fontSize:13, background:"#f9fafb", borderRadius:10 }}>
              No qualifying positions. Hold 100% cash. Wait for higher conviction opportunities.
            </div>
          ) : (
            <>
              {topAllocs.map((a,i) => (
                <div key={a.name} style={{ display:"flex", alignItems:"center", gap:12, padding:"12px 0",
                  borderBottom:"1px solid #f9fafb" }}>
                  <div style={{ width:24, height:24, borderRadius:6, flexShrink:0,
                    background:i===0?"#f0fdf4":"#f9fafb", display:"flex", alignItems:"center", justifyContent:"center",
                    fontSize:11, fontWeight:700, color:i===0?"#16a34a":"#9ca3af" }}>{i+1}</div>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:13, fontWeight:700, color:"#111827" }}>{a.name}</div>
                    <div style={{ fontSize:11, color:"#9ca3af" }}>EV +{a.ev}% · Conviction {a.conviction} · {a.sector}</div>
                  </div>
                  <div style={{ minWidth:110, textAlign:"right" }}>
                    <div style={{ height:4, background:"#F0EDE8", borderRadius:2, overflow:"hidden", marginBottom:3 }}>
                      <div style={{ height:"100%", width:`${(a.pct/25)*100}%`, background:"#16a34a", borderRadius:2 }} />
                    </div>
                    <div style={{ fontSize:12, fontWeight:700, color:"#374151" }}>{a.pct}% · {fC(a.amount)}</div>
                  </div>
                </div>
              ))}
              <div style={{ display:"flex", alignItems:"center", gap:12, padding:"12px 0" }}>
                <div style={{ width:24, flexShrink:0 }} />
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:13, fontWeight:700, color:"#6b7280" }}>Cash Reserve</div>
                  <div style={{ fontSize:11, color:"#9ca3af" }}>Never deploy below 25% cash buffer</div>
                </div>
                <div style={{ fontSize:13, fontWeight:700, color:"#6b7280" }}>
                  {100-deployedPct}% · {fC(reserve)}
                </div>
              </div>
            </>
          )}

          <div style={{ marginTop:12, padding:"10px 14px", background:"#0f172a", borderRadius:10,
            fontSize:11, color:"#94a3b8", lineHeight:1.8 }}>
            <span style={{ color:"#4ade80", fontWeight:700 }}>Engine: </span>
            Capital preservation before growth. Only deploy to Conviction ≥ 70, Positive EV.
            The best trade is sometimes no trade.
          </div>
        </WCard>

        {/* ── Market Regime Stats ─────────────────────────────────── */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:12 }}>
          {[
            {l:"Market Regime",     v:"COLD 2026",   sub:"42% win rate",          c:"#dc2626", bg:"#fef2f2", bd:"#fecaca"},
            {l:"Avg IPO Return",    v:"+2%",          sub:"2026 year to date",     c:"#d97706", bg:"#fffbeb", bd:"#fde68a"},
            {l:"Positive EV IPOs", v:`${ranked.length}`, sub:"in pipeline now",  c:"#16a34a", bg:"#f0fdf4", bd:"#bbf7d0"},
            {l:"Hard Stop Rule",   v:"−10%",          sub:"no exceptions, ever",  c:"#374151", bg:"#f9fafb", bd:"#e5e7eb"},
          ].map(s => (
            <div key={s.l} style={{ background:s.bg, border:`1px solid ${s.bd}`,
              borderRadius:12, padding:"14px 12px", textAlign:"center" }}>
              <div style={{ fontSize:10, color:"#9ca3af", marginBottom:4 }}>{s.l}</div>
              <div style={{ fontSize:20, fontWeight:700, color:s.c, marginBottom:2 }}>{s.v}</div>
              <div style={{ fontSize:10, color:"#9ca3af" }}>{s.sub}</div>
            </div>
          ))}
        </div>

      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 3 — SUBSCRIPTION DAY TRACKER
// Paste this entire block into AACapitalApp.tsx BEFORE the // ═══════════════════════════════════════════════════════════════════
// SPRINT 5 COMPONENTS
// MarketRegimePanel   — Markets tab persistence + regime engine
// StocksUploadPanel   — Screener.in CSV upload + quality display
// PostListingScanner  — GMP disappointment contrarian signals
// CapitalProtectionBadge — inline badge for stock cards
// ═══════════════════════════════════════════════════════════════════

// ── Stocks Upload Panel ───────────────────────────────────────────

export function StocksUploadPanel() {
  const [stocks,    setStocks]    = useState<any[]>([])
  const [uploading, setUploading] = useState(false)
  const [result,    setResult]    = useState<any>(null)
  const [filter,    setFilter]    = useState("Tier1A")
  const [loading,   setLoading]   = useState(true)

  useEffect(() => {
    loadStocks(filter)
  }, [filter])

  const loadStocks = async (tier: string) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/stocks/upload?tier=${tier}&minQ=0&minCP=0`)
      const d   = await res.json()
      setStocks(d.stocks || [])
    } finally { setLoading(false) }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setResult(null)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await fetch("/api/stocks/upload", { method: "POST", body: fd })
      const d   = await res.json()
      setResult(d)
      if (d.ok) loadStocks(filter)
    } finally { setUploading(false) }
  }

  const tierColor = (tier: string) => {
    if (tier === "Tier1A") return { c:"#16a34a", bg:"#f0fdf4" }
    if (tier === "Tier1B") return { c:"#1d4ed8", bg:"#eff6ff" }
    if (tier === "Good")   return { c:"#d97706", bg:"#fffbeb" }
    if (tier === "Watch")  return { c:"#9ca3af", bg:"#f9fafb" }
    return { c:"#dc2626", bg:"#fef2f2" }
  }

  return (
    <Card>
      <SectionTitle text="Stock Quality Engine" />
      <div style={{ fontSize:12, color:"#6b7280", marginBottom:16, lineHeight:1.7 }}>
        Export stocks from Screener.in → Upload CSV → Engine scores Quality + Capital Protection automatically.
        No paid data needed.
      </div>

      {/* Upload */}
      <div style={{ padding:"16px", background:"#f9fafb", border:"1.5px dashed #e5e7eb",
        borderRadius:12, marginBottom:16, textAlign:"center" }}>
        <div style={{ fontSize:13, fontWeight:600, color:"#374151", marginBottom:8 }}>
          Upload Screener.in CSV Export
        </div>
        <div style={{ fontSize:11, color:"#9ca3af", marginBottom:12 }}>
          Go to Screener.in → create a screen → Export → Upload here
        </div>
        <label style={{ padding:"8px 20px", background:"#111827", color:"#fff",
          border:"none", borderRadius:8, fontSize:12, fontWeight:700, cursor:"pointer",
          display:"inline-block" }}>
          {uploading ? "Processing..." : "Choose CSV File"}
          <input type="file" accept=".csv" onChange={handleUpload}
            style={{ display:"none" }} disabled={uploading} />
        </label>
        {result && (
          <div style={{ marginTop:10, fontSize:12,
            color: result.ok ? "#16a34a" : "#dc2626" }}>
            {result.ok
              ? `✓ ${result.inserted} stocks imported and scored`
              : `Error: ${result.error}`}
          </div>
        )}
      </div>

      {/* Filter tabs */}
      <div style={{ display:"flex", gap:6, marginBottom:14 }}>
        {["Tier1A","Tier1B","Good","Watch","Avoid"].map(t => {
          const tc = tierColor(t)
          return (
            <button key={t} onClick={() => setFilter(t)}
              style={{ padding:"5px 12px", borderRadius:20, border:"1px solid",
                borderColor: filter===t ? tc.c : "#e5e7eb",
                background: filter===t ? tc.bg : "transparent",
                color: filter===t ? tc.c : "#6b7280",
                fontSize:11, fontWeight:700, cursor:"pointer" }}>
              {t}
            </button>
          )
        })}
      </div>

      {/* Stock list */}
      {loading ? (
        <div style={{ padding:"20px", textAlign:"center", color:"#9ca3af", fontSize:13 }}>Loading...</div>
      ) : stocks.length === 0 ? (
        <div style={{ padding:"20px", textAlign:"center", color:"#9ca3af", fontSize:13 }}>
          No stocks in this tier yet. Upload a Screener.in CSV to get started.
        </div>
      ) : (
        <>
          <div style={{ display:"grid", gridTemplateColumns:"2fr 80px 80px 80px 80px 90px",
            gap:0, fontSize:10, color:"#9ca3af", padding:"6px 10px",
            background:"#f9fafb", borderRadius:"8px 8px 0 0", fontWeight:600 }}>
            <div>Stock</div><div style={{textAlign:"center"}}>Quality</div>
            <div style={{textAlign:"center"}}>Protection</div><div style={{textAlign:"center"}}>ROCE</div>
            <div style={{textAlign:"center"}}>D/E</div><div style={{textAlign:"center"}}>Tier</div>
          </div>
          {stocks.slice(0,30).map((s,i) => {
            const tc = tierColor(s.tier)
            return (
              <div key={s.symbol} style={{
                display:"grid", gridTemplateColumns:"2fr 80px 80px 80px 80px 90px",
                gap:0, fontSize:12, padding:"10px 10px",
                background: i%2===0?"#FFFFFF":"#fafaf8",
                borderBottom:"1px solid #f9fafb", alignItems:"center"
              }}>
                <div>
                  <div style={{ fontWeight:700, color:"#111827" }}>{s.symbol}</div>
                  <div style={{ fontSize:10, color:"#9ca3af" }}>{s.sector || "—"}</div>
                </div>
                <div style={{ textAlign:"center", fontWeight:700,
                  color: s.quality_score>=75?"#16a34a":s.quality_score>=60?"#1d4ed8":"#d97706" }}>
                  {s.quality_score}
                </div>
                <div style={{ textAlign:"center", fontWeight:700,
                  color: s.capital_protection_score>=70?"#16a34a":s.capital_protection_score>=55?"#d97706":"#dc2626" }}>
                  {s.capital_protection_score}
                </div>
                <div style={{ textAlign:"center", color:"#374151" }}>{s.roce ? `${s.roce}%` : "—"}</div>
                <div style={{ textAlign:"center", color: +s.debt_equity>1.5?"#dc2626":"#374151" }}>
                  {s.debt_equity || "—"}
                </div>
                <div style={{ textAlign:"center" }}>
                  <span style={{ padding:"3px 8px", borderRadius:20, fontSize:10, fontWeight:700,
                    background:tc.bg, color:tc.c }}>{s.tier}</span>
                </div>
              </div>
            )
          })}
        </>
      )}
    </Card>
  )
}

// ── Post-Listing Base Scanner ─────────────────────────────────────
// Uses GMP Disappointment signal on recent listed IPOs
// No live prices needed — uses entry data + known listing results

export function PostListingScanner({ ipos }: { ipos: any[] }) {
  // Filter: recently listed IPOs where listing < GMP expectations
  const candidates = ipos.filter(ipo => {
    const status = (ipo.status || "").toLowerCase()
    const hasListed = status.includes("listed") || ipo.actualD1Return !== undefined
    const gmp = ipo.gmpPrice || 0
    const ip  = ipo.priceBandHigh || ipo.priceBandLow || 0
    const gmpPct = ip > 0 ? (gmp / ip * 100) : 0
    const d1  = ipo.actualD1Return ?? (status.includes("listed") ? 0 : null)
    const gap = gmpPct - (d1 ?? 999)
    const quality = ipo.score?.businessScore || 0
    return hasListed && gap >= 5 && quality >= 65
  }).map(ipo => {
    const ip     = ipo.priceBandHigh || ipo.priceBandLow || 0
    const gmpPct = ip > 0 ? (ipo.gmpPrice / ip * 100) : 0
    const d1     = ipo.actualD1Return ?? 0
    const gap    = +(gmpPct - d1).toFixed(1)
    const quality = ipo.score?.businessScore || 0
    const regime  = ipo.score?.regime?.label || "COLD"
    const regMult = regime === "HOT" ? 1.0 : regime === "NORMAL" ? 0.85 : 0.70
    const winRate = quality >= 80 ? Math.round(87 * regMult) :
                    quality >= 70 ? Math.round(73 * regMult) :
                    Math.round(54 * regMult)
    const avgM6   = quality >= 80 ? +(28 * regMult).toFixed(0) :
                    quality >= 70 ? +(21 * regMult).toFixed(0) : +(8 * regMult).toFixed(0)
    const signal  = winRate >= 65 ? "BUY AFTER BASE" : "WATCH"
    return { ...ipo, gmpPct, d1, gap, quality, winRate, avgM6, signal }
  }).sort((a,b) => b.winRate - a.winRate)

  if (candidates.length === 0) return (
    <Card>
      <SectionTitle text="Post-Listing Base Scanner" />
      <div style={{ textAlign:"center", padding:"24px 0", color:"#9ca3af", fontSize:13 }}>
        No GMP disappointment candidates in current pipeline.<br/>
        <span style={{ fontSize:11 }}>Scanner activates after IPOs list below GMP expectations with Quality ≥ 65.</span>
      </div>
    </Card>
  )

  return (
    <Card>
      <SectionTitle text="Post-Listing Base Scanner" />
      <div style={{ fontSize:11, color:"#6b7280", marginBottom:14, lineHeight:1.7 }}>
        IPOs that listed below GMP expectations. Quality ≥ 65.
        Backtest: 73% win rate (6M ≥ +10%) when quality ≥ 70. Entry on base breakout with volume.
      </div>

      {candidates.map(ipo => {
        const sc = ipo.signal === "BUY AFTER BASE"
          ? { bg:"#f0fdf4", c:"#16a34a", bd:"#bbf7d0" }
          : { bg:"#fffbeb", c:"#d97706", bd:"#fde68a" }
        return (
          <div key={ipo.name} style={{ background:sc.bg, border:`1px solid ${sc.bd}`,
            borderRadius:12, padding:"14px 16px", marginBottom:10 }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", flexWrap:"wrap", gap:8 }}>
              <div>
                <div style={{ fontSize:16, fontWeight:700, color:"#111827", marginBottom:2 }}>{ipo.name}</div>
                <div style={{ fontSize:11, color:"#9ca3af" }}>{ipo.sector}</div>
              </div>
              <div style={{ padding:"4px 12px", borderRadius:20, fontSize:11, fontWeight:700,
                background:sc.c, color:"#fff" }}>{ipo.signal}</div>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8, marginTop:12 }}>
              {[
                { l:"GMP was",      v:`+${ipo.gmpPct.toFixed(0)}%`, c:"#374151" },
                { l:"Listed at",    v:`${ipo.d1>=0?"+":""}${ipo.d1}%`, c:ipo.d1>=0?"#16a34a":"#dc2626" },
                { l:"Gap",          v:`${ipo.gap}%`, c:"#d97706" },
                { l:"Win rate 6M",  v:`${ipo.winRate}%`, c:sc.c },
                { l:"Avg 6M return",v:`+${ipo.avgM6}%`, c:sc.c },
              ].map(s => (
                <div key={s.l} style={{ textAlign:"center", background:"rgba(255,255,255,0.7)",
                  borderRadius:8, padding:"8px 6px" }}>
                  <div style={{ fontSize:10, color:"#9ca3af", marginBottom:2 }}>{s.l}</div>
                  <div style={{ fontSize:15, fontWeight:700, color:s.c }}>{s.v}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop:10, fontSize:11, color:"#6b7280", lineHeight:1.7 }}>
              Entry: breakout above post-listing consolidation on volume ≥ 1.5× 10-day avg.
              Stop: −8% from base low. Quality {ipo.quality}/100.
            </div>
          </div>
        )
      })}

      <div style={{ marginTop:4, padding:"8px 12px", background:"#f9fafb", borderRadius:8,
        fontSize:11, color:"#9ca3af" }}>
        Live price integration paused — will activate with Zerodha connection.
        Currently shows pattern signal from listing data + historical backtest.
      </div>
    </Card>
  )
}

// ── Capital Protection Badge (inline, use anywhere) ───────────────

export function CapProtBadge({ score }: { score: number }) {
  const label = score >= 80 ? "Clean" : score >= 65 ? "OK" : score >= 50 ? "Caution" : "High Risk"
  const c = score >= 80 ? "#16a34a" : score >= 65 ? "#1d4ed8" : score >= 50 ? "#d97706" : "#dc2626"
  const bg = score >= 80 ? "#f0fdf4" : score >= 65 ? "#eff6ff" : score >= 50 ? "#fffbeb" : "#fef2f2"
  return (
    <span style={{ padding:"2px 8px", borderRadius:20, fontSize:10, fontWeight:700,
      background:bg, color:c, border:`1px solid ${c}30` }}>
      CP {score} · {label}
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 3 — SUBSCRIPTION DAY TRACKER
// Paste this entire block into AACapitalApp.tsx BEFORE the // ═══════════════════════════════════════════════════════════════════
// SPRINT M1/M2 — MARKET ENGINE + BACKTESTING LAB
// MarketEnginePanel   — live Zerodha data + regime + IPO mode gate
// BacktestingLab      — strategy backtests + weight calibration
// ═══════════════════════════════════════════════════════════════════

// ── Market Engine Panel ───────────────────────────────────────────

export function MarketEnginePanel() {
  const [snap,     setSnap]     = useState<any>(null)
  const [loading,  setLoading]  = useState(false)
  const [fetching, setFetching] = useState(false)
  const [pcr,      setPcr]      = useState("")
  const [fiiFlow,  setFii]      = useState("")
  const [diiFlow,  setDii]      = useState("")
  const [adRatio,  setAD]       = useState("")
  const [notes,    setNotes]    = useState("")

  useEffect(() => {
    setLoading(true)
    fetch("/api/market/live")
      .then(r => r.json())
      .then(d => { if (d.snapshot) setSnap(d.snapshot) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const fetchLive = async () => {
    setFetching(true)
    try {
      const res = await fetch("/api/market/live", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pcr:          +pcr     || undefined,
          fiiFlow:      +fiiFlow || undefined,
          diiFlow:      +diiFlow || undefined,
          advanceDecline: +adRatio || undefined,
          notes
        })
      })
      const d = await res.json()
      if (d.ok) {
        // Reload from DB
        const r2 = await fetch("/api/market/live").then(r => r.json())
        if (r2.snapshot) setSnap(r2.snapshot)
      }
    } finally { setFetching(false) }
  }

  const regimeConfig: Record<string, { bg:string; c:string; bd:string; emoji:string; note:string }> = {
    HOT:               { bg:"#f0fdf4", c:"#16a34a", bd:"#bbf7d0", emoji:"🔥", note:"Deploy full allocation. IPO Mode active." },
    NORMAL:            { bg:"#eff6ff", c:"#1d4ed8", bd:"#bfdbfe", emoji:"✅", note:"Standard allocation. IPO Mode active. Conviction ≥ 82." },
    CAUTION:           { bg:"#fffbeb", c:"#d97706", bd:"#fde68a", emoji:"⚠️", note:"Reduce allocation 50%. IPO Mode: Conviction ≥ 85 only." },
    COLD:              { bg:"#fff1f2", c:"#e11d48", bd:"#fecdd3", emoji:"❄️", note:"Defensive. 25% allocation. IPO Mode: Conviction ≥ 90 only." },
    FROZEN:            { bg:"#fef2f2", c:"#dc2626", bd:"#fecaca", emoji:"🚫", note:"Pause all new positions. Capital protection mode." },
    PANIC_OPPORTUNITY: { bg:"#f5f3ff", c:"#7c3aed", bd:"#ddd6fe", emoji:"💡", note:"Contrarian zone. Only Tier 1A quality stocks in tranches." },
  }

  const regime = snap?.market_regime || "UNKNOWN"
  const rc = regimeConfig[regime] || { bg:"#f9fafb", c:"#6b7280", bd:"#e5e7eb", emoji:"—", note:"Fetch live data to see regime" }

  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16, flexWrap:"wrap", gap:10 }}>
        <SectionTitle text="Market Engine" />
        <button onClick={fetchLive} disabled={fetching}
          style={{ padding:"8px 18px", background:fetching?"#9ca3af":"#111827", color:"#fff",
            border:"none", borderRadius:10, fontSize:12, fontWeight:700, cursor:"pointer" }}>
          {fetching ? "Fetching from Zerodha..." : "Fetch Live Market Data"}
        </button>
      </div>

      {loading && !snap && (
        <div style={{ padding:"20px 0", textAlign:"center", color:"#9ca3af", fontSize:13 }}>Loading last snapshot...</div>
      )}

      {snap && (
        <>
          {/* Regime banner */}
          <div style={{ background:rc.bg, border:`1px solid ${rc.bd}`, borderRadius:12,
            padding:"14px 18px", marginBottom:16 }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", flexWrap:"wrap", gap:10 }}>
              <div>
                <div style={{ fontSize:11, color:"#9ca3af", marginBottom:4 }}>Market Regime · {snap.source === "zerodha" ? "Live from Zerodha" : "Manual entry"}</div>
                <div style={{ fontSize:22, fontWeight:700, color:rc.c, marginBottom:4 }}>
                  {rc.emoji} {regime.replace("_", " ")}
                </div>
                <div style={{ fontSize:12, color:"#6b7280" }}>{rc.note}</div>
                <div style={{ fontSize:10, color:"#9ca3af", marginTop:6 }}>
                  Last updated: {snap.created_at ? new Date(snap.created_at).toLocaleString("en-IN") : "—"}
                </div>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, minWidth:200 }}>
                <div style={{ textAlign:"center", background:"rgba(255,255,255,0.7)", borderRadius:8, padding:"8px 12px" }}>
                  <div style={{ fontSize:10, color:"#9ca3af", marginBottom:2 }}>Risk Score</div>
                  <div style={{ fontSize:22, fontWeight:700,
                    color: snap.market_risk_score > 70 ? "#dc2626" : snap.market_risk_score > 50 ? "#d97706" : "#16a34a" }}>
                    {snap.market_risk_score}/100
                  </div>
                </div>
                <div style={{ textAlign:"center", background:"rgba(255,255,255,0.7)", borderRadius:8, padding:"8px 12px" }}>
                  <div style={{ fontSize:10, color:"#9ca3af", marginBottom:2 }}>Opportunity</div>
                  <div style={{ fontSize:22, fontWeight:700, color:rc.c }}>{snap.market_opportunity_score}/100</div>
                </div>
              </div>
            </div>

            {/* IPO Mode gate */}
            <div style={{ marginTop:12, padding:"8px 12px",
              background: snap.ipo_mode_allowed ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${snap.ipo_mode_allowed ? "#bbf7d0" : "#fecaca"}`,
              borderRadius:8, fontSize:12,
              color: snap.ipo_mode_allowed ? "#16a34a" : "#dc2626", fontWeight:600 }}>
              IPO Mode: {snap.ipo_mode_allowed ? `Active — Conviction ≥ ${snap.ipo_conviction_threshold} required` : "Paused — Market conditions unfavourable"}
            </div>
          </div>

          {/* Live indices grid */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(130px,1fr))", gap:8, marginBottom:16 }}>
            {[
              { l:"Nifty 50",    v:snap.nifty_price    ? `₹${(+snap.nifty_price).toLocaleString("en-IN")}` : "—", c:+(snap.nifty_change_pct||0) },
              { l:"Bank Nifty",  v:snap.banknifty_price ? `₹${(+snap.banknifty_price).toLocaleString("en-IN")}` : "—", c:+(snap.banknifty_change_pct||0) },
              { l:"India VIX",   v:snap.india_vix ? `${snap.india_vix}` : "—", c: -(+snap.india_vix-15) },
              { l:"PCR",         v:snap.pcr ? `${snap.pcr}` : "—", c: snap.pcr < 0.8 ? 1 : snap.pcr > 1.3 ? -1 : 0 },
              { l:"vs 20 DMA",   v:snap.nifty_vs_20dma != null ? `${+snap.nifty_vs_20dma > 0 ? "+" : ""}${snap.nifty_vs_20dma}%` : "—", c:+(snap.nifty_vs_20dma||0) },
              { l:"vs 50 DMA",   v:snap.nifty_vs_50dma != null ? `${+snap.nifty_vs_50dma > 0 ? "+" : ""}${snap.nifty_vs_50dma}%` : "—", c:+(snap.nifty_vs_50dma||0) },
              { l:"vs 200 DMA",  v:snap.nifty_vs_200dma != null ? `${+snap.nifty_vs_200dma > 0 ? "+" : ""}${snap.nifty_vs_200dma}%` : "—", c:+(snap.nifty_vs_200dma||0) },
              { l:"Exposure",    v:`${snap.recommended_exposure}%`, c: +(snap.recommended_exposure||75) - 50 },
            ].map(s => (
              <div key={s.l} style={{ background:"#f9fafb", border:"1px solid #F0EDE8", borderRadius:10, padding:"10px 10px", textAlign:"center" }}>
                <div style={{ fontSize:10, color:"#9ca3af", marginBottom:3 }}>{s.l}</div>
                <div style={{ fontSize:15, fontWeight:700, color: s.c > 0 ? "#16a34a" : s.c < 0 ? "#dc2626" : "#374151" }}>{s.v}</div>
              </div>
            ))}
          </div>

          {/* Sector heat */}
          {snap.sector_data_json && (() => {
            try {
              const sectors = JSON.parse(snap.sector_data_json)
              const entries = Object.entries(sectors) as [string, number][]
              if (entries.length === 0) return null
              return (
                <div style={{ marginBottom:16 }}>
                  <div style={{ fontSize:11, color:"#9ca3af", marginBottom:8, fontWeight:600 }}>SECTOR HEAT MAP</div>
                  <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
                    {entries.map(([sector, chg]) => (
                      <div key={sector} style={{
                        padding:"4px 10px", borderRadius:20, fontSize:11, fontWeight:700,
                        background: chg > 1 ? "#f0fdf4" : chg < -1 ? "#fef2f2" : "#f9fafb",
                        color: chg > 1 ? "#16a34a" : chg < -1 ? "#dc2626" : "#6b7280",
                        border: `1px solid ${chg > 1 ? "#bbf7d0" : chg < -1 ? "#fecaca" : "#e5e7eb"}`
                      }}>
                        {sector} {chg > 0 ? "+" : ""}{chg.toFixed(1)}%
                      </div>
                    ))}
                  </div>
                </div>
              )
            } catch { return null }
          })()}
        </>
      )}

      {/* Manual input for PCR/FII (Zerodha doesn't provide these) */}
      <div style={{ borderTop:"1px solid #F0EDE8", paddingTop:14 }}>
        <div style={{ fontSize:11, color:"#9ca3af", marginBottom:10, fontWeight:600 }}>
          MANUAL INPUTS — PCR and FII/DII not available from Zerodha. Enter from NSE/Moneycontrol.
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:10, marginBottom:10 }}>
          {[
            { l:"PCR (from NSE)", v:pcr, set:setPcr, ph:"e.g. 0.95" },
            { l:"FII Flow (₹Cr)", v:fiiFlow, set:setFii, ph:"e.g. -500" },
            { l:"DII Flow (₹Cr)", v:diiFlow, set:setDii, ph:"e.g. 800" },
            { l:"A/D Ratio",      v:adRatio, set:setAD,  ph:"e.g. 1.4" },
          ].map(f => (
            <div key={f.l}>
              <div style={{ fontSize:10, color:"#9ca3af", marginBottom:3 }}>{f.l}</div>
              <input value={f.v} onChange={e => f.set(e.target.value)} placeholder={f.ph}
                style={{ width:"100%", border:"1px solid #F0EDE8", borderRadius:8,
                  padding:"6px 10px", fontSize:13, color:"#111827", background:"#FFFFFF" }} />
            </div>
          ))}
        </div>
        <button onClick={fetchLive} disabled={fetching}
          style={{ padding:"8px 16px", background:"#16a34a", color:"#fff",
            border:"none", borderRadius:8, fontSize:12, fontWeight:700, cursor:"pointer" }}>
          {fetching ? "Saving..." : "Save Snapshot"}
        </button>
      </div>
    </Card>
  )
}

// ── Backtesting Lab ───────────────────────────────────────────────

export function BacktestingLab() {
  const [running,  setRunning]  = useState(false)
  const [results,  setResults]  = useState<any>(null)
  const [startYear, setStart]   = useState(2020)
  const [endYear,   setEnd]     = useState(2024)
  const [minConv,   setConv]    = useState(80)
  const [minQual,   setQual]    = useState(70)
  const [maxRisk,   setRisk]    = useState(50)
  const [runs,      setRuns]    = useState<any[]>([])
  const [activeRun, setActive]  = useState<string|null>(null)

  useEffect(() => {
    fetch("/api/backtest").then(r=>r.json()).then(d => setRuns(d.runs||[]))
  }, [])

  const runBacktest = async () => {
    setRunning(true)
    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          startYear, endYear,
          filters: { minConviction: minConv, minQuality: minQual, maxRisk },
          runName: `Backtest ${startYear}–${endYear} Conv≥${minConv}`
        })
      })
      const d = await res.json()
      if (d.ok) setResults(d)
    } finally { setRunning(false) }
  }

  const stratColors = ["#16a34a","#1d4ed8","#7c3aed","#d97706"]

  return (
    <Card>
      <SectionTitle text="Backtesting Lab" />
      <div style={{ fontSize:12, color:"#6b7280", marginBottom:16 }}>
        Test AACapital engine accuracy against {IPO_HISTORICAL_COUNT} historical IPOs (2017–2025). Zerodha historical data enriches post-listing returns.
      </div>

      {/* Filters */}
      <div style={{ background:"#f9fafb", border:"1px solid #F0EDE8", borderRadius:12, padding:"14px 16px", marginBottom:16 }}>
        <div style={{ fontSize:11, color:"#9ca3af", marginBottom:12, fontWeight:600 }}>BACKTEST PARAMETERS</div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:12 }}>
          {[
            { l:"Start Year",       v:startYear, set:setStart, min:2017, max:2024, step:1 },
            { l:"End Year",         v:endYear,   set:setEnd,   min:2018, max:2025, step:1 },
            { l:"Min Conviction",   v:minConv,   set:setConv,  min:60,   max:95,   step:5 },
            { l:"Min Quality",      v:minQual,   set:setQual,  min:50,   max:90,   step:5 },
            { l:"Max Risk",         v:maxRisk,   set:setRisk,  min:20,   max:70,   step:5 },
          ].map(f => (
            <div key={f.l}>
              <div style={{ fontSize:10, color:"#9ca3af", marginBottom:4 }}>{f.l}</div>
              <div style={{ fontSize:16, fontWeight:700, color:"#111827", marginBottom:4 }}>{f.v}</div>
              <input type="range" min={f.min} max={f.max} step={f.step} value={f.v}
                onChange={e => f.set(+e.target.value)}
                style={{ width:"100%", accentColor:"#111827" }} />
            </div>
          ))}
        </div>
        <button onClick={runBacktest} disabled={running}
          style={{ marginTop:14, padding:"10px 24px", background:running?"#9ca3af":"#111827",
            color:"#fff", border:"none", borderRadius:10, fontSize:13, fontWeight:700, cursor:"pointer" }}>
          {running ? "Running backtest..." : "Run Backtest"}
        </button>
      </div>

      {/* Results */}
      {results && (
        <>
          <div style={{ fontSize:13, fontWeight:600, color:"#374151", marginBottom:12 }}>
            Results: {results.dateRange} · {results.sampleSize} IPOs
          </div>

          {/* Strategy cards */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:12, marginBottom:16 }}>
            {results.strategies.map((s: any, i: number) => (
              <div key={s.strategy} style={{ background:"#f9fafb", border:"1px solid #F0EDE8", borderRadius:12, padding:"14px 16px" }}>
                <div style={{ fontSize:12, fontWeight:700, color:stratColors[i]||"#374151", marginBottom:10 }}>{s.strategy}</div>
                {s.sampleSize === 0 ? (
                  <div style={{ fontSize:12, color:"#9ca3af" }}>No qualifying trades with current filters</div>
                ) : (
                  <>
                    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8, marginBottom:10 }}>
                      {[
                        { l:"Win Rate",    v:`${s.winRate}%`,       c: s.winRate>=70?"#16a34a":s.winRate>=55?"#d97706":"#dc2626" },
                        { l:"Avg Return",  v:`${s.avgReturn>0?"+":""}${s.avgReturn}%`, c: s.avgReturn>0?"#16a34a":"#dc2626" },
                        { l:"Sample",      v:`${s.sampleSize}`,     c:"#374151" },
                      ].map(m => (
                        <div key={m.l} style={{ textAlign:"center" }}>
                          <div style={{ fontSize:10, color:"#9ca3af", marginBottom:2 }}>{m.l}</div>
                          <div style={{ fontSize:16, fontWeight:700, color:m.c }}>{m.v}</div>
                        </div>
                      ))}
                    </div>
                    {s.regimeBreakdown && s.regimeBreakdown.length > 0 && (
                      <div>
                        <div style={{ fontSize:10, color:"#9ca3af", marginBottom:6 }}>Win rate by market regime:</div>
                        {s.regimeBreakdown.map((r: any) => (
                          <div key={r.regime} style={{ display:"flex", justifyContent:"space-between",
                            fontSize:11, color:"#6b7280", padding:"2px 0" }}>
                            <span>{r.regime}</span>
                            <span style={{ fontWeight:700, color: r.winRate>=70?"#16a34a":r.winRate>=50?"#d97706":"#dc2626" }}>
                              {r.winRate}% win · {r.avgReturn>0?"+":""}{r.avgReturn}% avg
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>

          {/* Weight calibration */}
          {results.weightCalibration && (
            <div style={{ background:"#0f172a", borderRadius:12, padding:"14px 18px", marginBottom:12 }}>
              <div style={{ fontSize:12, fontWeight:700, color:"#f8fafc", marginBottom:12 }}>
                Weight Calibration Recommendations
              </div>
              <div style={{ fontSize:11, color:"#475569", marginBottom:10 }}>
                Based on correlation analysis. DO NOT auto-apply — review and decide.
              </div>
              {results.weightCalibration.filter((c: any) => c.correlation != null).map((c: any) => {
                const changed = c.suggestedWeight !== c.currentWeight
                return (
                  <div key={c.name} style={{ display:"flex", alignItems:"center", gap:12,
                    padding:"8px 0", borderBottom:"1px solid rgba(255,255,255,0.06)" }}>
                    <div style={{ flex:1, fontSize:12, color:"#94a3b8" }}>{c.name}</div>
                    <div style={{ fontSize:12, color:"#64748b" }}>Current: {c.currentWeight}%</div>
                    <div style={{ fontSize:12, fontWeight:700,
                      color: changed ? (c.suggestedWeight > c.currentWeight ? "#4ade80" : "#f87171") : "#64748b" }}>
                      {changed ? `→ ${c.suggestedWeight}%` : "No change"}
                    </div>
                    <div style={{ fontSize:10, color:"#475569", maxWidth:200 }}>{c.reason}</div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Summary */}
          <div style={{ padding:"10px 14px", background: results.strategies[0]?.winRate >= 70 ? "#f0fdf4" : "#fffbeb",
            borderRadius:10, fontSize:12, fontWeight:600,
            color: results.strategies[0]?.winRate >= 70 ? "#16a34a" : "#d97706" }}>
            {results.summary?.recommendation}
          </div>
        </>
      )}
    </Card>
  )
}

// placeholder for component count reference
export const IPO_HISTORICAL_COUNT = 27

// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 3 — SUBSCRIPTION DAY TRACKER
// Paste this entire block into AACapitalApp.tsx BEFORE the // MAIN PAGE comment
// Then add <SubscriptionTracker ipo={ipo} /> inside IpoDetail, after <RegimeWidget>
// ─────────────────────────────────────────────────────────────────────────────

export function SubscriptionTracker({ ipo }: { ipo: any }) {
  const [days, setDays] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ day: "1", qib_x: "", nii_x: "", retail_x: "", notes: "" })
  const [msg, setMsg] = useState("")

  useEffect(() => {
    if (!ipo.name) return
    fetch(`/api/ipo/subscription?name=${encodeURIComponent(ipo.name)}`)
      .then(r => r.json())
      .then(d => { setDays(d.days || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [ipo.name])

  const save = async () => {
    if (!form.qib_x && !form.nii_x && !form.retail_x) {
      setMsg("Enter at least one subscription figure"); return
    }
    setSaving(true); setMsg("")
    try {
      const res = await fetch("/api/ipo/subscription", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: ipo.name,
          day: parseInt(form.day),
          qib_x: form.qib_x ? parseFloat(form.qib_x) : null,
          nii_x: form.nii_x ? parseFloat(form.nii_x) : null,
          retail_x: form.retail_x ? parseFloat(form.retail_x) : null,
          notes: form.notes || null,
        })
      })
      const d = await res.json()
      if (d.ok) {
        setDays(d.days)
        setShowForm(false)
        setForm({ day: String(Math.min(3, parseInt(form.day) + 1)), qib_x: "", nii_x: "", retail_x: "", notes: "" })
        setMsg("✅ Saved")
        setTimeout(() => setMsg(""), 3000)
      } else {
        setMsg(`❌ ${d.error}`)
      }
    } catch (e: any) { setMsg(`❌ ${e.message}`) }
    setSaving(false)
  }

  // Signals derived from day data
  const d1 = days.find(d => d.day === 1)
  const d2 = days.find(d => d.day === 2)
  const d3 = days.find(d => d.day === 3)
  const latest = d3 || d2 || d1

  const qibAcceleration = d1 && d2 && d1.qib_x > 0
    ? +((d2.qib_x - d1.qib_x) / d1.qib_x * 100).toFixed(1)
    : null
  const niiJump = d1 && d2 && d1.nii_x > 0
    ? +((d2.nii_x - d1.nii_x) / d1.nii_x * 100).toFixed(1)
    : null
  const isQibAccelerating = qibAcceleration !== null && qibAcceleration > 50
  const isNiiJumping = niiJump !== null && niiJump > 100

  // SVG momentum chart
  const chartDays = ["Day 1", "Day 2", "Day 3"]
  const W = 340, H = 90, padL = 32, padR = 10, padT = 8, padB = 16
  const cW = W - padL - padR, cH = H - padT - padB

  const allVals = days.flatMap(d => [d.qib_x, d.nii_x, d.retail_x].filter(Boolean))
  const maxV = Math.max(...allVals, 1)

  const xPos = (dayIdx: number) => padL + (dayIdx / 2) * cW
  const yPos = (val: number) => padT + cH - (val / maxV) * cH

  const lineFor = (key: "qib_x" | "nii_x" | "retail_x") => {
    const pts = [1, 2, 3]
      .map(d => ({ day: d, val: days.find(x => x.day === d)?.[key] }))
      .filter(p => p.val != null)
    if (pts.length < 2) return null
    return pts.map((p, i) => `${i === 0 ? "M" : "L"}${xPos(p.day - 1)},${yPos(p.val)}`).join(" ")
  }

  const dotFor = (key: "qib_x" | "nii_x" | "retail_x") =>
    [1, 2, 3]
      .map(d => ({ day: d, val: days.find(x => x.day === d)?.[key] }))
      .filter(p => p.val != null)
      .map(p => ({ x: xPos(p.day - 1), y: yPos(p.val), val: p.val }))

  const seriesColors = { qib_x: "#1d4ed8", nii_x: "#d97706", retail_x: "#16a34a" }
  const seriesLabels = { qib_x: "QIB", nii_x: "NII/HNI", retail_x: "Retail" }

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <SectionTitle text="Subscription Momentum Tracker" />
        <button onClick={() => setShowForm(v => !v)}
          style={{ padding: "6px 14px", background: showForm ? "transparent" : "#0f172a", border: `1px solid ${showForm ? "#e5e7eb" : "#0f172a"}`, borderRadius: 8, color: showForm ? C.gray : "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
          {showForm ? "Cancel" : `+ Enter Day ${days.length + 1} Data`}
        </button>
      </div>

      {loading && <div style={{ fontSize: 12, color: C.gray }}>Loading…</div>}

      {/* Entry form */}
      {showForm && (
        <div style={{ background: C.grayBg, border: `1px solid ${C.grayBd}`, borderRadius: 10, padding: "12px 14px", marginBottom: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "80px 1fr 1fr 1fr", gap: 8, marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>Day</div>
              <select value={form.day} onChange={e => setForm(p => ({ ...p, day: e.target.value }))}
                style={{ width: "100%", border: "1px solid #e5e7eb", borderRadius: 6, padding: "6px 8px", fontSize: 12 }}>
                <option value="1">Day 1</option>
                <option value="2">Day 2</option>
                <option value="3">Day 3</option>
              </select>
            </div>
            {(["qib_x", "nii_x", "retail_x"] as const).map(key => (
              <div key={key}>
                <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>{seriesLabels[key]} (x)</div>
                <input
                  type="number" step="0.01" min="0"
                  value={form[key]} onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                  placeholder="e.g. 45"
                  style={{ width: "100%", border: "1px solid #e5e7eb", borderRadius: 6, padding: "6px 8px", fontSize: 12 }}
                />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
              placeholder="Optional note — e.g. 'QIB momentum strong, HNI lag'"
              style={{ flex: 1, border: "1px solid #e5e7eb", borderRadius: 6, padding: "6px 10px", fontSize: 12 }}
            />
            <button onClick={save} disabled={saving}
              style={{ padding: "6px 16px", background: C.blue, border: "none", borderRadius: 7, color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer", opacity: saving ? 0.7 : 1 }}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
          {msg && <div style={{ marginTop: 8, fontSize: 11, color: msg.startsWith("✅") ? C.green : C.red }}>{msg}</div>}
        </div>
      )}

      {/* Day summary tiles */}
      {days.length > 0 && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 12 }}>
            {[1, 2, 3].map(d => {
              const row = days.find(x => x.day === d)
              return (
                <div key={d} style={{ background: row ? C.grayBg : "#fff", border: `1px solid ${row ? "#e5e7eb" : "#f1f5f9"}`, borderRadius: 9, padding: "10px 12px", opacity: row ? 1 : 0.4 }}>
                  <div style={{ fontSize: 11, color: C.gray, marginBottom: 6, fontWeight: 600 }}>Day {d}{!row ? " — no data" : ""}</div>
                  {row && (
                    <>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 11, color: C.gray }}>QIB</span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#1d4ed8" }}>{row.qib_x ? `${row.qib_x}x` : "—"}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 11, color: C.gray }}>NII</span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#d97706" }}>{row.nii_x ? `${row.nii_x}x` : "—"}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 11, color: C.gray }}>Retail</span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#16a34a" }}>{row.retail_x ? `${row.retail_x}x` : "—"}</span>
                      </div>
                      {row.notes && <div style={{ fontSize: 10, color: C.gray, marginTop: 5, lineHeight: 1.4 }}>{row.notes}</div>}
                    </>
                  )}
                </div>
              )
            })}
          </div>

          {/* Momentum chart */}
          {days.length > 1 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: C.gray, marginBottom: 6 }}>Subscription momentum</div>
              <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H + 10, display: "block" }}>
                {/* Y gridlines */}
                {[0.25, 0.5, 0.75, 1].map(pct => {
                  const y = padT + cH - pct * cH
                  const v = Math.round(maxV * pct)
                  return (
                    <g key={pct}>
                      <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="#e5e7eb" strokeWidth="0.5" />
                      <text x={padL - 4} y={y} textAnchor="end" dominantBaseline="central" fontSize="9" fill="#9ca3af">{v}x</text>
                    </g>
                  )
                })}
                {/* X axis labels */}
                {[0, 1, 2].map(i => (
                  <text key={i} x={xPos(i)} y={H - 2} textAnchor="middle" fontSize="9" fill="#9ca3af">{chartDays[i]}</text>
                ))}
                {/* Lines */}
                {(["qib_x", "nii_x", "retail_x"] as const).map(key => {
                  const path = lineFor(key)
                  if (!path) return null
                  return <path key={key} d={path} fill="none" stroke={seriesColors[key]} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                })}
                {/* Dots */}
                {(["qib_x", "nii_x", "retail_x"] as const).flatMap(key =>
                  dotFor(key).map((pt, i) => (
                    <circle key={`${key}-${i}`} cx={pt.x} cy={pt.y} r={3} fill={seriesColors[key]} />
                  ))
                )}
              </svg>
              {/* Legend */}
              <div style={{ display: "flex", gap: 14, justifyContent: "center" }}>
                {(["qib_x", "nii_x", "retail_x"] as const).map(key => (
                  <div key={key} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <div style={{ width: 10, height: 3, borderRadius: 2, background: seriesColors[key] }} />
                    <span style={{ fontSize: 10, color: C.gray }}>{seriesLabels[key]}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Signal alerts */}
          {(isQibAccelerating || isNiiJumping) && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {isQibAccelerating && (
                <div style={{ background: C.blueBg, border: `1px solid ${C.blueBd}`, borderRadius: 8, padding: "9px 12px", display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span style={{ fontSize: 16 }}>⚡</span>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.blue, marginBottom: 2 }}>QIB ACCELERATION SIGNAL</div>
                    <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.5 }}>
                      QIB jumped +{qibAcceleration}% from Day 1 to Day 2 — strongest predictor of final oversubscription. Institutional conviction is building.
                    </div>
                  </div>
                </div>
              )}
              {isNiiJumping && (
                <div style={{ background: "#fff7ed", border: `1px solid ${C.amberBd}`, borderRadius: 8, padding: "9px 12px", display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span style={{ fontSize: 16 }}>🚨</span>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.amber, marginBottom: 2 }}>NII CONVICTION JUMP</div>
                    <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.5 }}>
                      NII/HNI surged +{niiJump}% on Day 2 — HNI money arriving late signals strong conviction. Watch Day 3 for confirmation.
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Latest snapshot */}
          {latest && (
            <div style={{ marginTop: 12, padding: "8px 12px", background: C.grayBg, borderRadius: 8, fontSize: 11, color: C.gray }}>
              Latest (Day {latest.day}): QIB {latest.qib_x ? `${latest.qib_x}x` : "—"} · NII {latest.nii_x ? `${latest.nii_x}x` : "—"} · Retail {latest.retail_x ? `${latest.retail_x}x` : "—"}
            </div>
          )}
        </>
      )}

      {!loading && days.length === 0 && !showForm && (
        <div style={{ textAlign: "center", padding: "20px 0", color: C.gray }}>
          <div style={{ fontSize: 28, marginBottom: 6 }}>📊</div>
          <div style={{ fontSize: 12 }}>No subscription data yet.<br />Enter Day 1 figures once the IPO opens.</div>
        </div>
      )}
    </Card>
  )
}

