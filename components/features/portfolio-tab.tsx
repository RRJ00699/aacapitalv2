"use client"
// components/features/portfolio-tab.tsx
// Live portfolio from Zerodha + manual entry drawer.
// SESSION 9: Added ManualHoldingsDrawer — so you can track positions
// even when Zerodha isn't connected or you hold stocks outside Kite.

import { useState, useEffect, useRef } from "react"
import { PortfolioIntelligence } from "./portfolio-intelligence"

const T = {
  white:"#FFFFFF", border:"#E5E7EB", text:"#111827", textSub:"#374151",
  gray:"#6B7280",  grayBg:"#F9FAFB",
  blue:"#2563EB",  blueBg:"#EFF6FF",  blueBd:"#BFDBFE",
  green:"#16A34A", greenBg:"#F0FDF4", greenBd:"#BBF7D0",
  red:"#DC2626",   redBg:"#FEF2F2",   redBd:"#FECACA",
  amber:"#D97706", amberBg:"#FFFBEB", amberBd:"#FDE68A",
  purple:"#7C3AED",
}
function pnlColor(v:number){return v>=0?T.green:T.red}
function fmt(v:number){return v.toLocaleString("en-IN",{maximumFractionDigits:0})}
function fmtPct(v:number){return`${v>=0?"+":""}${v.toFixed(2)}%`}
function recColor(rec:string|undefined){
  if(!rec)return T.gray
  if(rec.includes("Aggressively"))return T.green
  if(rec.includes("Avoid"))return T.red
  if(rec.includes("Trade"))return"#0891B2"
  if(rec.includes("Watch"))return T.amber
  return T.blue
}
function Card({children,style={}}:{children:any;style?:any}){
  return<div style={{background:T.white,border:`1px solid ${T.border}`,borderRadius:14,padding:16,marginBottom:14,...style}}>{children}</div>
}

// ─── Manual holding type ─────────────────────────────────────────────────────
interface ManualHolding {
  id: string
  symbol: string
  quantity: number
  avgPrice: number
  buyDate: string
  // runtime fields (filled in when live price is fetched)
  lastPrice?: number
  currentValue?: number
  investedValue?: number
  pnl?: number
  pnlPct?: number
}

