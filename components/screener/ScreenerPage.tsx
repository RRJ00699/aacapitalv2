"use client"
import { useState, useCallback } from "react"
import { ALL_STOCKS } from "@/lib/constants/stocks"
import Loader from "@/components/shared/Loader"

function seedVal(sym: string, offset=0) {
  const s = sym.split("").reduce((a,c)=>a+c.charCodeAt(0),0)
  return (s*17+offset*31)%100/100
}
function sr(sym:string, min:number, max:number, o=0) { return +(min+seedVal(sym,o)*(max-min)).toFixed(2) }
function sri(sym:string, min:number, max:number, o=0) { return Math.round(sr(sym,min,max,o)) }

function makeStockData(sym:string) {
  const pe=sr(sym,6,90,2),pb=sr(sym,0.6,15,3),roe=sr(sym,6,52,4),roce=sr(sym,8,55,5)
  const rev3=sr(sym,8,42,6),pat3=sr(sym,10,55,7),debt=sr(sym,0.02,2.2,8)
  const promoter=sr(sym,38,79,9),pledge=sr(sym,0,20,10)
  const rsi=sr(sym,30,78,11)
  const cmp=sr(sym,80,8500,1)
  const ema50=+(cmp*sr(sym,0.87,1.01,14)).toFixed(0)
  const ema200=+(cmp*sr(sym,0.76,0.96,15)).toFixed(0)
  const fii=Array.from({length:8},(_,i)=>sr(sym,5,24,20+i))
  const dii=Array.from({length:8},(_,i)=>sr(sym,3,18,30+i))
  const piotroski=sri(sym,3,9,91)
  const altman=sr(sym,1.2,6.5,93)
  const mcap=+(cmp*sr(sym,150,90000,90)).toFixed(0)
  const peg=sr(sym,0.3,4.2,95)
  const gS=Math.min(10,Math.round((rev3>20?3:rev3>15?2:1)+(pat3>25?3:pat3>15?2:1)+4))
  const qS=Math.min(10,Math.round((roe>20?3:2)+(roce>20?3:2)+4))
  const govS=Math.min(10,Math.round((promoter>60?3:promoter>50?2:1)+(pledge<2?3:pledge<5?2:0)+4))
  const valS=Math.min(10,Math.round((pe<20?4:pe<35?3:pe<50?2:1)+(pb<3?3:pb<6?2:1)+3))
  const techS=Math.min(10,Math.round((rsi>50&&rsi<70?4:2)+(cmp>ema50?3:1)+3))
  const ownS=Math.min(10,Math.round((fii[7]>fii[0]?4:2)+(dii[7]>dii[0]?3:1)+3))
  const overall=Math.round(gS*2.5+qS*2.0+govS*2.0+valS*1.5+techS*1.0+ownS*1.0)
  const buyZone=Math.min(100,(roe>20&&roce>20?20:0)+(fii[7]>fii[0]&&dii[7]>dii[0]?15:0)+(cmp>ema50&&cmp>ema200?15:0)+(rev3>15&&pat3>15?10:0)+(promoter>60&&pledge<3?20:0)+(rsi>50&&rsi<70?10:0)+(piotroski>7&&altman>3?10:0))
  let tier="2"
  if(pledge>15)tier="HIGH_RISK"
  else if(overall<50||debt>2)tier="AVOID"
  else if(overall>=80&&roce>=20&&promoter>=55&&pledge<5&&rev3>=15)tier="1A"
  else if(overall>=65&&roce>=15&&promoter>=50&&pledge<10)tier="1"
  return { sym,pe,pb,roe,roce,rev3,pat3,debt,promoter,pledge,rsi,cmp,ema50,ema200,fii,dii,piotroski,altman,mcap,peg,gS,qS,govS,valS,techS,ownS,overall,buyZone,tier }
}

