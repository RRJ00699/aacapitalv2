"use client"
// components/features/portfolio-tab.tsx
// Live portfolio from Zerodha + Opportunity Cost Engine.

import { useState, useEffect } from "react"
import { PortfolioIntelligence } from "./portfolio-intelligence"


const T = {
  white:"#FFFFFF",border:"#E5E7EB",text:"#111827",textSub:"#374151",
  gray:"#6B7280",grayBg:"#F9FAFB",
  blue:"#2563EB",blueBg:"#EFF6FF",blueBd:"#BFDBFE",
  green:"#16A34A",greenBg:"#F0FDF4",greenBd:"#BBF7D0",
  red:"#DC2626",redBg:"#FEF2F2",redBd:"#FECACA",
  amber:"#D97706",amberBg:"#FFFBEB",amberBd:"#FDE68A",
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

export function PortfolioTab(){
  const[holdings,setHoldings]=useState<any[]>([])
  const[summary,setSummary]=useState<any>(null)
  const[settings,setSettings]=useState<any>({})
  const[opportunities,setOpportunities]=useState<any[]>([])
  const[loading,setLoading]=useState(true)
  const[error,setError]=useState("")
  const[sort,setSort]=useState<"value"|"pnl"|"pct">("value")
  const[manualHoldings,setManualHoldings]=useState<any[]>([])
  const[showManualForm,setShowManualForm]=useState(false)
  const[manualSym,setManualSym]=useState("")
  const[manualQty,setManualQty]=useState("")
  const[manualAvg,setManualAvg]=useState("")

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

  const cagr=(()=>{
    if(!settings.portfolioStartDate||!summary||!settings.startingCapital)return null
    const years=(Date.now()-new Date(settings.portfolioStartDate).getTime())/(365.25*864e5)
    if(years<0.05)return null
    const tv=summary.totalCurrent+(settings.startingCapital-summary.totalInvested)
    return{value:(((tv/settings.startingCapital)**(1/years)-1)*100).toFixed(1),years:years.toFixed(1)}
  })()
  const targetCAGR=(settings.targetCapital&&settings.startingCapital&&settings.targetYears)
    ?(((settings.targetCapital/settings.startingCapital)**(1/settings.targetYears)-1)*100).toFixed(1):null

  const sorted=[...holdings].sort((a,b)=>
    sort==="value"?b.currentValue-a.currentValue:sort==="pnl"?b.pnl-a.pnl:b.pnlPct-a.pnlPct)
  const top5=[...holdings].sort((a,b)=>b.currentValue-a.currentValue).slice(0,5)
  const underperformers=holdings.filter(h=>h.pnlPct<-5).sort((a,b)=>a.pnlPct-b.pnlPct).slice(0,3)
  const topOpp=opportunities[0]

  if(loading)return(
    <div style={{display:"flex",alignItems:"center",justifyContent:"center",height:220,gap:10,color:T.gray,fontSize:13}}>
      <div style={{width:16,height:16,border:"2px solid #E5E7EB",borderTopColor:T.blue,borderRadius:"50%",animation:"spin .7s linear infinite"}}/>
      Loading portfolio from Zerodha…
    </div>
  )
  if(error)return(
    <div style={{maxWidth:480,margin:"60px auto",textAlign:"center",padding:16}}>
      <div style={{fontSize:40,marginBottom:12}}>🔌</div>
      <div style={{fontSize:15,fontWeight:700,color:T.red,marginBottom:8}}>{error}</div>
      <div style={{fontSize:12,color:T.gray,marginBottom:20,lineHeight:1.6}}>Connect Zerodha to see your live portfolio.</div>
      <div style={{display:"flex",gap:12,flexWrap:"wrap" as const,justifyContent:"center",marginTop:8}}>
      <a href="/api/auth/zerodha" style={{display:"inline-block",padding:"10px 24px",background:"#FF6600",borderRadius:8,color:"#fff",fontSize:13,fontWeight:700,textDecoration:"none"}}>Connect Zerodha →</a>
    </div>
  )
  if(!summary)return null

  return(
    <div style={{maxWidth:960,margin:"0 auto",padding:16}}>
      <div style={{marginBottom:20}}>
        <div style={{fontSize:22,fontWeight:800,color:T.text,marginBottom:4}}>Portfolio</div>
        <div style={{fontSize:12,color:T.gray}}>Live from Zerodha · Real holdings · P&L + CAGR tracking</div>
      </div>

      {/* Summary */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(145px,1fr))",gap:10,marginBottom:14}}>
        {[
          {l:"Portfolio Value",v:`₹${fmt(summary.totalCurrent)}`,c:T.blue},
          {l:"Total Invested",v:`₹${fmt(summary.totalInvested)}`,c:T.text},
          {l:"Total P&L",v:`${summary.totalPnl>=0?"+":"−"}₹${fmt(Math.abs(summary.totalPnl))}`,c:pnlColor(summary.totalPnl)},
          {l:"Return",v:fmtPct(summary.totalPnlPct),c:pnlColor(summary.totalPnlPct)},
          {l:"Cash Available",v:`₹${fmt(summary.availableFunds)}`,c:T.green},
          {l:"Holdings",v:`${summary.totalHoldings} stocks`,c:T.purple},
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
          const pct=summary.totalCurrent>0?(h.currentValue/summary.totalCurrent)*100:0
          const colors=[T.blue,"#7C3AED","#0891B2",T.amber,"#059669"]
          return(
            <div key={h.symbol} style={{marginBottom:i<top5.length-1?12:0}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  <span style={{fontSize:13,fontWeight:700,color:T.text}}>{h.symbol}</span>
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

      {/* Portfolio Intelligence — Sprint 12 */}
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
                ⚠ Indicative only. Expected gain is a proxy based on listing score — not a guarantee. Verify thesis before exiting any position.
              </div>
            </div>
          ):(
            <div style={{padding:"12px 14px",background:T.greenBg,border:`1px solid ${T.greenBd}`,borderRadius:9,fontSize:12,color:T.green,fontWeight:600}}>
              ✅ No significant underperformers. Portfolio performing well.
            </div>
          )}
        </div>
      )}

      {/* Full table */}
      <Card style={{padding:0,overflow:"hidden"}}>
        <div style={{padding:"14px 16px",borderBottom:`1px solid ${T.border}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
          <div style={{fontSize:13,fontWeight:700,color:T.text}}>All Holdings ({holdings.length})</div>
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
                <tr key={h.symbol} style={{borderBottom:`1px solid ${i===sorted.length-1?"transparent":"#F3F4F6"}`}}>
                  <td style={{padding:"10px 12px",fontWeight:700,color:T.text,fontSize:13}}>{h.symbol}</td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12}}>{h.quantity}</td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12,fontFamily:"monospace"}}>₹{h.avgPrice.toFixed(2)}</td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12,fontFamily:"monospace"}}>₹{h.lastPrice.toFixed(2)}</td>
                  <td style={{padding:"10px 12px",color:T.textSub,fontSize:12}}>₹{fmt(h.investedValue)}</td>
                  <td style={{padding:"10px 12px",fontWeight:600,color:T.blue,fontSize:12}}>₹{fmt(h.currentValue)}</td>
                  <td style={{padding:"10px 12px",fontWeight:700,fontSize:12,color:pnlColor(h.pnl)}}>{h.pnl>=0?"+":"−"}₹{fmt(Math.abs(h.pnl))}</td>
                  <td style={{padding:"10px 12px",fontWeight:700,fontSize:12,color:pnlColor(h.pnlPct)}}>{fmtPct(h.pnlPct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>

  // Merge manual + zerodha holdings
  const allHoldings = [...holdings, ...manualHoldings]

  // Manual form
  const ManualForm = () => showManualForm ? (
    <Card style={{border:`1px solid ${T.blueBd}`,background:T.blueBg,marginBottom:12}}>
      <div style={{fontSize:13,fontWeight:700,color:T.blue,marginBottom:10}}>Add Holding Manually</div>
      <div style={{display:"flex",gap:8,flexWrap:"wrap" as const}}>
        <input value={manualSym} onChange={e=>setManualSym(e.target.value.toUpperCase())}
          placeholder="Symbol (e.g. RELIANCE)" style={{flex:2,minWidth:120,padding:"8px 10px",borderRadius:8,border:`1px solid ${T.border}`,fontSize:13}}/>
        <input value={manualQty} onChange={e=>setManualQty(e.target.value)} type="number"
          placeholder="Qty" style={{flex:1,minWidth:70,padding:"8px 10px",borderRadius:8,border:`1px solid ${T.border}`,fontSize:13}}/>
        <input value={manualAvg} onChange={e=>setManualAvg(e.target.value)} type="number"
          placeholder="Avg price" style={{flex:1,minWidth:90,padding:"8px 10px",borderRadius:8,border:`1px solid ${T.border}`,fontSize:13}}/>
        <button onClick={addManualHolding}
          style={{padding:"8px 16px",background:T.blue,color:"#fff",border:"none",borderRadius:8,fontSize:13,fontWeight:600,cursor:"pointer"}}>
          Add
        </button>
      </div>
      {manualHoldings.length > 0 && (
        <div style={{marginTop:8,fontSize:11,color:T.gray}}>
          {manualHoldings.length} manual holding(s) added. These won't persist after page refresh.
        </div>
      )}
    </Card>
  ) : null
  )
}