// ─── Manual Holdings Drawer ──────────────────────────────────────────────────
function ManualHoldingsDrawer({
  open, onClose, onAdd,
}: { open: boolean; onClose: () => void; onAdd: (h: ManualHolding) => void }) {
  const [sym,  setSym]  = useState("")
  const [qty,  setQty]  = useState("")
  const [avg,  setAvg]  = useState("")
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [err,  setErr]  = useState("")
  const symRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setSym(""); setQty(""); setAvg(""); setErr("")
      setTimeout(() => symRef.current?.focus(), 60)
    }
  }, [open])

  function handleAdd() {
    const s = sym.trim().toUpperCase()
    const q = parseFloat(qty)
    const p = parseFloat(avg)
    if (!s)          return setErr("Symbol required")
    if (!q || q <= 0) return setErr("Quantity must be > 0")
    if (!p || p <= 0) return setErr("Avg price must be > 0")
    const h: ManualHolding = {
      id: `${s}-${Date.now()}`,
      symbol: s, quantity: q, avgPrice: p, buyDate: date,
      investedValue: q * p,
      lastPrice: p,           // will update when price refresh runs
      currentValue: q * p,
      pnl: 0, pnlPct: 0,
    }
    onAdd(h)
    setSym(""); setQty(""); setAvg(""); setErr("")
  }

  const overlay: React.CSSProperties = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 9998,
    display: open ? "block" : "none",
  }
  const drawer: React.CSSProperties = {
    position: "fixed", top: 0, right: 0, bottom: 0, width: 340,
    background: T.white, zIndex: 9999, padding: 24, overflowY: "auto",
    boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
    transform: open ? "translateX(0)" : "translateX(100%)",
    transition: "transform 0.25s cubic-bezier(.4,0,.2,1)",
  }

  return (
    <>
      <div style={overlay} onClick={onClose} />
      <div style={drawer}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}>
          <div style={{fontSize:16,fontWeight:800,color:T.text}}>Add holding manually</div>
          <button onClick={onClose} style={{background:"none",border:"none",fontSize:20,cursor:"pointer",color:T.gray,lineHeight:1}}>×</button>
        </div>

        <div style={{fontSize:11,color:T.gray,marginBottom:18,lineHeight:1.6}}>
          Track positions not in Zerodha, or use this when Kite isn't connected.
          Holdings are saved for this session.
        </div>

        {[
          { label:"Symbol (NSE)", placeholder:"e.g. ABCAPITAL", value:sym, onChange:setSym, ref:symRef, inputMode:"text" },
          { label:"Quantity",     placeholder:"e.g. 100",        value:qty, onChange:setQty, inputMode:"numeric" },
          { label:"Avg Buy Price (₹)", placeholder:"e.g. 360",   value:avg, onChange:setAvg, inputMode:"decimal" },
        ].map(f => (
          <div key={f.label} style={{marginBottom:14}}>
            <div style={{fontSize:11,fontWeight:600,color:T.textSub,marginBottom:5}}>{f.label}</div>
            <input
              ref={(f as any).ref}
              value={f.value}
              onChange={e => f.onChange(e.target.value)}
              placeholder={f.placeholder}
              inputMode={(f.inputMode as any) ?? "text"}
              style={{width:"100%",boxSizing:"border-box",padding:"9px 12px",borderRadius:8,
                border:`1px solid ${T.border}`,fontSize:13,color:T.text,outline:"none"}}
            />
          </div>
        ))}

        <div style={{marginBottom:18}}>
          <div style={{fontSize:11,fontWeight:600,color:T.textSub,marginBottom:5}}>Buy Date</div>
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            style={{width:"100%",boxSizing:"border-box",padding:"9px 12px",borderRadius:8,
              border:`1px solid ${T.border}`,fontSize:13,color:T.text,outline:"none"}} />
        </div>

        {err && (
          <div style={{background:T.redBg,border:`1px solid ${T.redBd}`,borderRadius:8,
            padding:"8px 12px",marginBottom:14,fontSize:12,color:T.red}}>{err}</div>
        )}

        {avg && qty && (
          <div style={{background:T.blueBg,border:`1px solid ${T.blueBd}`,borderRadius:8,
            padding:"10px 12px",marginBottom:14,fontSize:12,color:T.blue}}>
            Invested: ₹{fmt(parseFloat(qty||"0") * parseFloat(avg||"0"))}
          </div>
        )}

        <button onClick={handleAdd} style={{width:"100%",padding:"11px",borderRadius:10,
          background:T.blue,color:T.white,fontWeight:700,fontSize:13,
          border:"none",cursor:"pointer",marginBottom:10}}>
          Add to portfolio
        </button>
        <button onClick={onClose} style={{width:"100%",padding:"9px",borderRadius:10,
          background:"none",color:T.gray,fontWeight:500,fontSize:12,
          border:`1px solid ${T.border}`,cursor:"pointer"}}>
          Cancel
        </button>
      </div>
    </>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────