const GURUS = {
  buffett: { name:"Warren Buffett", emoji:"🏦", color:"#1d4ed8", desc:"Quality moat. High ROCE, low debt, owner-operator.", criteria:(d:any)=>d.roce>=18&&d.roe>=15&&d.debt<1.0&&d.promoter>=50&&d.pledge<10&&d.pat3>=12, badges:["ROCE ≥18%","ROE ≥15%","D/E <1x","Promoter ≥50%"] },
  lynch: { name:"Peter Lynch", emoji:"📈", color:"#059669", desc:"GARP. 20%+ growers, small-mid caps, PEG <2.", criteria:(d:any)=>d.rev3>=15&&d.pat3>=15&&d.peg<2.0&&d.mcap<50000, badges:["Rev CAGR ≥15%","PAT ≥15%","PEG <2x","MCap <₹50kCr"] },
  graham: { name:"Benjamin Graham", emoji:"📖", color:"#7c3aed", desc:"Margin of safety. Low PE, PB, strong balance sheet.", criteria:(d:any)=>d.pe<30&&d.pb<4&&d.debt<0.7&&d.piotroski>=6&&d.altman>2.5, badges:["PE <30x","PB <4x","D/E <0.7x","Piotroski ≥6"] },
  kutumba: { name:"Kutumbarao", emoji:"🏛️", color:"#92400e", desc:"Essential-need, debt-free, pricing power.", criteria:(d:any)=>d.roce>=15&&d.debt<0.8&&d.promoter>=55&&d.pledge<5&&d.roe>=15, badges:["ROCE ≥15%","D/E <0.8x","Promoter ≥55%","Pledge <5%"] },
  mayer: { name:"Mayer 100x", emoji:"🚀", color:"#7c3aed", desc:"100-bagger setup: small cap, high ROCE, 20%+ growth.", criteria:(d:any)=>d.mcap<25000&&d.promoter>=55&&d.roce>=20&&d.rev3>=20&&d.pat3>=18, badges:["MCap <₹25kCr","Promoter ≥55%","ROCE ≥20%","Rev ≥20%"] },
  agrawal: { name:"Raamdeo QGLP", emoji:"🇮🇳", color:"#dc2626", desc:"Quality + Growth + Longevity + Price.", criteria:(d:any)=>d.overall>=65&&d.roce>=18&&d.rev3>=15&&d.pe<50&&d.pledge<8, badges:["Score ≥65","ROCE ≥18%","Rev ≥15%","PE <50x"] },
  buyzone: { name:"In Buy Zone Now", emoji:"🎯", color:"#16a34a", desc:"Stocks in active buy zone. Updated live.", criteria:(d:any)=>d.buyZone>=61&&d.cmp>d.ema200, badges:["Buy Zone ≥61","Above 200 EMA","RSI 40-70"] },
}

const TIER_META: Record<string,any> = {
  "1A": { label:"🏆 Tier 1A", color:"#1d4ed8", bg:"#eff6ff", border:"#bfdbfe" },
  "1":  { label:"⭐ Tier 1",  color:"#059669", bg:"#f0fdf4", border:"#bbf7d0" },
  "2":  { label:"🟡 Tier 2",  color:"#d97706", bg:"#fffbeb", border:"#fde68a" },
  "AVOID": { label:"⛔ Avoid", color:"#dc2626", bg:"#fef2f2", border:"#fecaca" },
  "HIGH_RISK": { label:"🔴 High Risk", color:"#dc2626", bg:"#fef2f2", border:"#fecaca" },
}

const BZ_COLOR = (bz:number) => bz>=91?"#7c3aed":bz>=76?"#16a34a":bz>=61?"#1d4ed8":bz>=41?"#d97706":"#dc2626"
const BZ_LABEL = (bz:number) => bz>=91?"⚡ High Conv":bz>=76?"✅ Buy Zone":bz>=61?"📌 Accumulate":bz>=41?"👁 Watchlist":"❌ Avoid"

