"use client"
import { useState, useCallback } from "react"
import { searchStocks } from "@/lib/constants/stocks"
import type { StockMeta } from "@/lib/constants/stocks"
import Loader from "@/components/shared/Loader"
import Ring from "@/components/shared/Ring"
import Spark from "@/components/shared/Spark"
import StatCard from "@/components/shared/StatCard"

// Deterministic score engine (replaces makeStock for UI scoring)
function seedVal(sym: string, offset=0) {
  const s = sym.split("").reduce((a,c)=>a+c.charCodeAt(0),0)
  return (s*17+offset*31)%100/100
}
function sr(sym:string, min:number, max:number, o=0) { return +(min+seedVal(sym,o)*(max-min)).toFixed(2) }
function sri(sym:string, min:number, max:number, o=0) { return Math.round(sr(sym,min,max,o)) }

function buildScores(sym:string, liveData:any) {
  const pe = liveData?.fundamentals?.pe ?? sr(sym,6,90,2)
  const pb = liveData?.fundamentals?.pb ?? sr(sym,0.6,15,3)
  const roe = liveData?.fundamentals?.roe ?? sr(sym,6,52,4)
  const roce = liveData?.fundamentals?.roce ?? sr(sym,8,55,5)
  const rev3 = liveData?.fundamentals?.revenueCAGR3Y ?? sr(sym,8,42,6)
  const pat3 = liveData?.fundamentals?.patCAGR3Y ?? sr(sym,10,55,7)
  const debt = liveData?.fundamentals?.debtToEquity ?? sr(sym,0.02,2.2,8)
  const promoter = liveData?.ownership?.promoterPct ?? sr(sym,38,79,9)
  const pledge = liveData?.ownership?.pledgePct ?? sr(sym,0,20,10)
  const rsi = liveData?.technicals?.rsi ?? sr(sym,30,78,11)
  const cmp = liveData?.price?.price ?? sr(sym,80,8500,1)
  const ema20 = liveData?.technicals?.ema20 ?? +(cmp*sr(sym,0.93,1.05,13)).toFixed(0)
  const ema50 = liveData?.technicals?.ema50 ?? +(cmp*sr(sym,0.87,1.01,14)).toFixed(0)
  const ema200 = liveData?.technicals?.ema200 ?? +(cmp*sr(sym,0.76,0.96,15)).toFixed(0)
  const fii = liveData?.ownership?.fiiHistory ?? Array.from({length:8},(_,i)=>sr(sym,5,24,20+i))
  const dii = liveData?.ownership?.diiHistory ?? Array.from({length:8},(_,i)=>sr(sym,3,18,30+i))
  const rev = liveData?.fundamentals?.quarterlyRevenue ?? Array.from({length:8},(_,i)=>sr(sym,400,9000,50+i))
  const pat = liveData?.fundamentals?.quarterlyPAT ?? Array.from({length:8},(_,i)=>sr(sym,40,1400,60+i))
  const fcf = liveData?.fundamentals?.quarterlyFCF ?? Array.from({length:8},(_,i)=>sr(sym,-80,900,70+i))
  const piotroski = sri(sym,3,9,91)
  const beneish = sr(sym,-3.8,-1.0,92)
  const altman = sr(sym,1.2,6.5,93)
  const mcap = liveData?.fundamentals?.mcap ?? +(cmp*sr(sym,150,90000,90)).toFixed(0)
  const opMarg = liveData?.fundamentals?.operatingMargin ?? sr(sym,6,38,96)
  const cT = liveData?.fundamentals?.targetMean ?? +(cmp*sr(sym,1.1,1.45,100)).toFixed(0)
  const bullT = liveData?.fundamentals?.targetHigh ?? +(cmp*sr(sym,1.25,1.6,101)).toFixed(0)
  const bearT = liveData?.fundamentals?.targetLow ?? +(cmp*sr(sym,0.88,1.08,102)).toFixed(0)
  const analystCount = liveData?.fundamentals?.analystCount ?? sri(sym,6,30,103)
  const buyPct = liveData?.fundamentals?.buyPct ?? sri(sym,42,85,104)
  const holdPct = sri(sym,8,32,105)
  const sellPct = Math.max(0,100-buyPct-holdPct)
  const gS = Math.min(10,Math.round((rev3>20?3:rev3>15?2:1)+(pat3>25?3:pat3>15?2:1)+4))
  const qS = Math.min(10,Math.round((roe>20?3:2)+(roce>20?3:2)+4))
  const govS = Math.min(10,Math.round((promoter>60?3:promoter>50?2:1)+(pledge<2?3:pledge<5?2:0)+4))
  const valS = Math.min(10,Math.round((pe<20?4:pe<35?3:pe<50?2:1)+(pb<3?3:pb<6?2:1)+3))
  const techS = Math.min(10,Math.round((rsi>50&&rsi<70?4:2)+(cmp>ema50?3:1)+3))
  const ownS = Math.min(10,Math.round((fii[7]>fii[0]?4:2)+(dii[7]>dii[0]?3:1)+3))
  const overall = Math.round(gS*2.5+qS*2.0+govS*2.0+valS*1.5+techS*1.0+ownS*1.0)
  const buyZone = Math.min(100,(roe>20&&roce>20?20:0)+(fii[7]>fii[0]&&dii[7]>dii[0]?15:0)+(cmp>ema50&&cmp>ema200?15:0)+(rev3>15&&pat3>15?10:0)+(promoter>60&&pledge<3?20:0)+(rsi>50&&rsi<70?10:0)+(piotroski>7&&altman>3?10:0))
  const mbScore = Math.min(100,Math.round((rev3>=20?14:rev3>=15?9:4)+(roe>=20?14:roe>=15?9:4)+(roce>=20?12:roce>=15?7:3)+(promoter>=55?11:promoter>=50?7:3)+(pledge<2?10:pledge<5?5:0)+(debt<0.5?10:debt<1?5:1)+(mcap<20000?10:mcap<50000?5:2)+(pat3>=20?10:pat3>=15?6:3)+(piotroski>=7?6:3)))
  const sl = liveData?.technicals?.support1 ?? +(cmp*sr(sym,0.90,0.94,120)).toFixed(0)
  const t1 = +(cmp*sr(sym,1.08,1.15,121)).toFixed(0)
  const t2 = +(cmp*sr(sym,1.16,1.25,122)).toFixed(0)
  const t3 = +(cmp*sr(sym,1.26,1.42,123)).toFixed(0)
  const trend = liveData?.technicals?.trend ?? (cmp>ema200?"Bullish":"Bearish")
  const verd = overall>=80?"STRONG BUY":overall>=70?"ACCUMULATE":overall>=60?"HOLD":overall>=50?"WATCHLIST":"AVOID"
  const verdC = overall>=80?"#16a34a":overall>=70?"#1d4ed8":overall>=60?"#d97706":overall>=50?"#ea580c":"#dc2626"
  const change = liveData?.price?.change ?? sr(sym,-120,180,2)
  const changePct = liveData?.price?.changePct ?? sr(sym,-4,6,3)
  const week52h = liveData?.price?.week52h ?? +(cmp*sr(sym,1.1,1.6,6)).toFixed(2)
  const week52l = liveData?.price?.week52l ?? +(cmp*sr(sym,0.5,0.85,7)).toFixed(2)
  const source = liveData?.source ?? "simulated"

  // Tier classification
  let tier="2",tierLabel="🟡 Tier 2",tierColor="#d97706",tierBg="#fffbeb",tierBorder="#fde68a",tierDesc="Decent business. Trade only with strict SL."
  if(pledge>15){tier="HIGH_RISK";tierLabel="🔴 High Risk";tierColor="#dc2626";tierBg="#fef2f2";tierBorder="#fecaca";tierDesc="Pledge >15% — hard stop. Margin-call risk."}
  else if(overall<50||debt>2){tier="AVOID";tierLabel="⛔ AVOID";tierColor="#dc2626";tierBg="#fef2f2";tierBorder="#fecaca";tierDesc="Critical flags. Hard eliminate."}
  else if(overall>=80&&roce>=20&&promoter>=55&&pledge<5&&rev3>=15){tier="1A";tierLabel="🏆 Tier 1A — Elite";tierColor="#1d4ed8";tierBg="#eff6ff";tierBorder="#bfdbfe";tierDesc="Institutional grade. Full conviction buy on setup."}
  else if(overall>=65&&roce>=15&&promoter>=50&&pledge<10){tier="1";tierLabel="⭐ Tier 1 — Strong";tierColor="#059669";tierBg="#f0fdf4";tierBorder="#bbf7d0";tierDesc="Strong business. Buy on setup with conviction."}

  const buyZoneLabel = buyZone>=91?"⚡ High Conviction":buyZone>=76?"✅ Buy Zone":buyZone>=61?"📌 Accumulate":buyZone>=41?"👁 Watchlist":"❌ Avoid"
  const buyZoneColor = buyZone>=91?"#7c3aed":buyZone>=76?"#16a34a":buyZone>=61?"#1d4ed8":buyZone>=41?"#d97706":"#dc2626"

  return { pe,pb,roe,roce,rev3,pat3,debt,promoter,pledge,rsi,cmp,ema20,ema50,ema200,fii,dii,rev,pat,fcf,piotroski,beneish,altman,mcap,opMarg,cT,bullT,bearT,analystCount,buyPct,holdPct,sellPct,gS,qS,govS,valS,techS,ownS,overall,buyZone,mbScore,sl,t1,t2,t3,trend,verd,verdC,change,changePct,week52h,week52l,source,tier,tierLabel,tierColor,tierBg,tierBorder,tierDesc,buyZoneLabel,buyZoneColor,qs:["Q1'24","Q2'24","Q3'24","Q4'24","Q1'25","Q2'25","Q3'25","Q4'25"] }
}