export function PortfolioTab(){
  const[holdings,   setHoldings]   = useState<any[]>([])
  const[manualH,    setManualH]    = useState<ManualHolding[]>([])
  const[drawerOpen, setDrawerOpen] = useState(false)
  const[summary,    setSummary]    = useState<any>(null)
  const[settings,   setSettings]   = useState<any>({})
  const[opportunities,setOpportunities]=useState<any[]>([])
  const[loading,    setLoading]    = useState(true)
  const[error,      setError]      = useState("")
  const[sort,       setSort]       = useState<"value"|"pnl"|"pct">("value")
  const[showManual, setShowManual] = useState(false)

  useEffect(()=>{
    Promise.all([
      fetch("/api/broker/holdings").then(r=>r.json()),
      fetch("/api/settings").then(r=>r.json()),
      fetch("/api/ipo").then(r=>r.json()),
    ]).then(([h,s,ipo])=>{
      if(h.ok){setHoldings(h.holdings||[]);setSummary(h.summary)}
      else setError(h.error||"Broker not connected")
      if(s.settings)setSettings(s.settings)
      const opps=(ipo.ipos||[])
        .filter((i:any)=>i.status!=="LISTED")
        .sort((a:any,b:any)=>(b.score?.listingScore||0)-(a.score?.listingScore||0))
        .slice(0,3)
      setOpportunities(opps)
      setLoading(false)
    }).catch(()=>{setError("Failed to load portfolio");setLoading(false)})
  },[])

  // Merge manual holdings: compute P&L as 0 (no live price yet; upgrade later)
  const allHoldings = [
    ...holdings,
    ...manualH.map(m => ({
      ...m, isManual: true,
      currentValue:  m.investedValue ?? 0,
      pnl:           0,
      pnlPct:        0,
      lastPrice:     m.avgPrice,
    })),
  ]

  const cagr=(()=>{
    if(!settings.portfolioStartDate||!summary||!settings.startingCapital)return null
    const years=(Date.now()-new Date(settings.portfolioStartDate).getTime())/(365.25*864e5)
    if(years<0.05)return null
    const tv=summary.totalCurrent+(settings.startingCapital-summary.totalInvested)
    return{value:(((tv/settings.startingCapital)**(1/years)-1)*100).toFixed(1),years:years.toFixed(1)}
  })()
  const targetCAGR=(settings.targetCapital&&settings.startingCapital&&settings.targetYears)
    ?(((settings.targetCapital/settings.startingCapital)**(1/settings.targetYears)-1)*100).toFixed(1):null

  const sorted=[...allHoldings].sort((a,b)=>
    sort==="value"?b.currentValue-a.currentValue:sort==="pnl"?b.pnl-a.pnl:b.pnlPct-a.pnlPct)
  const top5=[...allHoldings].sort((a,b)=>b.currentValue-a.currentValue).slice(0,5)
  const underperformers=allHoldings.filter(h=>h.pnlPct<-5).sort((a,b)=>a.pnlPct-b.pnlPct).slice(0,3)
  const topOpp=opportunities[0]

  const manualTotal = manualH.reduce((s, m) => s + (m.investedValue ?? 0), 0)

  if(loading)return(
    <div style={{display:"flex",alignItems:"center",justifyContent:"center",height:220,gap:10,color:T.gray,fontSize:13}}>
      <div style={{width:16,height:16,border:"2px solid #E5E7EB",borderTopColor:T.blue,borderRadius:"50%",animation:"spin .7s linear infinite"}}/>
      Loading portfolio from Zerodha…
    </div>
  )

  // When Zerodha not connected — show manual entry option instead of dead-end screen
  if(error)return(
    <div style={{maxWidth:600,margin:"0 auto",padding:16}}>
      <div style={{background:T.redBg,border:`1px solid ${T.redBd}`,borderRadius:14,padding:"16px 20px",marginBottom:16}}>
        <div style={{fontSize:13,fontWeight:700,color:T.red,marginBottom:6}}>⚠ {error}</div>
        <div style={{fontSize:11,color:T.gray,marginBottom:14,lineHeight:1.6}}>
          Zerodha isn't connected. You can still track your portfolio manually below,
          or connect Zerodha for live prices and P&L.
        </div>
        <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
          <a href="/api/auth/zerodha" style={{display:"inline-block",padding:"9px 20px",background:"#FF6600",
            borderRadius:8,color:"#fff",fontSize:12,fontWeight:700,textDecoration:"none"}}>
            Connect Zerodha
          </a>
          <button onClick={() => setDrawerOpen(true)} style={{padding:"9px 20px",background:T.blueBg,
            border:`1px solid ${T.blueBd}`,borderRadius:8,color:T.blue,fontSize:12,fontWeight:700,cursor:"pointer"}}>
            + Add holding manually
          </button>
        </div>
      </div>

      {/* Show manual holdings even in error state */}
      {manualH.length > 0 && (
        <Card style={{padding:0,overflow:"hidden"}}>
          <div style={{padding:"14px 16px",borderBottom:`1px solid ${T.border}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <div style={{fontSize:13,fontWeight:700,color:T.text}}>Manual Holdings ({manualH.length})</div>
            <button onClick={() => setDrawerOpen(true)} style={{padding:"5px 12px",borderRadius:7,
              background:T.blueBg,border:`1px solid ${T.blueBd}`,color:T.blue,fontSize:11,fontWeight:700,cursor:"pointer"}}>
              + Add more
            </button>
          </div>
          <ManualHoldingsTable holdings={manualH} onRemove={id => setManualH(p => p.filter(m => m.id !== id))} />
        </Card>
      )}

      <ManualHoldingsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}
        onAdd={h => { setManualH(p => [...p, h]); setDrawerOpen(false) }} />
    </div>
  )

  if(!summary)return null

  return(
    <div style={{maxWidth:960,margin:"0 auto",padding:16}}>

      {/* Drawer */}
      <ManualHoldingsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}
        onAdd={h => { setManualH(p => [...p, h]); setDrawerOpen(false) }} />

      <div style={{marginBottom:20,display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
        <div>
          <div style={{fontSize:22,fontWeight:800,color:T.text,marginBottom:4}}>Portfolio</div>
          <div style={{fontSize:12,color:T.gray}}>Live from Zerodha · Real holdings · P&L + CAGR tracking</div>
        </div>
        <button onClick={() => setDrawerOpen(true)} style={{padding:"8px 16px",borderRadius:9,
          background:T.blueBg,border:`1px solid ${T.blueBd}`,color:T.blue,fontSize:12,fontWeight:700,cursor:"pointer"}}>
          + Add manual holding
        </button>
      </div>

      {/* Manual holdings notice */}
      {manualH.length > 0 && (
        <div style={{background:T.amberBg,border:`1px solid ${T.amberBd}`,borderRadius:10,
          padding:"10px 14px",marginBottom:14,display:"flex",justifyContent:"space-between",alignItems:"center",flexWrap:"wrap",gap:8}}>
          <div style={{fontSize:12,color:T.amber}}>
            <strong>{manualH.length} manual holding{manualH.length !== 1 ? "s" : ""}</strong> · ₹{fmt(manualTotal)} invested · Live P&L not available (no broker price feed)
          </div>
          <button onClick={() => setShowManual(!showManual)} style={{background:"none",border:"none",
            color:T.amber,fontSize:11,cursor:"pointer",fontWeight:600}}>
            {showManual ? "Hide" : "View"} manual holdings
          </button>
        </div>
      )}

      {/* Manual holdings table (expandable) */}
      {showManual && manualH.length > 0 && (
        <Card style={{padding:0,overflow:"hidden",marginBottom:14}}>
          <div style={{padding:"14px 16px",borderBottom:`1px solid ${T.border}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <div style={{fontSize:13,fontWeight:700,color:T.text}}>Manual Holdings ({manualH.length})</div>
            <button onClick={() => setDrawerOpen(true)} style={{padding:"5px 12px",borderRadius:7,
              background:T.blueBg,border:`1px solid ${T.blueBd}`,color:T.blue,fontSize:11,fontWeight:700,cursor:"pointer"}}>
              + Add more
            </button>
          </div>
          <ManualHoldingsTable holdings={manualH} onRemove={id => setManualH(p => p.filter(m => m.id !== id))} />
        </Card>
      )}

      {/* Summary */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(145px,1fr))",gap:10,marginBottom:14}}>
        {[
          {l:"Portfolio Value",  v:`₹${fmt(summary.totalCurrent)}`,  c:T.blue},
          {l:"Total Invested",   v:`₹${fmt(summary.totalInvested)}`, c:T.text},
          {l:"Total P&L",        v:`${summary.totalPnl>=0?"+":"−"}₹${fmt(Math.abs(summary.totalPnl))}`, c:pnlColor(summary.totalPnl)},
          {l:"Return",           v:fmtPct(summary.totalPnlPct),      c:pnlColor(summary.totalPnlPct)},
          {l:"Cash Available",   v:`₹${fmt(summary.availableFunds)}`,c:T.green},
          {l:"Holdings",         v:`${allHoldings.length} stocks`,   c:T.purple},
        ].map(s=>(
          <div key={s.l} style={{background:T.white,border:`1px solid ${T.border}`,borderRadius:12,padding:"13px 15px"}}>
            <div style={{fontSize:10,color:T.gray,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:6}}>{s.l}</div>
            <div style={{fontSize:19,fontWeight:800,color:s.c,lineHeight:1}}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* CAGR */}
      {cagr&&(
        <div style={{background:"linear-gradient(135deg,#0f172a,#1e3a5f)",borderRadius:12,padding:"16px 20px",marginBottom:14,display:"flex",gap:24,flexWrap:"wrap",alignItems:"center"}}>
          <div>
            <div style={{fontSize:10,color:"#475569",textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>Portfolio CAGR ({cagr.years}y)</div>
            <div style={{fontSize:40,fontWeight:900,color:parseFloat(cagr.value)>=0?"#4ade80":"#f87171",lineHeight:1}}>{cagr.value}%</div>
          </div>
          {targetCAGR&&(
            <div>
              <div style={{fontSize:10,color:"#475569",textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>Required CAGR</div>
              <div style={{fontSize:28,fontWeight:900,color:"#fbbf24",lineHeight:1}}>{targetCAGR}%</div>
            </div>
          )}
          <div style={{flex:1,minWidth:180,fontSize:11,color:"#64748b",lineHeight:1.7}}>
            Start: {settings.portfolioStartDate||"—"} · Capital: ₹{fmt(settings.startingCapital||0)}
            <br/>{targetCAGR&&parseFloat(cagr.value)<parseFloat(targetCAGR)
              ?"⚠ Below target — deploy idle cash or increase position sizing."
              :"✓ On track to hit your compounding target."}
          </div>
        </div>
      )}
      {!cagr&&!settings.portfolioStartDate&&(
        <div style={{background:T.amberBg,border:`1px solid ${T.amberBd}`,borderRadius:10,padding:"10px 14px",marginBottom:14,fontSize:11,color:T.amber}}>
          ⚠ Go to <strong>Settings</strong> → enter Portfolio Start Date + Starting Capital to enable CAGR tracking.
        </div>
      )}

      {/* Concentration */}
      <Card>
        <div style={{fontSize:13,fontWeight:700,color:T.text,marginBottom:14}}>📊 Concentration — Top 5</div>
        {top5.map((h,i)=>{
          const totalVal = summary.totalCurrent + manualTotal
          const pct = totalVal>0 ? (h.currentValue/totalVal)*100 : 0
          const colors=[T.blue,"#7C3AED","#0891B2",T.amber,"#059669"]
          return(
            <div key={h.symbol} style={{marginBottom:i<top5.length-1?12:0}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  <span style={{fontSize:13,fontWeight:700,color:T.text}}>{h.symbol}</span>
                  {(h as any).isManual && <span style={{fontSize:9,padding:"1px 5px",borderRadius:4,background:T.amberBg,color:T.amber,fontWeight:600}}>MANUAL</span>}
                  <span style={{fontSize:11,color:T.gray}}>{pct.toFixed(1)}%</span>
                </div>
                <div style={{display:"flex",gap:14}}>
                  <span style={{fontSize:12,color:T.gray}}>₹{fmt(h.currentValue)}</span>
                  <span style={{fontSize:12,fontWeight:700,color:pnlColor(h.pnl)}}>{h.pnl>=0?"+":"−"}₹{fmt(Math.abs(h.pnl))} ({fmtPct(h.pnlPct)})</span>
                </div>
              </div>
              <div style={{height:6,background:"#F3F4F6",borderRadius:3}}>
                <div style={{width:`${pct}%`,height:"100%",background:colors[i]||T.blue,borderRadius:3}}/>
              </div>
            </div>
          )
        })}
      </Card>

      {/* Portfolio Intelligence */}
      <Card>
        <div style={{fontSize:13,fontWeight:700,color:T.text,marginBottom:14}}>🧠 Portfolio Intelligence</div>
        <PortfolioIntelligence />
      </Card>

      {/* Opportunity Cost Engine */}
      {(underperformers.length>0||topOpp)&&(
        <div style={{background:"linear-gradient(135deg,#fef9c3,#fffff0)",border:`1px solid ${T.amberBd}`,borderRadius:14,padding:16,marginBottom:14}}>
          <div style={{fontSize:14,fontWeight:700,color:T.text,marginBottom:4}}>💡 Opportunity Cost Engine</div>
          <div style={{fontSize:11,color:T.gray,marginBottom:14}}>Capital locked in underperformers vs current best opportunity</div>
          {topOpp&&(
            <div style={{background:T.white,border:`1px solid ${T.border}`,borderRadius:10,padding:"12px 14px",marginBottom:12}}>
              <div style={{fontSize:10,color:T.gray,marginBottom:6,textTransform:"uppercase",letterSpacing:"0.06em",fontWeight:600}}>Best Current Opportunity</div>
              <div style={{display:"flex",alignItems:"center",gap:12,flexWrap:"wrap"}}>
                <div style={{flex:2}}>
                  <div style={{fontSize:14,fontWeight:800,color:T.text,marginBottom:2}}>{topOpp.name}</div>
                  <div style={{fontSize:11,color:T.gray}}>{topOpp.sector} · {topOpp.status} · ₹{topOpp.issueSize}Cr</div>
                </div>
                <div style={{textAlign:"center"}}>
                  <div style={{fontSize:9,color:T.gray,marginBottom:2}}>SCORE</div>
                  <div style={{fontSize:24,fontWeight:900,color:(topOpp.score?.listingScore||0)>=70?T.green:T.blue}}>{topOpp.score?.listingScore??"—"}</div>
                </div>
                {topOpp.score?.recommendation&&(
                  <div style={{padding:"5px 10px",borderRadius:7,fontSize:11,fontWeight:700,color:recColor(topOpp.score.recommendation),background:recColor(topOpp.score.recommendation)+"18",border:`1px solid ${recColor(topOpp.score.recommendation)}30`}}>
                    {topOpp.score.recommendation.split("—")[0].trim().split(" ").slice(0,3).join(" ")}
                  </div>
                )}
              </div>
            </div>
          )}
          {underperformers.length>0?(
            <div>
              <div style={{fontSize:10,color:T.gray,marginBottom:8,textTransform:"uppercase",letterSpacing:"0.06em",fontWeight:600}}>Underperforming Holdings (&lt;−5%)</div>
              {underperformers.map(h=>{
                const expectedGain=topOpp?((topOpp.score?.listingScore||50)/100*25):0
                const oppCost=h.currentValue*(expectedGain/100)
                return(
                  <div key={h.symbol} style={{display:"flex",alignItems:"center",gap:12,padding:"10px 12px",background:T.redBg,border:`1px solid ${T.redBd}`,borderRadius:9,marginBottom:7,flexWrap:"wrap"}}>
                    <div style={{flex:2,minWidth:100}}>
                      <span style={{fontSize:14,fontWeight:800,color:T.text}}>{h.symbol}</span>
                      <span style={{marginLeft:8,fontSize:12,fontWeight:700,color:T.red}}>{fmtPct(h.pnlPct)}</span>
                    </div>
                    <div style={{fontSize:12,color:T.textSub}}>₹{fmt(h.currentValue)} deployed</div>
                    {topOpp&&(
                      <div style={{fontSize:11,color:T.amber,fontWeight:600,textAlign:"right",flex:1,minWidth:160}}>
                        If redeployed to {topOpp.name.split(" ")[0]} →
                        <span style={{color:T.green}}> expected +₹{fmt(oppCost)} ({expectedGain.toFixed(0)}%)</span>
                      </div>
                    )}
                  </div>
                )
              })}
              <div style={{fontSize:10,color:T.gray,marginTop:8,lineHeight:1.5}}>
                ⚠ Indicative only. Expected gain is a proxy based on listing score — not a guarantee.
              </div>
            </div>
          ):(
            <div style={{padding:"12px 14px",background:T.greenBg,border:`1px solid ${T.greenBd}`,borderRadius:9,fontSize:12,color:T.green,fontWeight:600}}>
              ✅ No significant underperformers. Portfolio performing well.
            </div>
          )}
        </div>
      )}

      {/* All Holdings table */}
      <Card style={{padding:0,overflow:"hidden"}}>
        <div style={{padding:"14px 16px",borderBottom:`1px solid ${T.border}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
          <div style={{fontSize:13,fontWeight:700,color:T.text}}>All Holdings ({allHoldings.length})</div>
          <div style={{display:"flex",gap:6}}>
            {([["value","By Value"],["pnl","By P&L ₹"],["pct","By P&L %"]]as const).map(([k,l])=>(
              <button key={k} onClick={()=>setSort(k)} style={{padding:"4px 10px",borderRadius:6,fontSize:11,cursor:"pointer",border:`1px solid ${sort===k?T.blue:T.border}`,background:sort===k?T.blueBg:"transparent",color:sort===k?T.blue:T.gray,fontWeight:sort===k?600:400}}>{l}</button>
            ))}
          </div>
        </div>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead>
              <tr style={{background:T.grayBg}}>
                {["Symbol","Qty","Avg Price","LTP","Invested","Current","P&L","P&L %"].map(h=>(
                  <th key={h} style={{padding:"9px 12px",textAlign:"left",fontSize:10,color:T.gray,textTransform:"uppercase",letterSpacing:"0.05em",borderBottom:`1px solid ${T.border}`,whiteSpace:"nowrap",fontWeight:600}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((h,i)=>(
                <tr key={(h as any).id ?? h.symbol} style={{borderBottom:`1px solid ${i===sorted.length-1?"transparent":"#F3F4F6"}`}}>
                  <td style={{padding:"10px 12px",fontWeight:700,color:T.text,fontSize:13}}>
                    {h.symbol}
                    {(h as any).isManual && <span style={{marginLeft:6,fontSize:9,padding:"1px 5px",borderRadius:4,background:T.amberBg,color:T.amber,fontWeight:600}}>MANUAL</span>}
                  </td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12}}>{h.quantity}</td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12,fontFamily:"monospace"}}>₹{(h.avgPrice??0).toFixed(2)}</td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12,fontFamily:"monospace"}}>
                    {(h as any).isManual ? <span style={{color:T.amber,fontSize:10}}>—</span> : `₹${(h.lastPrice??0).toFixed(2)}`}
                  </td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12}}>₹{fmt(h.investedValue??0)}</td>
                  <td style={{padding:"10px 12px",fontWeight:600,color:T.blue,fontSize:12}}>₹{fmt(h.currentValue??0)}</td>
                  <td style={{padding:"10px 12px",fontWeight:700,fontSize:12,color:pnlColor(h.pnl??0)}}>
                    {(h as any).isManual ? <span style={{color:T.amber,fontSize:10}}>No live price</span> : `${h.pnl>=0?"+":"−"}₹${fmt(Math.abs(h.pnl??0))}`}
                  </td>
                  <td style={{padding:"10px 12px",fontWeight:700,fontSize:12,color:pnlColor(h.pnlPct??0)}}>
                    {(h as any).isManual ? "—" : fmtPct(h.pnlPct??0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ─── Manual holdings table (shared between error state + main view) ───────────
function ManualHoldingsTable({ holdings, onRemove }: { holdings: ManualHolding[]; onRemove: (id: string) => void }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: T.grayBg }}>
            {["Symbol", "Qty", "Avg Price", "Invested", "Buy Date", ""].map(h => (
              <th key={h} style={{ padding: "9px 12px", textAlign: "left", fontSize: 10, color: T.gray,
                textTransform: "uppercase", letterSpacing: "0.05em",
                borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap", fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {holdings.map((h, i) => (
            <tr key={h.id} style={{ borderBottom: `1px solid ${i === holdings.length - 1 ? "transparent" : "#F3F4F6"}` }}>
              <td style={{ padding: "10px 12px", fontWeight: 700, color: T.text, fontSize: 13 }}>{h.symbol}</td>
              <td style={{ padding: "10px 12px", color: T.textSub, fontSize: 12 }}>{h.quantity}</td>
              <td style={{ padding: "10px 12px", color: T.textSub, fontSize: 12, fontFamily: "monospace" }}>₹{h.avgPrice.toFixed(2)}</td>
              <td style={{ padding: "10px 12px", color: T.textSub, fontSize: 12 }}>₹{(h.quantity * h.avgPrice).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>
              <td style={{ padding: "10px 12px", color: T.textSub, fontSize: 12 }}>{h.buyDate}</td>
              <td style={{ padding: "10px 12px" }}>
                <button onClick={() => onRemove(h.id)} style={{ background: "none", border: "none",
                  color: T.red, fontSize: 11, cursor: "pointer", padding: "2px 6px" }}>Remove</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