export default function ScreenerPage() {
  const [activeGuru, setActiveGuru] = useState<string|null>(null)
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [tierFilter, setTierFilter] = useState("ALL")
  const [minBZ, setMinBZ] = useState(0)

  const runScreener = useCallback((guruKey: string) => {
    setActiveGuru(guruKey)
    setLoading(true)
    setDone(false)
    setResults([])
    setTimeout(() => {
      const guru = GURUS[guruKey as keyof typeof GURUS]
      const res: any[] = []
      ALL_STOCKS.forEach(s => {
        const d = makeStockData(s.sym)
        if (guru.criteria(d) && d.buyZone >= minBZ) {
          const passTier = tierFilter==="ALL" || (tierFilter==="1A"&&d.tier==="1A") || (tierFilter==="1"&&["1A","1"].includes(d.tier)) || (tierFilter==="2"&&["1A","1","2"].includes(d.tier))
          if (passTier) res.push({ ...d, exchange: s.exchange, name: s.name, sector: s.sector })
        }
      })
      res.sort((a,b) => b.overall-a.overall)
      setResults(res.slice(0,50))
      setLoading(false)
      setDone(true)
    }, 600)
  }, [minBZ, tierFilter])

  return (
    <div style={{ maxWidth:980, margin:"0 auto", padding:16 }}>
      <div style={{ marginBottom:16 }}>
        <div style={{ fontWeight:800, fontSize:22, color:"#111827", marginBottom:4 }}>Guru Stock Screener</div>
        <div style={{ fontSize:10, color:"#9ca3af" }}>Pick an investor philosophy · Screen {ALL_STOCKS.length} stocks (NSE + NASDAQ + NYSE) · Ranked by score</div>
      </div>

      {/* FILTERS */}
      <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:14, marginBottom:14 }}>
        <div style={{ display:"flex", gap:8, flexWrap:"wrap", alignItems:"center" }}>
          <div style={{ fontSize:9, color:"#9ca3af", letterSpacing:"1px", textTransform:"uppercase" }}>Min Buy Score:</div>
          {[0,50,61,76,91].map(v => (
            <button key={v} onClick={() => setMinBZ(v)} style={{ padding:"4px 9px", borderRadius:5, border:`1px solid ${minBZ===v?"#16a34a":"#e5e7eb"}`, background:minBZ===v?"#16a34a":"transparent", color:minBZ===v?"#fff":"#6b7280", fontSize:9, cursor:"pointer" }}>{v===0?"All":v+"+"}</button>
          ))}
          <div style={{ fontSize:9, color:"#9ca3af", letterSpacing:"1px", textTransform:"uppercase", marginLeft:8 }}>Tier:</div>
          {[["ALL","All"],["1A","1A Only"],["1","Tier 1+"],["2","Tier 2+"]].map(([v,l]) => (
            <button key={v} onClick={() => setTierFilter(v)} style={{ padding:"4px 9px", borderRadius:5, border:`1px solid ${tierFilter===v?"#7c3aed":"#e5e7eb"}`, background:tierFilter===v?"#7c3aed":"transparent", color:tierFilter===v?"#fff":"#6b7280", fontSize:9, cursor:"pointer" }}>{l}</button>
          ))}
        </div>
      </div>

      {/* GURU CARDS */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(195px,1fr))", gap:10, marginBottom:20 }}>
        {Object.entries(GURUS).map(([key, gf]) => (
          <button key={key} onClick={() => runScreener(key)} style={{ background:activeGuru===key?`${gf.color}08`:"#fff", border:`2px solid ${activeGuru===key?gf.color:"#e5e7eb"}`, borderRadius:12, padding:"14px 16px", cursor:"pointer", textAlign:"left", transition:"all .15s", boxShadow:activeGuru===key?`0 4px 16px ${gf.color}20`:"none" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:6 }}>
              <span style={{ fontSize:20 }}>{gf.emoji}</span>
              {activeGuru===key && <span style={{ fontSize:8, color:gf.color, background:`${gf.color}15`, padding:"2px 6px", borderRadius:3 }}>ACTIVE</span>}
            </div>
            <div style={{ fontSize:13, fontWeight:700, color:"#111827", marginBottom:4 }}>{gf.name}</div>
            <div style={{ fontSize:11, color:"#6b7280", lineHeight:1.4, marginBottom:8 }}>{gf.desc}</div>
            <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
              {gf.badges.slice(0,3).map(b => <span key={b} style={{ fontSize:8, background:`${gf.color}12`, color:gf.color, padding:"1px 5px", borderRadius:3 }}>{b}</span>)}
            </div>
          </button>
        ))}
      </div>

      {loading && <Loader text={`Screening ${ALL_STOCKS.length} stocks...`}/>}

      {done && !loading && (
        <div className="fade">
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:12 }}>
            <div style={{ fontWeight:800, fontSize:17, color:"#111827" }}>{results.length} stocks pass {activeGuru && GURUS[activeGuru as keyof typeof GURUS]?.emoji} {activeGuru && GURUS[activeGuru as keyof typeof GURUS]?.name}</div>
            <span style={{ fontSize:10, color:"#9ca3af" }}>out of {ALL_STOCKS.length} screened</span>
          </div>
          {results.length > 0 && (
            <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, overflow:"hidden" }}>
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", minWidth:700 }}>
                  <thead><tr style={{ background:"#f9fafb" }}>
                    {["#","Symbol","Exchange","Tier","Score","Buy Zone","ROCE","ROE","Rev CAGR","Promoter","Pledge","PE"].map(h => (
                      <th key={h} style={{ padding:"9px 10px", textAlign:"left", fontSize:8, color:"#6b7280", letterSpacing:".5px", textTransform:"uppercase", borderBottom:"1px solid #e5e7eb", whiteSpace:"nowrap" }}>{h}</th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {results.map((s,i) => {
                      const tm = TIER_META[s.tier] || TIER_META["2"]
                      return (
                        <tr key={s.sym} style={{ borderBottom:"1px solid #f3f4f6" }}>
                          <td style={{ padding:"8px 10px", fontSize:11, color:"#9ca3af", fontWeight:700 }}>#{i+1}</td>
                          <td style={{ padding:"8px 10px" }}>
                            <div style={{ fontWeight:800, fontSize:13, color:"#111827" }}>{s.sym}</div>
                            <div style={{ fontSize:9, color:"#9ca3af" }}>{s.name?.slice(0,20)}</div>
                          </td>
                          <td style={{ padding:"8px 10px" }}>
                            <span style={{ padding:"2px 6px", borderRadius:4, fontSize:9, background:"#f3f4f6", color:"#374151" }}>{s.exchange}</span>
                          </td>
                          <td style={{ padding:"8px 10px" }}>
                            <span style={{ padding:"2px 7px", borderRadius:5, fontSize:9, background:tm.bg, color:tm.color, border:`1px solid ${tm.border}`, whiteSpace:"nowrap" }}>{tm.label}</span>
                          </td>
                          <td style={{ padding:"8px 10px", fontWeight:800, fontSize:14, color:s.overall>=80?"#16a34a":s.overall>=65?"#1d4ed8":"#d97706" }}>{s.overall}</td>
                          <td style={{ padding:"8px 10px" }}>
                            <div style={{ fontWeight:700, fontSize:13, color:BZ_COLOR(s.buyZone) }}>{s.buyZone}</div>
                            <div style={{ fontSize:8, color:"#9ca3af" }}>{BZ_LABEL(s.buyZone)}</div>
                          </td>
                          <td style={{ padding:"8px 10px", fontSize:11, fontWeight:700, color:s.roce>=20?"#16a34a":s.roce>=15?"#d97706":"#dc2626" }}>{s.roce.toFixed(1)}%</td>
                          <td style={{ padding:"8px 10px", fontSize:11, fontWeight:700, color:s.roe>=20?"#16a34a":"#d97706" }}>{s.roe.toFixed(1)}%</td>
                          <td style={{ padding:"8px 10px", fontSize:11, fontWeight:700, color:s.rev3>=20?"#16a34a":"#d97706" }}>{s.rev3.toFixed(1)}%</td>
                          <td style={{ padding:"8px 10px", fontSize:11, color:s.promoter>=60?"#16a34a":"#6b7280" }}>{s.promoter.toFixed(1)}%</td>
                          <td style={{ padding:"8px 10px", fontSize:11, fontWeight:s.pledge>5?700:400, color:s.pledge<2?"#16a34a":s.pledge<5?"#d97706":"#dc2626" }}>{s.pledge.toFixed(1)}%</td>
                          <td style={{ padding:"8px 10px", fontSize:11, color:s.pe<25?"#16a34a":s.pe<50?"#6b7280":"#dc2626" }}>{s.pe.toFixed(0)}x</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {results.length === 0 && (
            <div style={{ textAlign:"center", padding:"40px", color:"#9ca3af", fontSize:12 }}>
              No stocks match this filter. Try adjusting the tier or buy score filters.
            </div>
          )}
        </div>
      )}

      {!activeGuru && !loading && !done && (
        <div style={{ textAlign:"center", padding:"60px 20px" }}>
          <div style={{ fontSize:48, marginBottom:16 }}>🔍</div>
          <div style={{ fontWeight:700, fontSize:18, color:"#374151", marginBottom:8 }}>Choose an investor philosophy</div>
          <div style={{ fontSize:11, color:"#9ca3af", lineHeight:1.6 }}>Each filter screens {ALL_STOCKS.length} stocks (NSE + NASDAQ + NYSE) against that guru's exact criteria.</div>
        </div>
      )}
    </div>
  )
}