export default function StocksPage() {
  const [inp, setInp] = useState("")
  const [suggestions, setSuggestions] = useState<StockMeta[]>([])
  const [showSugg, setShowSugg] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sym, setSym] = useState("")
  const [meta, setMeta] = useState<StockMeta|null>(null)
  const [scores, setScores] = useState<any>(null)
  const [page, setPage] = useState("overview")
  const [memo, setMemo] = useState<any>(null)
  const [memoLoad, setMemoLoad] = useState(false)
  const [err, setErr] = useState("")

  const analyze = useCallback(async (s: string) => {
    const upper = s.toUpperCase().trim()
    if (!upper) return
    setErr(""); setLoading(true); setMemo(null); setPage("overview"); setSym(upper)
    try {
      const res = await fetch(`/api/stock?sym=${upper}`)
      const json = await res.json()
      if (json.error) { setErr(json.error); setLoading(false); return }
      setMeta({ sym: upper, name: json.name, exchange: json.exchange, sector: json.sector })
      setScores(buildScores(upper, json))
    } catch { setErr("Failed to fetch data") }
    setLoading(false)
  }, [])

  const genMemo = async () => {
    if (!scores) return
    setMemoLoad(true)
    try {
      const res = await fetch("/api/ai/memo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym, data: { ...scores, exchange: meta?.exchange } }),
      })
      const json = await res.json()
      setMemo(json.memo)
    } catch { }
    setMemoLoad(false)
  }

  const D = scores

  return (
    <div>
      {/* SEARCH */}
      <div style={{ background:"#fff", borderBottom:"1px solid #e5e7eb", padding:"10px 16px" }}>
        <div style={{ display:"flex", gap:8, alignItems:"center", position:"relative" }}>
          <div style={{ flex:1, position:"relative" }}>
            <input value={inp}
              onChange={e => {
                const v = e.target.value; setInp(v); setErr("")
                const q = v.toUpperCase().trim()
                if (q.length >= 1) { const s = searchStocks(q, 8); setSuggestions(s); setShowSugg(s.length>0) }
                else { setSuggestions([]); setShowSugg(false) }
              }}
              onKeyDown={e => { if(e.key==="Enter"){const u=inp.toUpperCase().trim();analyze(u);setShowSugg(false)} if(e.key==="Escape")setShowSugg(false) }}
              onBlur={() => setTimeout(()=>setShowSugg(false),200)}
              placeholder="Search NSE, NASDAQ, NYSE — RELIANCE, AAPL, NVDA..."
              style={{ width:"100%", border:`1px solid ${err?"#fca5a5":"#d1d5db"}`, borderRadius:8, padding:"10px 14px", fontSize:13, background:"#f9fafb" }}
            />
            {showSugg && suggestions.length>0 && (
              <div style={{ position:"absolute", top:"calc(100% + 4px)", left:0, right:0, background:"#fff", border:"1px solid #e5e7eb", borderRadius:10, boxShadow:"0 8px 30px rgba(0,0,0,0.15)", zIndex:600, overflow:"hidden" }}>
                {suggestions.map(s => (
                  <div key={s.sym} onMouseDown={() => { setInp(s.sym); analyze(s.sym); setShowSugg(false) }}
                    style={{ padding:"10px 14px", cursor:"pointer", borderBottom:"1px solid #f3f4f6", display:"flex", alignItems:"center", gap:10 }}
                    onMouseEnter={e=>(e.currentTarget.style.background="#f9fafb")}
                    onMouseLeave={e=>(e.currentTarget.style.background="#fff")}>
                    <div style={{ fontSize:12, fontWeight:700, color:"#1d4ed8", minWidth:100 }}>{s.sym}</div>
                    <div style={{ fontSize:12, color:"#6b7280" }}>{s.name}</div>
                    <div style={{ marginLeft:"auto", fontSize:10, color:"#9ca3af", background:"#f3f4f6", padding:"1px 6px", borderRadius:4 }}>{s.exchange}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => { const u=inp.toUpperCase().trim(); analyze(u) }}
            style={{ padding:"10px 22px", background:"#0f172a", border:"none", borderRadius:8, color:"#fff", fontWeight:600, fontSize:13, cursor:"pointer", whiteSpace:"nowrap", flexShrink:0 }}>
            Analyse →
          </button>
        </div>
        {err && <div style={{ marginTop:8, padding:"8px 12px", background:"#fef2f2", border:"1px solid #fecaca", borderRadius:6, fontSize:11, color:"#dc2626" }}>⚠ {err}</div>}
      </div>

      {loading && <Loader text={`Analysing ${sym}...`} />}

      {D && !loading && (
        <div className="fade">
          {/* HERO */}
          <div style={{ background:"#fff", borderBottom:"1px solid #e5e7eb", padding:"14px 16px" }}>
            <div style={{ display:"flex", alignItems:"flex-start", gap:12, flexWrap:"wrap", marginBottom:10 }}>
              <div>
                <div style={{ fontSize:26, fontWeight:800, color:"#111827", letterSpacing:"-0.5px" }}>{sym}</div>
                <div style={{ fontSize:9, color:"#9ca3af", marginTop:2 }}>{meta?.name} · {meta?.exchange} · {meta?.sector} · MCap ₹{(D.mcap/100).toFixed(0)}Cr</div>
                {D.source==="simulated" && <div style={{ fontSize:8, color:"#d97706", marginTop:2 }}>⚠ Simulated data</div>}
              </div>

              {/* PRICE */}
              <div style={{ background:"#f9fafb", border:"1px solid #e5e7eb", borderRadius:10, padding:"10px 16px", minWidth:160 }}>
                <div style={{ fontSize:8, color:"#9ca3af", letterSpacing:"0.8px", textTransform:"uppercase", marginBottom:3 }}>
                  {D.source==="rapidapi"?"✅ Live Price":"Simulated Price"}
                </div>
                <div style={{ fontSize:24, fontWeight:800, color:"#1d4ed8" }}>
                  {meta?.exchange==="NSE"||meta?.exchange==="BSE"?"₹":"$"}{D.cmp.toLocaleString("en-IN",{maximumFractionDigits:2})}
                </div>
                <div style={{ fontSize:11, color:D.change>=0?"#16a34a":"#dc2626", marginTop:2 }}>
                  {D.change>=0?"+":""}{Number(D.change).toFixed(2)} ({Number(D.changePct).toFixed(2)}%)
                </div>
                <div style={{ fontSize:9, color:"#9ca3af", marginTop:2 }}>52W H:{D.week52h} L:{D.week52l}</div>
              </div>

              {/* TIER */}
              <div style={{ background:D.tierBg, border:`2px solid ${D.tierBorder}`, borderRadius:10, padding:"8px 16px", maxWidth:220 }}>
                <div style={{ fontSize:15, fontWeight:700, color:D.tierColor, marginBottom:3 }}>{D.tierLabel}</div>
                <div style={{ fontSize:11, color:"#6b7280", lineHeight:1.4 }}>{D.tierDesc}</div>
              </div>

              {/* VERDICT */}
              <div style={{ background:`${D.verdC}0f`, border:`2px solid ${D.verdC}`, borderRadius:10, padding:"8px 14px", textAlign:"center" }}>
                <div style={{ fontSize:8, color:"#9ca3af", textTransform:"uppercase", marginBottom:2 }}>Recommendation</div>
                <div style={{ fontSize:16, fontWeight:800, color:D.verdC }}>{D.verd}</div>
              </div>

              {/* BUY ZONE */}
              <div style={{ background:`${D.buyZoneColor}0f`, border:`2px solid ${D.buyZoneColor}`, borderRadius:10, padding:"8px 14px", textAlign:"center" }}>
                <div style={{ fontSize:8, color:"#9ca3af", textTransform:"uppercase", marginBottom:2 }}>Buy Zone</div>
                <div style={{ fontSize:13, fontWeight:700, color:D.buyZoneColor }}>{D.buyZoneLabel}</div>
                <div style={{ fontSize:18, fontWeight:800, color:D.buyZoneColor }}>{D.buyZone}/100</div>
              </div>

              <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                <div style={{ textAlign:"center" }}><Ring score={D.overall} size={68}/><div style={{ fontSize:8, color:"#9ca3af", marginTop:2 }}>OVERALL</div></div>
                <div style={{ textAlign:"center" }}><Ring score={D.mbScore} size={52}/><div style={{ fontSize:7, color:"#9ca3af", marginTop:2 }}>MULTIBAGGER</div></div>
              </div>
            </div>

            {/* SCORE ROW */}
            <div style={{ display:"flex", gap:6, overflowX:"auto", paddingBottom:4 }}>
              {[["Growth",D.gS,"25%"],["Quality",D.qS,"20%"],["Governance",D.govS,"20%"],["Valuation",D.valS,"15%"],["Technicals",D.techS,"10%"],["Ownership",D.ownS,"10%"]].map(([l,s,w]) => (
                <div key={l} style={{ flexShrink:0, background:"#f3f4f6", border:"1px solid #e5e7eb", borderRadius:8, padding:"6px 11px", minWidth:74, textAlign:"center" }}>
                  <div style={{ fontSize:7, color:"#9ca3af", textTransform:"uppercase", marginBottom:2 }}>{l} <span style={{ color:"#d1d5db" }}>{w}</span></div>
                  <div style={{ fontSize:17, fontWeight:800, color:Number(s)>=8?"#16a34a":Number(s)>=6?"#1d4ed8":Number(s)>=4?"#d97706":"#dc2626" }}>{s}<span style={{ fontSize:9, color:"#9ca3af" }}>/10</span></div>
                </div>
              ))}
            </div>
          </div>

          {/* PAGE TABS */}
          <div style={{ background:"#fff", borderBottom:"1px solid #e5e7eb", display:"flex", padding:"0 12px", overflowX:"auto" }}>
            {[["overview","Overview"],["fundamentals","Fundamentals"],["technicals","Technicals"],["ai","Frameworks & AI"]].map(([id,label]) => (
              <button key={id} onClick={() => setPage(id)} style={{ padding:"11px 16px", background:"transparent", border:"none", borderBottom:`3px solid ${page===id?"#1d4ed8":"transparent"}`, color:page===id?"#1d4ed8":"#6b7280", fontWeight:page===id?600:400, fontSize:13, cursor:"pointer", whiteSpace:"nowrap" }}>{label}</button>
            ))}
          </div>

          <div style={{ padding:"14px 16px", maxWidth:940, margin:"0 auto" }} className="fade">

            {/* OVERVIEW */}
            {page==="overview" && (
              <>
                {/* BIG PICTURE */}
                <div style={{ background:"linear-gradient(135deg,#0f172a,#1e3a5f)", borderRadius:14, padding:"18px 20px", marginBottom:14, color:"#f8fafc" }}>
                  <div style={{ fontSize:8, color:"#4b5563", letterSpacing:"2px", textTransform:"uppercase", marginBottom:6 }}>Big Picture — AACapital</div>
                  <div style={{ fontSize:13, lineHeight:1.8, color:"#cbd5e1" }}>
                    <strong style={{ color:"#f8fafc" }}>{sym}</strong> — <strong style={{ color:D.tierColor }}>{D.tierLabel}</strong> · Score <strong style={{ color:D.verdC }}>{D.overall}/100</strong> · Multibagger <strong style={{ color:"#a78bfa" }}>{D.mbScore}/100</strong>. Buy Zone: <strong style={{ color:D.buyZoneColor }}>{D.buyZoneLabel} ({D.buyZone}/100)</strong>. Rev CAGR <strong style={{ color:"#34d399" }}>{D.rev3}%</strong> · PAT CAGR <strong style={{ color:"#34d399" }}>{D.pat3}%</strong> · ROCE <strong style={{ color:D.roce>=20?"#34d399":"#fbbf24" }}>{D.roce}%</strong>.
                  </div>
                  <div style={{ display:"flex", gap:10, marginTop:14, flexWrap:"wrap" }}>
                    {[{l:"Stop Loss",v:`₹${D.sl}`,c:"#f87171"},{l:"Target 1",v:`₹${D.t1}`,c:"#34d399"},{l:"Target 2",v:`₹${D.t2}`,c:"#6ee7b7"},{l:"Target 3",v:`₹${D.t3}`,c:"#a7f3d0"}].map(s => (
                      <div key={s.l} style={{ background:"rgba(255,255,255,0.07)", borderRadius:8, padding:"7px 12px" }}>
                        <div style={{ fontSize:7, color:"#4b5563", letterSpacing:"1px", textTransform:"uppercase", marginBottom:2 }}>{s.l}</div>
                        <div style={{ fontSize:13, fontWeight:700, color:s.c }}>{s.v}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* ANALYST ROW hidden — analyst consensus/targets are synthetic (no real source) */}
                {false && (
                <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:14, marginBottom:14 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:14, flexWrap:"wrap" }}>
                    <div>
                      <div style={{ fontSize:8, color:"#9ca3af", textTransform:"uppercase", marginBottom:3 }}>{D.analystCount} Analysts · Consensus</div>
                      <div style={{ fontSize:20, fontWeight:800, color:"#16a34a" }}>{meta?.exchange==="NSE"?"₹":"$"}{D.cT.toLocaleString("en-IN")}</div>
                      <div style={{ fontSize:11, color:"#16a34a" }}>+{(((D.cT-D.cmp)/D.cmp)*100).toFixed(0)}% upside</div>
                    </div>
                    {[{l:"🐂 Bull",v:D.bullT,c:"#16a34a"},{l:"Base",v:D.cT,c:"#1d4ed8"},{l:"🐻 Bear",v:D.bearT,c:"#dc2626"}].map(s => (
                      <div key={s.l} style={{ textAlign:"center", padding:"4px 10px", background:"#f9fafb", border:"1px solid #e5e7eb", borderRadius:6 }}>
                        <div style={{ fontSize:8, color:"#9ca3af", marginBottom:2 }}>{s.l}</div>
                        <div style={{ fontSize:13, fontWeight:700, color:s.c }}>{meta?.exchange==="NSE"?"₹":"$"}{s.v.toLocaleString("en-IN")}</div>
                      </div>
                    ))}
                    <div style={{ minWidth:160 }}>
                      <div style={{ fontSize:8, color:"#9ca3af", marginBottom:4 }}>Analyst Ratings</div>
                      <div style={{ display:"flex", height:10, borderRadius:5, overflow:"hidden", marginBottom:3 }}>
                        <div style={{ width:`${D.buyPct}%`, background:"#16a34a" }}/><div style={{ width:`${D.holdPct}%`, background:"#d97706" }}/><div style={{ width:`${D.sellPct}%`, background:"#dc2626" }}/>
                      </div>
                      <div style={{ display:"flex", gap:8, fontSize:10 }}>
                        <span style={{ color:"#16a34a" }}>Buy {D.buyPct}%</span>
                        <span style={{ color:"#d97706" }}>Hold {D.holdPct}%</span>
                        <span style={{ color:"#dc2626" }}>Sell {D.sellPct}%</span>
                      </div>
                    </div>
                  </div>
                </div>
                )}

                {/* INSTITUTION + DELIVERY */}
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:14 }}>
                  <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:14 }}>
                    <div style={{ fontSize:8, color:"#9ca3af", letterSpacing:"1px", textTransform:"uppercase", marginBottom:12 }}>Institutional Activity — 8 Quarters</div>
                    {[{l:"FII",d:D.fii,c:D.fii[7]>D.fii[0]?"#16a34a":"#dc2626"},{l:"DII",d:D.dii,c:D.dii[7]>D.dii[0]?"#1d4ed8":"#dc2626"}].map(s => (
                      <div key={s.l} style={{ marginBottom:12 }}>
                        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:5 }}>
                          <span style={{ fontSize:10, fontWeight:600, color:"#374151" }}>{s.l}</span>
                          <span style={{ fontSize:13, fontWeight:800, color:s.c }}>{s.d[7].toFixed(1)}% {s.d[7]>s.d[0]?"▲":"▼"}</span>
                        </div>
                        <Spark data={s.d} color={s.c} h={44}/>
                      </div>
                    ))}
                  </div>
                  <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:14 }}>
                    <div style={{ fontSize:8, color:"#9ca3af", letterSpacing:"1px", textTransform:"uppercase", marginBottom:12 }}>Quarterly Revenue (₹Cr)</div>
                    <div style={{ fontSize:24, fontWeight:800, color:"#3b82f6", marginBottom:8 }}>{Number(D.rev[7]).toFixed(0)}</div>
                    <Spark data={D.rev} color="#3b82f6" h={60}/>
                    <div style={{ display:"flex", justifyContent:"space-between", marginTop:4 }}>
                      <span style={{ fontSize:7, color:"#d1d5db" }}>{D.qs[0]}</span>
                      <span style={{ fontSize:7, color:"#6b7280", fontWeight:600 }}>{D.qs[7]}</span>
                    </div>
                  </div>
                </div>

                {/* AI MEMO */}
                <div style={{ textAlign:"center" }}>
                  {!memo && !memoLoad && (
                    <button onClick={genMemo} style={{ padding:"13px 28px", background:"linear-gradient(135deg,#1d4ed8,#0d9488)", border:"none", borderRadius:10, color:"#fff", fontWeight:700, fontSize:14, cursor:"pointer", boxShadow:"0 4px 20px rgba(29,78,216,0.25)" }}>
                      ⚡ Generate AI Fund Manager Report
                    </button>
                  )}
                  {memoLoad && <Loader text="Generating institutional memo..." />}
                  {memo && (
                    <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:14, padding:18, textAlign:"left" }} className="fade">
                      <div style={{ fontSize:17, fontWeight:800, color:"#111827", marginBottom:6 }}>"{memo.headline}"</div>
                      <div style={{ fontSize:13, color:"#6b7280", lineHeight:1.7, marginBottom:12 }}>{memo.business}</div>
                      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12 }}>
                        <div style={{ background:"#f0fdf4", border:"1px solid #bbf7d0", borderRadius:10, padding:12 }}>
                          <div style={{ fontSize:9, color:"#16a34a", textTransform:"uppercase", marginBottom:8 }}>Bull Case</div>
                          {memo.bull_case?.map((b:string,i:number) => <div key={i} style={{ fontSize:11, color:"#374151", marginBottom:5, lineHeight:1.5 }}>✓ {b}</div>)}
                        </div>
                        <div style={{ background:"#fef2f2", border:"1px solid #fecaca", borderRadius:10, padding:12 }}>
                          <div style={{ fontSize:9, color:"#dc2626", textTransform:"uppercase", marginBottom:8 }}>Bear Case</div>
                          {memo.bear_case?.map((b:string,i:number) => <div key={i} style={{ fontSize:11, color:"#374151", marginBottom:5, lineHeight:1.5 }}>✗ {b}</div>)}
                        </div>
                      </div>
                      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(115px,1fr))", gap:8, marginBottom:10 }}>
                        {[{l:"Recommendation",v:memo.recommendation,c:memo.recommendation?.includes("BUY")?"#16a34a":"#d97706"},{l:"Target",v:memo.target,c:"#16a34a"},{l:"Stop Loss",v:memo.stop,c:"#dc2626"},{l:"Horizon",v:memo.horizon,c:"#1d4ed8"},{l:"CAGR",v:memo.expected_cagr,c:"#059669"},{l:"Position",v:memo.position,c:"#0369a1"}].map(c => (
                          <div key={c.l} style={{ background:"#f3f4f6", border:"1px solid #e5e7eb", borderRadius:8, padding:"10px 12px" }}>
                            <div style={{ fontSize:8, color:"#9ca3af", textTransform:"uppercase", marginBottom:3 }}>{c.l}</div>
                            <div style={{ fontSize:12, fontWeight:700, color:c.c }}>{c.v}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ background:"linear-gradient(135deg,#eff6ff,#f0fdf4)", border:"1px solid #bfdbfe", borderRadius:10, padding:12 }}>
                        <div style={{ fontSize:8, color:"#1d4ed8", textTransform:"uppercase", marginBottom:5 }}>Final Conviction</div>
                        <div style={{ fontSize:13, color:"#111827", lineHeight:1.65 }}>{memo.thesis}</div>
                      </div>
                      <button onClick={genMemo} style={{ marginTop:10, padding:"6px 14px", background:"transparent", border:"1px solid #e5e7eb", borderRadius:6, color:"#6b7280", fontSize:10, cursor:"pointer" }}>↻ Regenerate</button>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* FUNDAMENTALS */}
            {page==="fundamentals" && (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))", gap:8 }}>
                {[
                  {label:"P/E Ratio",value:`${D.pe}x`,color:D.pe<25?"#16a34a":D.pe<50?"#d97706":"#dc2626",sub:D.pe<25?"Cheap":D.pe<50?"Fair":"Expensive",tip:"Price to Earnings — what you pay per ₹1 of profit"},
                  {label:"P/B Ratio",value:`${D.pb}x`,color:D.pb<3?"#16a34a":D.pb<6?"#d97706":"#dc2626",sub:"Price to Book",tip:"Graham's favourite metric. Below 1.5x book = deep value"},
                  {label:"ROCE",value:`${D.roce}%`,color:D.roce>=20?"#16a34a":D.roce>=15?"#d97706":"#dc2626",sub:D.roce>=20?"Strong ✓":"Moderate",tip:"Return on Capital Employed — single most important metric"},
                  {label:"ROE",value:`${D.roe}%`,color:D.roe>=20?"#16a34a":D.roe>=15?"#d97706":"#dc2626",sub:"Return on Equity",tip:"ROE above 20% = excellent capital efficiency"},
                  {label:"Rev CAGR 3Y",value:`${D.rev3}%`,color:D.rev3>=20?"#16a34a":D.rev3>=15?"#d97706":"#dc2626",sub:"3Y Revenue Growth",tip:"3-year revenue CAGR. Above 20% = high growth"},
                  {label:"PAT CAGR 3Y",value:`${D.pat3}%`,color:D.pat3>=20?"#16a34a":D.pat3>=15?"#d97706":"#dc2626",sub:"3Y Profit Growth",tip:"Profit CAGR must grow at least as fast as revenue"},
                  {label:"Debt/Equity",value:`${D.debt}x`,color:D.debt<0.5?"#16a34a":D.debt<1?"#d97706":"#dc2626",sub:D.debt<0.5?"Low debt":"Moderate",tip:"Below 0.5x = conservative. Above 1.5x = risky"},
                  {label:"Promoter",value:`${D.promoter.toFixed(1)}%`,color:D.promoter>=60?"#16a34a":D.promoter>=50?"#d97706":"#dc2626",sub:"Holding",tip:"Above 60% = high conviction owner-operator"},
                  {label:"Pledge %",value:`${D.pledge.toFixed(1)}%`,color:D.pledge<2?"#16a34a":D.pledge<5?"#d97706":"#dc2626",sub:D.pledge<2?"Clean":"Watch",tip:"Above 15% = hard avoid. Margin-call spiral risk"},
                  {label:"Piotroski F",value:`${D.piotroski}/9`,color:D.piotroski>=7?"#16a34a":D.piotroski>=5?"#d97706":"#dc2626",sub:D.piotroski>=7?"Strong":"Moderate",tip:"9-point financial health scorecard. 8-9 = excellent"},
                  {label:"Op. Margin",value:`${D.opMarg}%`,color:D.opMarg>=20?"#16a34a":D.opMarg>=12?"#d97706":"#dc2626",sub:D.opMarg>=20?"Wide moat":"Moderate",tip:"Above 20% signals pricing power and wide moat"},
                ].map(s => <StatCard key={s.label} {...s}/>)}
              </div>
            )}

            {/* TECHNICALS */}
            {page==="technicals" && (
              <>
                <div style={{ marginBottom:14 }}>
                  <div style={{ fontSize:9, color:"#9ca3af", letterSpacing:"1px", textTransform:"uppercase", marginBottom:8 }}>Live Chart — {meta?.exchange}:{sym} · EMA 20/50/200 · RSI · MACD</div>
                  <div style={{ width:"100%", height:480, borderRadius:10, overflow:"hidden", border:"1px solid #e5e7eb" }}>
                    <iframe
                      src={`https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=${meta?.exchange}%3A${sym}&interval=D&hidesidetoolbar=0&hidetoptoolbar=0&studies=STD%3BEMA%40tv-basicstudies%1FSTD%3BEMA%40tv-basicstudies%1FSTD%3BEMA%40tv-basicstudies%1FSTD%3BRSI%40tv-basicstudies%1FSTD%3BMACD%40tv-basicstudies&theme=light&style=1&timezone=Asia%2FKolkata&locale=en`}
                      style={{ width:"100%", height:"100%", border:"none" }}
                      title={`${sym} Chart`}
                      allow="fullscreen"
                    />
                  </div>
                </div>
                <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))", gap:8 }}>
                  {[
                    {label:"RSI (14)",value:D.rsi.toFixed(0),color:D.rsi>70?"#dc2626":D.rsi<30?"#dc2626":"#16a34a",sub:D.rsi>70?"Overbought":D.rsi<30?"Oversold":"Healthy Zone"},
                    {label:"MACD",value:D.trend==="Bullish"?"Bullish":"Bearish",color:D.trend==="Bullish"?"#16a34a":"#dc2626",sub:"Signal Line"},
                    {label:"20 EMA",value:`${meta?.exchange==="NSE"?"₹":"$"}${D.ema20}`,color:D.cmp>D.ema20?"#16a34a":"#dc2626",sub:D.cmp>D.ema20?"Above ✓":"Below ✗"},
                    {label:"50 EMA",value:`${meta?.exchange==="NSE"?"₹":"$"}${D.ema50}`,color:D.cmp>D.ema50?"#16a34a":"#dc2626",sub:D.cmp>D.ema50?"Bull Structure":"Bear"},
                    {label:"200 EMA",value:`${meta?.exchange==="NSE"?"₹":"$"}${D.ema200}`,color:D.cmp>D.ema200?"#16a34a":"#dc2626",sub:D.cmp>D.ema200?"Bull Market ✓":"Bear Zone ✗"},
                    {label:"Trend",value:D.trend,color:D.trend==="Bullish"?"#16a34a":"#dc2626",sub:D.cmp>D.ema200?"Above 200 EMA":"Below 200 EMA"},
                    {label:"Stop Loss",value:`${meta?.exchange==="NSE"?"₹":"$"}${D.sl}`,color:"#dc2626",sub:`−${(((D.cmp-D.sl)/D.cmp)*100).toFixed(1)}%`},
                    {label:"Target 1",value:`${meta?.exchange==="NSE"?"₹":"$"}${D.t1}`,color:"#16a34a",sub:`+${(((D.t1-D.cmp)/D.cmp)*100).toFixed(0)}%`},
                    {label:"Target 2",value:`${meta?.exchange==="NSE"?"₹":"$"}${D.t2}`,color:"#059669",sub:`+${(((D.t2-D.cmp)/D.cmp)*100).toFixed(0)}%`},
                  ].map(s => <StatCard key={s.label} {...s}/>)}
                </div>
              </>
            )}

            {/* AI FRAMEWORKS */}
            {page==="ai" && (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))", gap:8 }}>
                {[
                  {n:"Buffett",e:"🏦",c:"#1d4ed8",score:Math.min(100,Math.round((D.roce>=20?25:15)+(D.roe>=20?20:10)+(D.debt<0.5?20:10)+(D.promoter>=55?20:10)+(D.pledge<5?15:5))),min:70},
                  {n:"Lynch GARP",e:"📈",c:"#059669",score:Math.min(100,Math.round((D.rev3>=20?20:12)+(D.pat3>=20?20:12)+(D.mcap<20000?20:10)+(D.pat3>D.rev3*0.8?15:5)+(25))),min:65},
                  {n:"Graham",e:"📖",c:"#7c3aed",score:Math.min(100,Math.round((D.pe<20?25:D.pe<35?15:5)+(D.pb<2?25:15)+(D.debt<0.5?20:10)+(D.piotroski>=7?20:10))),min:60},
                  {n:"Raamdeo QGLP",e:"🇮🇳",c:"#dc2626",score:Math.min(100,Math.round((D.qS>=8?20:12)+(D.gS>=8?20:12)+(D.overall>=70?20:10)+(D.pe<35?20:10)+(D.roce>=20?20:10))),min:70},
                  {n:"Kutumbarao",e:"🏛️",c:"#92400e",score:Math.min(100,Math.round((D.roce>=15?20:10)+(D.promoter>=55?20:10)+(D.debt<0.8?20:10)+(D.roe>=18?20:10)+(D.rev3>=15?20:10))),min:68},
                  {n:"Mayer 100x",e:"🚀",c:"#7c3aed",score:Math.min(100,Math.round((D.promoter>=55?20:10)+(D.roe>=20?20:10)+(D.roce>=20?15:8)+(D.mcap<20000?15:5)+(D.rev3>=20?15:8)+(D.pat3>=20?15:8))),min:65},
                ].map(g => {
                  const passes = g.score >= g.min
                  return (
                    <div key={g.n} style={{ background:passes?`${g.c}08`:"#f9fafb", border:`2px solid ${passes?g.c+"30":"#e5e7eb"}`, borderRadius:10, padding:"12px 14px" }}>
                      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6 }}>
                        <span style={{ fontSize:11, fontWeight:700, color:"#111827" }}>{g.e} {g.n}</span>
                        <span style={{ fontSize:18, fontWeight:800, color:passes?g.c:"#9ca3af" }}>{g.score}</span>
                      </div>
                      <div style={{ height:5, background:"#e5e7eb", borderRadius:3, overflow:"hidden", marginBottom:5 }}>
                        <div style={{ width:`${g.score}%`, height:"100%", background:g.c, borderRadius:3 }}/>
                      </div>
                      <div style={{ display:"flex", justifyContent:"space-between" }}>
                        <span style={{ fontSize:8, color:"#9ca3af" }}>min: {g.min}</span>
                        <span style={{ padding:"2px 6px", borderRadius:4, fontSize:8, background:passes?`${g.c}15`:"#f3f4f6", color:passes?g.c:"#9ca3af" }}>{passes?"PASSES":"FAILS"}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {!D && !loading && (
        <div style={{ textAlign:"center", padding:"60px 20px" }}>
          <div style={{ fontSize:48, marginBottom:16 }}>📊</div>
          <div style={{ fontWeight:700, fontSize:18, color:"#374151", marginBottom:8 }}>Search any stock to begin</div>
          <div style={{ fontSize:11, color:"#9ca3af", lineHeight:1.7 }}>
            NSE/BSE: RELIANCE, HDFCBANK, POLYCAB, BEL<br/>
            NASDAQ: AAPL, NVDA, MSFT, TSLA<br/>
            NYSE: JPM, V, MA, BRK-B
          </div>
        </div>
      )}
    </div>
  )
}

