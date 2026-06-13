"use client"
import { useState, useEffect, useRef } from "react"
import LiveTape from "./LiveTape"
import PostListingMonitor from "./PostListingMonitor"

// ── Colour system ─────────────────────────────────────────────────────────
const C = {
  green:  "#15803d", greenBg:  "#f0fdf4", greenBd: "#bbf7d0",
  blue:   "#1d4ed8", blueBg:   "#eff6ff", blueBd:  "#bfdbfe",
  amber:  "#b45309", amberBg:  "#fefce8", amberBd: "#fde68a",
  red:    "#b91c1c", redBg:    "#fef2f2", redBd:   "#fecaca",
  purple: "#7c3aed", purpleBg: "#f5f3ff", purpleBd:"#e9d5ff",
  cyan:   "#0891b2", cyanBg:   "#ecfeff", cyanBd:  "#cffafe",
  gray:   "#6b7280", grayBg:   "#f9fafb", grayBd:  "#e5e7eb",
}
const scoreCol = (v:number) => v>=80?C.green:v>=65?C.blue:v>=50?C.amber:C.red
const scoreBg  = (v:number) => v>=80?C.greenBg:v>=65?C.blueBg:v>=50?C.amberBg:C.redBg
const pctStr   = (v:number,base:number) => { const p=base>0?((v-base)/base*100):0; return (p>=0?"+":"")+p.toFixed(1)+"%" }

const REC: Record<string,[string,string,string]> = {
  "Apply Aggressively":                        [C.green,  C.greenBg,  "APPLY AGGRESSIVELY"],
  "Apply — Long-Term Hold":                    [C.blue,   C.blueBg,   "APPLY — LONG-TERM HOLD"],
  "Apply — Listing Trade Only":                [C.cyan,   C.cyanBg,   "LISTING-DAY TRADE"],
  "Apply Retail Only":                         [C.blue,   C.blueBg,   "APPLY RETAIL ONLY"],
  "Long-Term Compounder — Buy on Listing Dip": [C.purple, C.purpleBg, "WATCH POST-LISTING BASE"],
  "Watch — Selective Apply":                   [C.amber,  C.amberBg,  "WATCH"],
  "Avoid":                                     [C.red,    C.redBg,    "AVOID"],
}

// ── Primitives ────────────────────────────────────────────────────────────
function Tag({ text, color=C.gray, bg=C.grayBg }: { text:string; color?:string; bg?:string }) {
  return <span style={{ display:"inline-block", padding:"2px 9px", borderRadius:99, fontSize:10, fontWeight:700, background:bg, color }}>{text}</span>
}
function Bar({ v, max=100, color=C.blue }: { v:number; max?:number; color?:string }) {
  return <div style={{ height:3, background:"#e5e7eb", borderRadius:2, marginTop:3 }}><div style={{ width:`${Math.min(100,Math.round(v/max*100))}%`, height:"100%", background:color, borderRadius:2 }} /></div>
}
function Card({ children, style={} }: { children:any; style?:any }) {
  return <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:14, padding:16, marginBottom:12, ...style }}>{children}</div>
}
function SectionTitle({ text }: { text:string }) {
  return <div style={{ fontSize:10, fontWeight:900, color:"#374151", letterSpacing:"0.08em", marginBottom:12, textTransform:"uppercase" }}>{text}</div>
}

// ─────────────────────────────────────────────────────────────────────────────
// A: HERO DECISION PANEL
// ─────────────────────────────────────────────────────────────────────────────
function HeroPanel({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const rec = s.recommendation || "Watch — Selective Apply"
  const [recFg, recBg, recLabel] = REC[rec] || [C.gray, C.grayBg, rec]
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmp = ipo.gmpPrice || 0
  const eff = s.regime?.gmpEfficiency || 0.6
  const expLow  = gmp ? Math.round(ip + gmp * 0.50) : null
  const expHigh = gmp ? Math.round(ip + gmp * 0.90) : null
  const exp12mLow  = s.businessScore >= 70 ? Math.round((s.businessScore - 70) * 0.5 + 15) : 5
  const exp12mHigh = s.businessScore >= 70 ? Math.round((s.businessScore - 70) * 1.2 + 20) : 12

  return (
    <div style={{ background:"#0f172a", borderRadius:16, padding:"18px 20px", color:"#f8fafc", marginBottom:12 }}>
      {/* Name + recommendation */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", flexWrap:"wrap", gap:12, marginBottom:16 }}>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:9, color:"#64748b", letterSpacing:"0.08em", marginBottom:4 }}>{ipo.status} · {ipo.sector}</div>
          <div style={{ fontSize:22, fontWeight:900, letterSpacing:"-0.02em", lineHeight:1.2, marginBottom:5 }}>{ipo.name}</div>
          <div style={{ fontSize:11, color:"#64748b" }}>
            ₹{ipo.priceBandLow}–₹{ip} · ₹{ipo.issueSize}Cr{ipo.lotSize?` · Lot ${ipo.lotSize}`:""}
          </div>
          {ipo.brokerNote && (
            <div style={{ marginTop:8, padding:"7px 11px", background:"rgba(255,255,255,0.05)", borderRadius:8, fontSize:10, color:"#94a3b8", lineHeight:1.6 }}>
              {ipo.brokerReco && <strong style={{ color:"#4ade80" }}>SBI Sec {ipo.brokerReco}: </strong>}
              {ipo.brokerNote}
            </div>
          )}
        </div>
        <div style={{ background:recBg, border:`2px solid ${recFg}`, borderRadius:14, padding:"12px 16px", textAlign:"center", flexShrink:0 }}>
          <div style={{ fontSize:13, fontWeight:900, color:recFg, letterSpacing:"0.03em" }}>{recLabel}</div>
          <div style={{ fontSize:9, color:C.gray, marginTop:4 }}>Confidence: {s.confidence||"Medium"}</div>
        </div>
      </div>

      {/* 5 score tiles */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:6, marginBottom:14 }}>
        {[
          { l:"Listing",    v:s.listingScore??0,    c:"#60a5fa" },
          { l:"Business",   v:s.businessScore??0,   c:"#4ade80" },
          { l:"Management", v:s.managementScore??0, c:"#c084fc" },
          { l:"Risk ↓",     v:s.risk?.score??0,     c:"#f87171" },
          { l:"Multibagger",v:s.multibaggerProb??0, c:"#fbbf24" },
        ].map(t => (
          <div key={t.l} style={{ background:"rgba(255,255,255,0.05)", borderRadius:10, padding:"9px 0", textAlign:"center" }}>
            <div style={{ fontSize:7, color:"#64748b", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:3 }}>{t.l}</div>
            <div style={{ fontSize:22, fontWeight:900, color:t.c, lineHeight:1 }}>{t.v}</div>
          </div>
        ))}
      </div>

      {/* Expected ranges */}
      <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
        {expLow && (
          <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:9, padding:"7px 12px" }}>
            <div style={{ fontSize:8, color:"#64748b", marginBottom:2 }}>Expected listing range</div>
            <div style={{ fontSize:14, fontWeight:800, color:"#4ade80" }}>₹{expLow} – ₹{expHigh}</div>
          </div>
        )}
        <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:9, padding:"7px 12px" }}>
          <div style={{ fontSize:8, color:"#64748b", marginBottom:2 }}>Expected 12M return</div>
          <div style={{ fontSize:14, fontWeight:800, color:"#c084fc" }}>+{exp12mLow}% – +{exp12mHigh}%</div>
        </div>
        {s.anchorValidation?.label && (
          <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:9, padding:"7px 12px" }}>
            <div style={{ fontSize:8, color:"#64748b", marginBottom:2 }}>Anchor signal</div>
            <div style={{ fontSize:11, fontWeight:700, color: s.anchorValidation.label.includes("Confirmation")?"#4ade80":s.anchorValidation.label.includes("Trap")?"#f87171":"#fbbf24" }}>
              {s.anchorValidation.label}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// B: HISTORICAL SIMILARITY ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function SimilarityEngine({ ipo }: { ipo:any }) {
  const sim = ipo.similar
  if (!sim) return null
  const examples = sim.examples || []

  return (
    <Card>
      <SectionTitle text="B · Historical Similarity Engine" />
      <div style={{ fontSize:10, color:C.gray, marginBottom:12 }}>
        Matched by: sector · subscription · anchor quality · market regime · financials
      </div>
      {/* Summary stats */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:6, marginBottom:12 }}>
        {[
          { l:"Avg D1 return",   v:sim.avgD1,     fmt:(x:number)=>`${x>=0?"+":""}${x}%`,  good:sim.avgD1>=0 },
          { l:"Avg 6M return",   v:sim.avgM6,     fmt:(x:number)=>`${x>=0?"+":""}${x}%`,  good:sim.avgM6>=0 },
          { l:"Positive D1 rate",v:sim.hitRate,   fmt:(x:number)=>`${x}%`,                 good:sim.hitRate>=65 },
          { l:"Data quality",    v:sim.dataQuality==="high"?3:sim.dataQuality==="medium"?2:1,
            fmt:()=>sim.dataQuality||"—", good:true },
        ].map(s => (
          <div key={s.l} style={{ background:C.grayBg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:8, color:C.gray, textTransform:"uppercase", marginBottom:2 }}>{s.l}</div>
            <div style={{ fontSize:15, fontWeight:900, color:s.good?C.green:C.red }}>{s.fmt(s.v)}</div>
          </div>
        ))}
      </div>
      {/* Top matches */}
      {examples.map((e:any, i:number) => {
        const sim_pct = [87, 83, 78][i] || 70
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:10, padding:"9px 11px", background:C.grayBg, borderRadius:9, marginBottom:5 }}>
            <div style={{ fontSize:13, fontWeight:800, color:C.blue, width:28, textAlign:"center" }}>{sim_pct}%</div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:12, fontWeight:700, color:"#111827" }}>{e.name}</div>
              <div style={{ fontSize:9, color:C.gray }}>{e.sector}</div>
            </div>
            <div style={{ display:"flex", gap:14, textAlign:"right" }}>
              <div>
                <div style={{ fontSize:8, color:C.gray }}>D1</div>
                <div style={{ fontSize:12, fontWeight:800, color:e.d1Return>=0?C.green:C.red }}>
                  {e.d1Return>=0?"+":""}{e.d1Return}%
                </div>
              </div>
              <div>
                <div style={{ fontSize:8, color:C.gray }}>6M</div>
                <div style={{ fontSize:12, fontWeight:800, color:e.m6Return>=0?C.green:C.red }}>
                  {e.m6Return>=0?"+":""}{e.m6Return}%
                </div>
              </div>
            </div>
          </div>
        )
      })}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// C: MULTIBAGGER ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function MultibaggerEngine({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const prob = s.multibaggerProb || 0
  const benchmarks = [
    { name:"Kaynes Technology", prob:85, d1:18, m12:145 },
    { name:"Netweb Technologies", prob:82, d1:82, m12:120 },
    { name:"DOMS Industries", prob:75, d1:68, m12:55 },
    { name:"Premier Energies", prob:78, d1:96, m12:85 },
    { name:"NSDL", prob:70, d1:10, m12:40 },
  ]

  return (
    <Card>
      <SectionTitle text="C · Multibagger Probability Engine" />
      <div style={{ display:"flex", gap:14, alignItems:"center", marginBottom:14 }}>
        {/* Probability gauge */}
        <div style={{ textAlign:"center", background:scoreBg(prob), borderRadius:14, padding:"14px 20px" }}>
          <div style={{ fontSize:38, fontWeight:900, color:scoreCol(prob), lineHeight:1 }}>{prob}%</div>
          <div style={{ fontSize:9, color:C.gray, marginTop:4 }}>MULTIBAGGER PROB</div>
        </div>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:12, fontWeight:700, color:scoreCol(prob), marginBottom:6 }}>
            {prob>=70?"Strong compounder candidate":prob>=50?"Moderate long-term potential":prob>=30?"Limited compounding case":"Low probability — listing trade only"}
          </div>
          <div style={{ fontSize:10, color:C.gray, lineHeight:1.7 }}>
            Business Quality: <strong>{s.businessScore||0}/100</strong><br/>
            Sector Momentum: <strong>{s.sectorMomentum||0}/100</strong><br/>
            Long-Term Rating: <strong>{s.businessRating||"—"}</strong>
          </div>
        </div>
      </div>
      {/* Benchmark comparisons */}
      <div style={{ fontSize:9, color:C.gray, marginBottom:6, textTransform:"uppercase", letterSpacing:"0.06em" }}>Closest compounder comparables</div>
      {benchmarks.filter(b => Math.abs(b.prob - prob) < 25).slice(0,3).map(b => (
        <div key={b.name} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:5 }}>
          <div style={{ width:130, fontSize:10, fontWeight:600, color:"#374151" }}>{b.name}</div>
          <div style={{ flex:1, height:5, background:"#e5e7eb", borderRadius:3 }}>
            <div style={{ width:`${b.prob}%`, height:"100%", background:C.purple, borderRadius:3 }} />
          </div>
          <div style={{ fontSize:9, color:C.gray, width:30 }}>{b.prob}%</div>
          <div style={{ fontSize:9, color:b.m12>=50?C.green:C.amber, width:48, textAlign:"right" }}>12M +{b.m12}%</div>
        </div>
      ))}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// D: ANCHOR HEATMAP
// ─────────────────────────────────────────────────────────────────────────────
function AnchorHeatmap({ ipo }: { ipo:any }) {
  const anchors: string[] = ipo.anchors || []
  const s = ipo.score || {}
  const anchorScore = s.anchorScore || 0
  const av = s.anchorValidation || {}

  const getTier = (name: string): 1|2|3 => {
    const n = name.toLowerCase()
    const t1 = ["adia","gic","temasek","norges","cppib","sbi mf","sbi mutual","hdfc mf","hdfc mutual","icici pru","nippon","axis mf","axis mutual","kotak mf","kotak mutual","blackrock","lic","morgan stanley","goldman sachs","wellington","fidelity","sbi life","hdfc life","icici pru life"]
    const t2 = ["franklin","mirae","dsp","nomura","ubs","bnp","hsbc","bandhan","whiteoak","ashoka"]
    if (t1.some(x => n.includes(x))) return 1
    if (t2.some(x => n.includes(x))) return 2
    return 3
  }
  const getCategory = (name: string): string => {
    const n = name.toLowerCase()
    if (["adia","gic","temasek","norges","cppib"].some(x => n.includes(x))) return "Sovereign"
    if (["sbi mf","hdfc mf","icici pru mf","nippon","axis mf","kotak mf","franklin","mirae","dsp"].some(x => n.includes(x))) return "Domestic MF"
    if (["lic","sbi life","hdfc life","icici pru life","kotak life"].some(x => n.includes(x))) return "Insurance"
    if (["blackrock","goldman sachs","morgan stanley","wellington","fidelity","nomura","ubs","bnp"].some(x => n.includes(x))) return "FPI"
    return "AIF/Other"
  }

  const cats = { "Sovereign":0, "Domestic MF":0, "Insurance":0, "FPI":0, "AIF/Other":0 }
  anchors.forEach(a => { const c = getCategory(a); cats[c as keyof typeof cats]++ })

  const [avFg, avBg] = av.label?.includes("Confirmation") ? [C.green,C.greenBg]
    : av.label?.includes("Trap") ? [C.red,C.redBg] : [C.amber,C.amberBg]

  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
        <SectionTitle text="D · Anchor Heatmap" />
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <div style={{ textAlign:"center", background:scoreBg(anchorScore), borderRadius:9, padding:"4px 12px" }}>
            <div style={{ fontSize:18, fontWeight:900, color:scoreCol(anchorScore) }}>{anchorScore}</div>
            <div style={{ fontSize:7, color:C.gray }}>QUALITY</div>
          </div>
          {av.label && <Tag text={av.label} color={avFg} bg={avBg} />}
        </div>
      </div>

      {/* Category breakdown */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:5, marginBottom:12 }}>
        {Object.entries(cats).map(([cat, count]) => (
          <div key={cat} style={{ background:C.grayBg, borderRadius:8, padding:"7px 6px", textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:900, color:count>0?C.blue:C.gray }}>{count}</div>
            <div style={{ fontSize:7, color:C.gray, lineHeight:1.3 }}>{cat}</div>
          </div>
        ))}
      </div>

      {/* Tier breakdown */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:6, marginBottom:10 }}>
        {[
          { label:"Tier 1", color:C.green, bg:C.greenBg, desc:"Sovereign · MF · Insurance", anchors:anchors.filter(a=>getTier(a)===1) },
          { label:"Tier 2", color:C.blue,  bg:C.blueBg,  desc:"Mid-tier FPI · MF",         anchors:anchors.filter(a=>getTier(a)===2) },
          { label:"Tier 3", color:C.gray,  bg:C.grayBg,  desc:"AIF · PMS · Family",        anchors:anchors.filter(a=>getTier(a)===3) },
        ].map(t => (
          <div key={t.label} style={{ background:t.bg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:20, fontWeight:900, color:t.color }}>{t.anchors.length}</div>
            <div style={{ fontSize:8, fontWeight:700, color:t.color }}>{t.label}</div>
            <div style={{ fontSize:8, color:C.gray }}>{t.desc}</div>
          </div>
        ))}
      </div>

      {/* Named anchors */}
      {anchors.length > 0 && (
        <div style={{ display:"flex", gap:5, flexWrap:"wrap", marginBottom:8 }}>
          {anchors.map((a:string) => {
            const t = getTier(a)
            const [c,bg] = t===1?[C.green,C.greenBg]:t===2?[C.blue,C.blueBg]:[C.gray,C.grayBg]
            return <Tag key={a} text={`${t===1?"★ ":t===2?"◆ ":" "}${a}`} color={c} bg={bg} />
          })}
        </div>
      )}
      {anchors.length === 0 && <div style={{ fontSize:11, color:C.gray }}>No anchor data yet — upload SBI Sec PDF or fetch live data</div>}
      {av.detail && <div style={{ fontSize:10, color:C.gray, lineHeight:1.5, marginTop:6 }}>{av.detail}</div>}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// E: MARKET REGIME WIDGET
// ─────────────────────────────────────────────────────────────────────────────
function RegimeWidget({ regime }: { regime:any }) {
  if (!regime) return null
  const map: Record<string,[string,string,string]> = {
    HOT:    [C.green,  C.greenBg,  "HOT 🔥"],
    NORMAL: [C.blue,   C.blueBg,   "NORMAL"],
    COLD:   [C.red,    C.redBg,    "COLD ❄"],
  }
  const [fg, bg, label] = map[regime.label] || map.NORMAL
  const recentStats: Record<string,{avg:number,pos:number,count:number}> = {
    HOT:    { avg:34, pos:89, count:27 },
    NORMAL: { avg:9,  pos:68, count:95 },
    COLD:   { avg:2,  pos:42, count:24 },
  }
  const stats = recentStats[regime.label] || recentStats.NORMAL

  return (
    <div style={{ background:bg, border:`1px solid ${fg}30`, borderRadius:12, padding:"12px 16px", marginBottom:12 }}>
      <SectionTitle text="E · Market Regime" />
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:8, alignItems:"center" }}>
        <div>
          <div style={{ fontSize:22, fontWeight:900, color:fg }}>{label}</div>
          <div style={{ fontSize:9, color:C.gray, marginTop:2 }}>Score: {regime.score}/100</div>
        </div>
        {[
          { l:"12M avg gain",    v:`+${stats.avg}%` },
          { l:"Positive rate",   v:`${stats.pos}%` },
          { l:"GMP efficiency",  v:`${Math.round((regime.gmpEfficiency||0.6)*100)}%` },
        ].map(s => (
          <div key={s.l} style={{ textAlign:"center" }}>
            <div style={{ fontSize:8, color:C.gray, textTransform:"uppercase", marginBottom:2 }}>{s.l}</div>
            <div style={{ fontSize:16, fontWeight:900, color:fg }}>{s.v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// F: OFS vs FRESH ISSUE BANNER
// ─────────────────────────────────────────────────────────────────────────────
function IssueBanner({ ipo }: { ipo:any }) {
  const fresh = ipo.freshIssuePct ?? 0
  const ofs   = ipo.ofsPct ?? 100
  const isBad = ofs >= 70
  const isGood = fresh >= 70

  return (
    <Card>
      <SectionTitle text="F · OFS vs Fresh Issue" />
      <div style={{ height:22, borderRadius:11, overflow:"hidden", display:"flex", marginBottom:10 }}>
        {fresh > 0 && (
          <div style={{ width:`${fresh}%`, background:C.green, display:"flex", alignItems:"center", justifyContent:"center" }}>
            {fresh > 12 && <span style={{ fontSize:9, color:"#fff", fontWeight:800 }}>{fresh}% Fresh</span>}
          </div>
        )}
        <div style={{ flex:1, background:"#fca5a5", display:"flex", alignItems:"center", justifyContent:"center" }}>
          <span style={{ fontSize:9, color:"#7f1d1d", fontWeight:800 }}>{ofs}% OFS</span>
        </div>
      </div>
      {/* Warning / badge */}
      {isBad && (
        <div style={{ background:C.redBg, border:`1px solid ${C.redBd}`, borderRadius:8, padding:"8px 12px", marginBottom:8 }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.red }}>
            🔴 OFS {ofs}% — {ofs>=90?"100% OFS: zero growth capital raised. Existing investors exiting.":"High OFS: majority is investor exit, not growth funding."}
          </div>
        </div>
      )}
      {isGood && (
        <div style={{ background:C.greenBg, border:`1px solid ${C.greenBd}`, borderRadius:8, padding:"8px 12px", marginBottom:8 }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.green }}>✅ Fresh Issue {fresh}% — growth capital badge: company raising funds for expansion</div>
        </div>
      )}
      {!isBad && !isGood && (
        <div style={{ fontSize:11, color:C.amber }}>⚠ Mixed issue — partial growth capital, partial investor exit</div>
      )}
      {ipo.peRatio && ipo.peerPE && (
        <div style={{ marginTop:8, padding:"7px 10px", background:C.grayBg, borderRadius:8, fontSize:11, color:"#374151" }}>
          PE: <strong>{ipo.peRatio}x</strong> vs peers ({ipo.peerLabel})
          <span style={{ marginLeft:8, fontWeight:700, color:ipo.peRatio<ipo.peerPE?C.green:C.amber }}>
            {ipo.peRatio<ipo.peerPE
              ? `${Math.round((1-ipo.peRatio/ipo.peerPE)*100)}% discount ✅`
              : `${Math.round((ipo.peRatio/ipo.peerPE-1)*100)}% premium ⚠`}
          </span>
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// G: LISTING-DAY TRADING ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function TradingEngine({ ipo, onGmpUpdate }: { ipo:any; onGmpUpdate:(v:number)=>void }) {
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 192
  const [gmp, setGmp] = useState<number>(ipo.gmpPrice || 0)
  const lot = ipo.lotSize || 78
  const regime = ipo.score?.regime?.label || "NORMAL"
  const eff = regime==="HOT"?0.70:regime==="COLD"?0.50:0.60
  const gmpPct = ip>0 ? (gmp/ip*100) : 0
  const gmpStrength = gmpPct>=50?"Very Hot 🔥":gmpPct>=20?"Strong":gmpPct>=8?"Moderate":gmpPct>=3?"Weak":"No Signal"
  const entry = ip + gmp
  const bull  = Math.round(ip + gmp*0.90)
  const base  = Math.round(ip + gmp*eff)
  const bear  = Math.round(ip - gmp*0.20)
  const stop  = Math.round(entry*0.90)
  const exitL = Math.round(entry*1.05)
  const exitH = Math.round(entry*1.12)
  const trend = ipo.gmpTrend || []

  const [gmpInput, setGmpInput] = useState(String(ipo.gmpPrice||""))
  const [saved, setSaved] = useState(false)
  const handleSave = async () => {
    const n = parseFloat(gmpInput)
    if (!isNaN(n)) {
      setGmp(n)
      onGmpUpdate(n)
      await fetch("/api/ipo/gmp", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ name:ipo.name, gmpPrice:n }) })
      setSaved(true); setTimeout(()=>setSaved(false), 2000)
    }
  }

  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
        <SectionTitle text="G · Listing-Day Trading Engine" />
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          {trend.length > 1 && (
            <div style={{ display:"flex", alignItems:"flex-end", gap:2, height:18 }}>
              {trend.map((v:number,i:number) => { const mx=Math.max(...trend); const h=Math.max(2,Math.round(v/mx*18)); return <div key={i} style={{ width:5,height:h,borderRadius:2,background:i===trend.length-1?C.green:"#d1d5db" }} /> })}
            </div>
          )}
          <Tag text={gmpStrength} color={gmpPct>=20?C.green:gmpPct>=8?C.amber:C.gray} bg={gmpPct>=20?C.greenBg:gmpPct>=8?C.amberBg:C.grayBg} />
        </div>
      </div>

      {/* GMP Slider */}
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:12 }}>
        <span style={{ fontSize:10, color:C.gray, whiteSpace:"nowrap" }}>GMP ₹</span>
        <input type="range" min={0} max={250} step={1} value={gmp} onChange={e=>setGmp(+e.target.value)}
          style={{ flex:1, accentColor:C.blue }} />
        <span style={{ fontSize:20, fontWeight:900, color:"#0f172a", minWidth:40, textAlign:"right" }}>{gmp}</span>
        <span style={{ fontSize:10, color:C.gray }}>({gmpPct.toFixed(1)}%)</span>
      </div>

      {/* Key prices */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8, marginBottom:12 }}>
        {[
          { l:"Issue price",    v:`₹${ip}`,              c:"#374151", bg:C.grayBg },
          { l:"Current GMP",    v:`+₹${gmp}`,            c:C.green,   bg:C.greenBg },
          { l:"GMP entry price",v:`₹${Math.round(entry)}`,c:C.blue,   bg:C.blueBg },
        ].map(s => (
          <div key={s.l} style={{ background:s.bg, borderRadius:10, padding:"9px 10px", textAlign:"center" }}>
            <div style={{ fontSize:8, color:C.gray, marginBottom:3, textTransform:"uppercase" }}>{s.l}</div>
            <div style={{ fontSize:16, fontWeight:900, color:s.c }}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* 3 scenarios */}
      <div style={{ display:"flex", flexDirection:"column", gap:6, marginBottom:12 }}>
        {[
          { label:`Bull listing — 90% GMP captured → sell Week 1`, price:bull, gain:entry>0?((bull-entry)/entry*100):0, good:true },
          { label:`Base listing — ${Math.round(eff*100)}% GMP (${regime} market)`, price:base, gain:entry>0?((base-entry)/entry*100):0, good:base>=entry },
          { label:"Bad day — GMP −20% at open (hard stop triggered)", price:bear, gain:entry>0?((bear-entry)/entry*100):0, good:false },
        ].map((s,i) => (
          <div key={i} style={{ background:s.good?C.greenBg:C.redBg, borderRadius:9, padding:"10px 12px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <div style={{ fontSize:10, color:s.good?C.green:C.red, fontWeight:600 }}>{s.label}</div>
            <div style={{ textAlign:"right", flexShrink:0 }}>
              <div style={{ fontSize:15, fontWeight:900, color:s.good?C.green:C.red }}>₹{s.price}</div>
              <div style={{ fontSize:10, color:s.good?"#16a34a":"#dc2626" }}>{s.gain>=0?"+":""}{s.gain.toFixed(1)}%</div>
            </div>
          </div>
        ))}
      </div>

      {/* Per-lot P&L */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:6, marginBottom:12 }}>
        {[
          { l:`Max gain · ${lot} shares`,   v:`+₹${Math.abs(Math.round((bull-entry)*lot)).toLocaleString("en-IN")}`, c:C.green, bg:C.greenBg },
          { l:"Hard stop −10%",              v:`−₹${Math.abs(Math.round((stop-entry)*lot)).toLocaleString("en-IN")}`, c:C.red,   bg:C.redBg },
          { l:"D1 exit target",              v:`₹${exitL}–₹${exitH}`,  c:C.blue, bg:C.blueBg },
        ].map(s => (
          <div key={s.l} style={{ background:s.bg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:8, color:C.gray, textTransform:"uppercase", marginBottom:3 }}>{s.l}</div>
            <div style={{ fontSize:12, fontWeight:900, color:s.c }}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* Two outcomes */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6, marginBottom:10 }}>
        <div style={{ background:C.greenBg, borderRadius:9, padding:"9px 12px" }}>
          <div style={{ fontSize:10, fontWeight:800, color:C.green, marginBottom:3 }}>↑ Positive listing</div>
          <div style={{ fontSize:10, color:"#16a34a", lineHeight:1.6 }}>
            Exit ₹{exitL}–₹{exitH} by Week 1.<br/>
            Do not hold beyond Week 1 without base.
          </div>
        </div>
        <div style={{ background:C.redBg, borderRadius:9, padding:"9px 12px" }}>
          <div style={{ fontSize:10, fontWeight:800, color:C.red, marginBottom:3 }}>↓ Negative listing</div>
          <div style={{ fontSize:10, color:"#dc2626", lineHeight:1.6 }}>
            Exit at open − 10% stop = ₹{stop}.<br/>
            No averaging. Wait for IPO base.
          </div>
        </div>
      </div>

      {/* GMP manual update */}
      <div style={{ borderTop:"1px solid #f1f5f9", paddingTop:10, display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
        <span style={{ fontSize:10, color:C.gray }}>Update GMP:</span>
        <input value={gmpInput} onChange={e=>setGmpInput(e.target.value)} placeholder="₹ e.g. 70"
          style={{ width:90, border:"1px solid #e5e7eb", borderRadius:7, padding:"5px 8px", fontSize:12 }} />
        <button onClick={handleSave}
          style={{ padding:"5px 12px", background:saved?C.green:"#0f172a", border:"none", borderRadius:7, color:"#fff", fontSize:11, fontWeight:700, cursor:"pointer" }}>
          {saved?"✓ Saved":"Set GMP"}
        </button>
        <span style={{ fontSize:9, color:"#9ca3af" }}>Sources: InvestorGain · IPOWatch · 5paisa</span>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// H: IPO DNA CLASSIFICATION
// ─────────────────────────────────────────────────────────────────────────────
function IpoDna({ ipo }: { ipo:any }) {
  const sector = ipo.sector || ""
  const examples = ipo.similar?.examples || []
  const archetypes: Record<string,{icon:string;color:string;traits:string}> = {
    "Defense":          { icon:"🛡", color:C.blue,   traits:"High-conviction institutional · Defense capex cycle · Strong OB visibility" },
    "EMS/Electronics":  { icon:"⚡", color:C.cyan,   traits:"Revenue visibility · Customer stickiness · Operating leverage play" },
    "Solar":            { icon:"☀", color:C.amber,  traits:"PLI beneficiary · Capacity expansion · Green energy tailwind" },
    "SaaS":             { icon:"💾", color:C.purple, traits:"Recurring revenue · Low capex · High margin scalability" },
    "Financial Infrastructure": { icon:"🏛", color:C.green, traits:"Regulatory moat · Network effect · High ROCE visibility" },
    "NBFC":             { icon:"💰", color:C.green,  traits:"Spread business · Asset quality watch · Growth vs NPAs" },
    "IT Infrastructure":{ icon:"🖥", color:C.blue,   traits:"Domestic enterprise spend · AI/cloud infra · High win rates" },
    "Pharma":           { icon:"💊", color:C.cyan,   traits:"USFDA pipeline · Domestic formulations · Export diversification" },
    "Manufacturing":    { icon:"🏭", color:C.gray,   traits:"China+1 play · Capacity addition · Operating leverage" },
    "Infrastructure EPC":{ icon:"🏗", color:C.amber, traits:"Order book · Execution track record · Working capital watch" },
    "PSU":              { icon:"🏢", color:C.gray,   traits:"Government dividend · Low valuation · Liquidity discount" },
    "Retail/Apparel":   { icon:"🛍", color:C.red,    traits:"Brand building · Unit economics · Store expansion" },
  }
  const match = Object.keys(archetypes).find(k => sector.toLowerCase().includes(k.split("/")[0].toLowerCase()))
  const arch = match || "Manufacturing"
  const meta = archetypes[arch]

  return (
    <Card>
      <SectionTitle text="H · IPO DNA Classification" />
      <div style={{ display:"flex", gap:12, alignItems:"flex-start", marginBottom:14 }}>
        <div style={{ fontSize:36 }}>{meta.icon}</div>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:16, fontWeight:900, color:meta.color }}>{arch}</div>
          <div style={{ fontSize:10, color:C.gray, marginBottom:6 }}>{sector}</div>
          <div style={{ fontSize:10, color:"#374151", lineHeight:1.6 }}>{meta.traits}</div>
        </div>
        <div style={{ textAlign:"center", background:scoreBg(ipo.score?.multibaggerProb||0), borderRadius:10, padding:"8px 14px" }}>
          <div style={{ fontSize:22, fontWeight:900, color:scoreCol(ipo.score?.multibaggerProb||0) }}>{ipo.score?.multibaggerProb||0}%</div>
          <div style={{ fontSize:8, color:C.gray }}>MULTIBAGGER</div>
        </div>
      </div>
      {examples.length > 0 && (
        <div>
          <div style={{ fontSize:9, color:C.gray, marginBottom:8, textTransform:"uppercase", letterSpacing:"0.06em" }}>This IPO behaves like:</div>
          {examples.map((e:any,i:number) => {
            const pcts=[65,22,13]
            return (
              <div key={i} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:5 }}>
                <div style={{ fontSize:10, fontWeight:700, color:"#374151", width:140, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{e.name}</div>
                <div style={{ flex:1, height:6, background:"#e5e7eb", borderRadius:3 }}>
                  <div style={{ width:`${pcts[i]}%`, height:"100%", background:C.blue, borderRadius:3 }} />
                </div>
                <div style={{ fontSize:10, color:C.gray, width:30 }}>{pcts[i]}%</div>
                <div style={{ fontSize:10, color:e.d1Return>=0?C.green:C.red, width:48, textAlign:"right" }}>
                  D1 {e.d1Return>=0?"+":""}{e.d1Return}%
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// I: RISK FLAGS
// ─────────────────────────────────────────────────────────────────────────────
function RiskPanel({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const flags  = s.flags  || []
  const greens = s.greens || []
  const level  = s.risk?.level || "MEDIUM"
  const [lFg,lBg] = level==="EXTREME"||level==="HIGH"?[C.red,C.redBg]:level==="MEDIUM"?[C.amber,C.amberBg]:[C.green,C.greenBg]

  return (
    <Card>
      <SectionTitle text="I · Risk Engine" />
      <div style={{ display:"flex", gap:8, alignItems:"center", marginBottom:12 }}>
        <div style={{ background:lBg, border:`1px solid ${lFg}30`, borderRadius:8, padding:"6px 14px" }}>
          <span style={{ fontSize:13, fontWeight:900, color:lFg }}>RISK: {level}</span>
        </div>
        <div style={{ fontSize:11, color:C.gray }}>Score: {s.risk?.score??0}/100</div>
        {s.riskMultiplier < 1 && <div style={{ fontSize:10, color:C.red }}>Penalty: {Number(s.riskMultiplier).toFixed(2)}x applied</div>}
      </div>
      {(flags.length > 0 || greens.length > 0) && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
          {greens.length > 0 && (
            <div style={{ background:C.greenBg, border:`1px solid ${C.greenBd}`, borderRadius:11, padding:12 }}>
              <div style={{ fontSize:9, fontWeight:800, color:C.green, marginBottom:7, letterSpacing:"0.06em" }}>✅ GREEN FLAGS</div>
              {greens.map((g:string,i:number) => <div key={i} style={{ fontSize:10, color:"#374151", marginBottom:4, lineHeight:1.4 }}>{g}</div>)}
            </div>
          )}
          {flags.length > 0 && (
            <div style={{ background:C.redBg, border:`1px solid ${C.redBd}`, borderRadius:11, padding:12 }}>
              <div style={{ fontSize:9, fontWeight:800, color:C.red, marginBottom:7, letterSpacing:"0.06em" }}>⚠ RISK FLAGS</div>
              {flags.map((f:string,i:number) => <div key={i} style={{ fontSize:10, color:"#374151", marginBottom:4, lineHeight:1.4 }}>{f}</div>)}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// J: POST-LISTING ACTION PLAN
// ─────────────────────────────────────────────────────────────────────────────
function ActionPlan({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const qualGood = (s.businessScore||0) >= 75
  const riskLow  = (s.risk?.score||50) < 40
  const listing  = (s.listingScore||0) >= 65
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmp = ipo.gmpPrice || 0
  const exitL = Math.round((ip+gmp)*1.05)
  const exitH = Math.round((ip+gmp)*1.12)

  const steps = [
    { t:"Day 1", icon:"🔔",
      text: listing
        ? `If positive open: sell between 10AM–12PM. Target exit ₹${exitL}–₹${exitH}. Do not wait for close.`
        : "If opens negative: exit at market immediately. Apply hard stop −10%. Zero averaging." },
    { t:"Week 1", icon:"📊",
      text:"Trail stop at opening price. Book 50% if gain >15%. Watch volume — continuation only on rising volume." },
    { t:"Month 1", icon:"⏳",
      text:"Do not average down. Wait for IPO base formation (price consolidation 3–6 weeks after listing). Re-enter only on clean breakout with volume." },
    { t:"Long Term", icon: qualGood&&riskLow?"🌱":"⚠",
      text: qualGood&&riskLow
        ? `Quality ${s.businessScore}/100 + Risk ${s.risk?.score}/100 → eligible long-term hold. Review quarterly results. Exit if ROCE drops below 15%.`
        : `Quality ${s.businessScore||0}/100 — not yet a long-term hold. Exit on listing pop. Watch for 2–3 quarters before re-evaluating.` },
  ]

  return (
    <Card>
      <SectionTitle text="J · Post-Listing Action Plan" />
      {steps.map((step,i) => (
        <div key={i} style={{ display:"flex", gap:12, padding:"9px 11px", background:C.grayBg, borderRadius:9, marginBottom:6 }}>
          <div style={{ fontSize:16 }}>{step.icon}</div>
          <div>
            <div style={{ fontSize:9, fontWeight:800, color:C.gray, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:3 }}>{step.t}</div>
            <div style={{ fontSize:11, color:"#374151", lineHeight:1.6 }}>{step.text}</div>
          </div>
        </div>
      ))}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// DUAL MODEL SCORES
// ─────────────────────────────────────────────────────────────────────────────
function DualModels({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  return (
    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12 }}>
      {/* Model 1 */}
      <Card style={{ marginBottom:0 }}>
        <div style={{ fontSize:9, fontWeight:800, color:"#374151", marginBottom:10, letterSpacing:"0.06em" }}>MODEL 1 · LISTING ENGINE</div>
        <div style={{ fontSize:28, fontWeight:900, color:scoreCol(s.listingScore??0), lineHeight:1 }}>{s.listingScore??0}</div>
        <div style={{ fontSize:10, fontWeight:700, color:scoreCol(s.listingScore??0), marginBottom:10 }}>{s.listingRating||"—"}</div>
        {Object.entries(s.listingComponents||{}).map(([k,v]:any) => (
          <div key={k} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:4 }}>
            <span style={{ fontSize:9, color:C.gray, textTransform:"capitalize" }}>{k.replace(/([A-Z])/g," $1")}</span>
            <div style={{ display:"flex", alignItems:"center", gap:4 }}>
              <div style={{ width:50, height:3, background:"#e5e7eb", borderRadius:2 }}>
                <div style={{ width:`${Math.round((v/25)*100)}%`, height:"100%", background:C.blue, borderRadius:2 }} />
              </div>
              <span style={{ fontSize:9, fontWeight:700, color:"#374151", minWidth:18, textAlign:"right" }}>{v}</span>
            </div>
          </div>
        ))}
      </Card>
      {/* Model 2 */}
      <Card style={{ marginBottom:0 }}>
        <div style={{ fontSize:9, fontWeight:800, color:"#374151", marginBottom:10, letterSpacing:"0.06em" }}>MODEL 2 · BUSINESS QUALITY</div>
        <div style={{ fontSize:28, fontWeight:900, color:scoreCol(s.businessScore??0), lineHeight:1 }}>{s.businessScore??0}</div>
        <div style={{ fontSize:10, fontWeight:700, color:scoreCol(s.businessScore??0), marginBottom:10 }}>{s.businessRating||"—"}</div>
        {Object.entries(s.businessComponents||{}).map(([k,v]:any) => (
          <div key={k} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:4 }}>
            <span style={{ fontSize:9, color:C.gray, textTransform:"capitalize" }}>{k.replace(/([A-Z])/g," $1")}</span>
            <div style={{ display:"flex", alignItems:"center", gap:4 }}>
              <div style={{ width:50, height:3, background:"#e5e7eb", borderRadius:2 }}>
                <div style={{ width:`${Math.round((v/20)*100)}%`, height:"100%", background:C.green, borderRadius:2 }} />
              </div>
              <span style={{ fontSize:9, fontWeight:700, color:"#374151", minWidth:18, textAlign:"right" }}>{v}</span>
            </div>
          </div>
        ))}
        {(s.multibaggerProb||0) > 0 && (
          <div style={{ marginTop:8, padding:"6px 10px", background:s.multibaggerProb>=60?C.greenBg:C.grayBg, borderRadius:8 }}>
            <div style={{ fontSize:8, color:C.gray }}>Multibagger probability</div>
            <div style={{ fontSize:14, fontWeight:900, color:s.multibaggerProb>=60?C.green:"#374151" }}>{s.multibaggerProb}%</div>
          </div>
        )}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MANAGEMENT QUALITY
// ─────────────────────────────────────────────────────────────────────────────
function MgmtPanel({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const mgmt = s.managementScore ?? 0
  if (!mgmt) return null
  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12 }}>
        <SectionTitle text="Management Quality Score" />
        <div style={{ textAlign:"center", background:scoreBg(mgmt), borderRadius:9, padding:"4px 12px" }}>
          <div style={{ fontSize:20, fontWeight:900, color:scoreCol(mgmt) }}>{mgmt}</div>
          <div style={{ fontSize:7, color:C.gray }}>/ 100</div>
        </div>
      </div>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:4, marginBottom:10 }}>
        {Object.entries(s.managementComponents||{}).map(([k,v]:any) => (
          <div key={k} style={{ display:"flex", justifyContent:"space-between", padding:"5px 0", borderBottom:"1px solid #f3f4f6" }}>
            <span style={{ fontSize:9, color:C.gray, textTransform:"capitalize" }}>{k.replace(/([A-Z])/g," $1").trim()}</span>
            <span style={{ fontSize:9, fontWeight:700, color:v>=8?C.green:v>=5?"#374151":C.red }}>{v}</span>
          </div>
        ))}
      </div>
      {s.managementPositives?.map((p:string,i:number) => <div key={i} style={{ fontSize:10, color:C.green, marginBottom:3 }}>✅ {p}</div>)}
      {s.managementFlags?.map((f:string,i:number) => <div key={i} style={{ fontSize:10, color:C.red, marginBottom:3 }}>⚠ {f}</div>)}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PDF UPLOAD
// ─────────────────────────────────────────────────────────────────────────────
function PdfUpload({ onData }: { onData:(d:any)=>void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<"idle"|"loading"|"done"|"error">("idle")
  const [msg, setMsg] = useState("")

  const handle = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setState("loading")
    setMsg(`Reading ${file.name}…`)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await fetch("/api/ipo/upload", { method:"POST", body:fd })
      const d = await res.json()
      if (d.ok) {
        setState("done")
        setMsg(d.message)
        onData(d.extracted)
      } else {
        setState("error")
        setMsg(`Error: ${d.error}`)
      }
    } catch (err: any) {
      setState("error")
      setMsg(`Error: ${err.message}`)
    }
    // Reset so same file can be re-uploaded
    if (ref.current) ref.current.value = ""
  }

  return (
    <div style={{ border:"1.5px dashed #cbd5e1", borderRadius:12, padding:"12px 16px", background:"#f8fafc", marginBottom:12 }}>
      <div style={{ display:"flex", alignItems:"center", gap:12, flexWrap:"wrap" }}>
        <button onClick={() => ref.current?.click()}
          style={{ padding:"8px 16px", background:"#0f172a", color:"#f8fafc", border:"none", borderRadius:8, fontSize:12, fontWeight:700, cursor:"pointer" }}>
          📄 Upload SBI Sec / Broker PDF
        </button>
        <div style={{ fontSize:11, color:
          state==="loading"?"#3b82f6":state==="done"?C.green:state==="error"?C.red:"#64748b" }}>
          {state==="idle"  && "Upload any broker research note — auto-fills all engine values"}
          {state==="loading" && `⏳ ${msg}`}
          {state==="done"    && `✅ ${msg}`}
          {state==="error"   && `❌ ${msg}`}
        </div>
        <input ref={ref} type="file" accept=".pdf,.txt,.PDF" onChange={handle} style={{ display:"none" }} />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SCRAPE BUTTON
// ─────────────────────────────────────────────────────────────────────────────
function ScrapeButton({ ipoName, onData }: { ipoName:string; onData:(d:any)=>void }) {
  const [state, setState] = useState<"idle"|"loading"|"done">("idle")
  const run = async () => {
    setState("loading")
    try {
      const res = await fetch("/api/ipo/scrape", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:ipoName })
      })
      const d = await res.json()
      if (d.ok && d.results?.[0]) {
        onData(d.results[0])
        setState("done")
      } else setState("idle")
    } catch { setState("idle") }
    setTimeout(() => setState("idle"), 4000)
  }
  return (
    <button onClick={run} disabled={state==="loading"}
      style={{ padding:"6px 13px", background:state==="done"?C.green:C.blue, color:"#fff", border:"none", borderRadius:7, fontSize:10, fontWeight:700, cursor:"pointer", opacity:state==="loading"?0.7:1 }}>
      {state==="loading"?"⏳ Fetching…":state==="done"?"✅ Updated":"🔄 Fetch Live Data"}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// IPO LIST CARD
// ─────────────────────────────────────────────────────────────────────────────
function IpoCard({ ipo, onClick }: { ipo:any; onClick:()=>void }) {
  const s = ipo.score || {}
  const rec = s.recommendation || "Watch — Selective Apply"
  const [recFg,,recLabel] = REC[rec] || [C.gray,C.grayBg,"WATCH"]
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmpEntry = ipo.gmpPrice ? ip + ipo.gmpPrice : null
  const statusCol: Record<string,string> = { OPEN:C.green, UPCOMING:C.blue, LISTED:C.gray, CLOSED:C.gray }
  const sCol = statusCol[ipo.status||""] || C.gray

  return (
    <div onClick={onClick}
      style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:14, overflow:"hidden", cursor:"pointer", transition:"box-shadow .15s,transform .15s" }}
      onMouseEnter={e=>{const d=e.currentTarget as HTMLDivElement;d.style.boxShadow="0 8px 24px rgba(0,0,0,0.10)";d.style.transform="translateY(-1px)"}}
      onMouseLeave={e=>{const d=e.currentTarget as HTMLDivElement;d.style.boxShadow="none";d.style.transform="none"}}>

      <div style={{ height:3, background:sCol }} />
      <div style={{ padding:"12px 14px 11px" }}>
        {/* Name + recommendation */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:9 }}>
          <div style={{ flex:1, paddingRight:8 }}>
            <div style={{ fontSize:13, fontWeight:800, color:"#0f172a", lineHeight:1.3, marginBottom:1 }}>{ipo.name}</div>
            <div style={{ fontSize:9, color:C.gray }}>{ipo.sector} · ₹{ipo.issueSize}Cr</div>
          </div>
          <div style={{ background:scoreBg(s.listingScore??0), border:`1.5px solid ${scoreCol(s.listingScore??0)}30`, borderRadius:9, padding:"5px 9px", flexShrink:0, textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:900, color:scoreCol(s.listingScore??0), lineHeight:1 }}>{s.listingScore??0}</div>
            <div style={{ fontSize:7, fontWeight:700, color:scoreCol(s.listingScore??0), marginTop:1, letterSpacing:"0.04em" }}>LISTING</div>
          </div>
        </div>

        {/* GMP block */}
        {gmpEntry ? (
          <div style={{ background:C.greenBg, borderRadius:9, padding:"8px 11px", marginBottom:8 }}>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:4 }}>
              {[
                { l:"Issue",  v:`₹${ip}`,               c:"#374151" },
                { l:"GMP",    v:`+₹${ipo.gmpPrice}`,    c:C.green },
                { l:"Entry",  v:`₹${Math.round(gmpEntry)}`, c:C.blue },
              ].map(s => (
                <div key={s.l} style={{ textAlign:"center" }}>
                  <div style={{ fontSize:7, color:C.gray, marginBottom:1 }}>{s.l}</div>
                  <div style={{ fontSize:12, fontWeight:800, color:s.c }}>{s.v}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ background:C.grayBg, border:"1px dashed #e5e7eb", borderRadius:9, padding:"6px 11px", marginBottom:8, textAlign:"center" }}>
            <div style={{ fontSize:10, color:C.gray }}>No GMP · tap to add</div>
          </div>
        )}

        {/* 3 model scores */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:5, marginBottom:8 }}>
          {[
            { l:"Listing",  v:s.listingScore??0,   bg:C.blueBg },
            { l:"Business", v:s.businessScore??0,  bg:C.greenBg },
            { l:"Mgmt",     v:s.managementScore??0,bg:C.purpleBg },
          ].map(t => (
            <div key={t.l} style={{ background:t.bg, borderRadius:7, padding:"5px 8px", textAlign:"center" }}>
              <div style={{ fontSize:7, color:C.gray, marginBottom:1 }}>{t.l}</div>
              <div style={{ fontSize:15, fontWeight:900, color:scoreCol(t.v) }}>{t.v||"?"}</div>
            </div>
          ))}
        </div>

        {/* Tags */}
        <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
          <Tag text={ipo.status} color={sCol} bg={sCol+"18"} />
          <Tag text={recLabel} color={recFg} bg={recFg+"15"} />
          {ipo.brokerReco && <Tag text={`SBI ${ipo.brokerReco}`} color={C.green} bg={C.greenBg} />}
          {(ipo.freshIssuePct??0)===0 && <Tag text="100% OFS" color={C.red} bg={C.redBg} />}
          {(s.multibaggerProb??0)>=65 && <Tag text="Multibagger" color={C.purple} bg={C.purpleBg} />}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// DETAIL VIEW — full command center
// ─────────────────────────────────────────────────────────────────────────────
function IpoDetail({ ipo: _ipo, onBack }: { ipo:any; onBack:()=>void }) {
  const [ipo, setIpo] = useState(_ipo)

  const merge = (d: any) => setIpo((prev: any) => ({ ...prev, ...d }))

  return (
    <div>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
        <button onClick={onBack}
          style={{ padding:"7px 14px", background:C.grayBg, border:"1px solid #e5e7eb", borderRadius:8, cursor:"pointer", fontSize:12, color:"#374151", fontWeight:600 }}>
          ← All IPOs
        </button>
        <ScrapeButton ipoName={ipo.name} onData={merge} />
      </div>

      {/* PDF Upload */}
      <PdfUpload onData={merge} />

      {/* Sections A–J in order from the prompt */}
      <HeroPanel ipo={ipo} />
      <RegimeWidget regime={ipo.score?.regime} />
      <SimilarityEngine ipo={ipo} />
      <MultibaggerEngine ipo={ipo} />
      <AnchorHeatmap ipo={ipo} />
      <IssueBanner ipo={ipo} />
      <TradingEngine ipo={ipo} onGmpUpdate={(v) => setIpo((p: any) => ({ ...p, gmpPrice:v }))} />
      <IpoDna ipo={ipo} />
      <DualModels ipo={ipo} />
      <MgmtPanel ipo={ipo} />
      <RiskPanel ipo={ipo} />
      <ActionPlan ipo={ipo} />

      {/* Live Tape Engine — Section 19 */}
      <LiveTape ipo={ipo} />

      {/* Contrarian engine */}
      {(ipo.score?.contraryScore||0) >= 50 && (
        <Card style={{ background:C.purpleBg, border:`2px solid ${C.purpleBd}` }}>
          <div style={{ fontSize:10, fontWeight:900, color:C.purple, marginBottom:8, letterSpacing:"0.06em" }}>🎯 CONTRARIAN ENGINE</div>
          <div style={{ display:"flex", gap:14, alignItems:"center" }}>
            <div style={{ textAlign:"center" }}>
              <div style={{ fontSize:30, fontWeight:900, color:C.purple }}>{ipo.score.contraryScore}</div>
              <div style={{ fontSize:8, color:C.gray }}>score</div>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:11, color:"#374151", lineHeight:1.6, marginBottom:6 }}>
                {ipo.score.contraryScore >= 70
                  ? "Weak subscription + strong fundamentals. Post-listing base formation opportunity."
                  : "Monitor post-listing for IPO base entry."}
              </div>
              <div style={{ fontSize:12, fontWeight:800, color:C.purple }}>{ipo.score.postListingRating}</div>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
export default function IpoPage() {
  const [ipos, setIpos]     = useState<any[]>([])
  const [dash, setDash]     = useState<any>(null)
  const [loading, setLoad]  = useState(true)
  const [sel, setSel]       = useState<any>(null)
  const [view, setView]     = useState<"list"|"detail">("list")
  const [filter, setFilter] = useState("ALL")
  const [search, setSearch] = useState("")
  const [showUpload, setShowUpload] = useState(false)

  useEffect(() => {
    fetch("/api/ipo").then(r=>r.json()).then(d=>{
      setIpos(d.ipos||[]); setDash(d.dashboard); setLoad(false)
    }).catch(()=>setLoad(false))
  }, [])

  const filtered = ipos.filter(i => {
    const mf = filter==="ALL" || i.status===filter
    const ms = !search || i.name.toLowerCase().includes(search.toLowerCase()) || (i.sector||"").toLowerCase().includes(search.toLowerCase())
    return mf && ms
  })

  if (loading) return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:200, gap:10, color:C.gray, fontSize:13 }}>
      <div style={{ width:16, height:16, border:"2px solid #e5e7eb", borderTopColor:C.blue, borderRadius:"50%", animation:"spin 0.8s linear infinite" }} />
      Loading IPO Intelligence Engine…
    </div>
  )

  return (
    <div style={{ fontFamily:"-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>

      {/* HEADER */}
      <div style={{ background:"#0f172a", padding:"14px 20px", borderBottom:"1px solid #1e293b" }}>
        <div style={{ maxWidth:960, margin:"0 auto" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12, flexWrap:"wrap", gap:10 }}>
            <div>
              <div style={{ fontSize:17, fontWeight:900, color:"#f8fafc", letterSpacing:"-0.02em" }}>IPO Intelligence</div>
              <div style={{ fontSize:9, color:"#475569", marginTop:1 }}>Listing · Business · Management · Two Outcomes Only</div>
            </div>
            <div style={{ display:"flex", gap:5, flexWrap:"wrap" }}>
              {(["ALL","OPEN","UPCOMING","LISTED"] as const).map(f => (
                <button key={f} onClick={()=>setFilter(f)}
                  style={{ padding:"5px 11px", borderRadius:8, border:`1px solid ${filter===f?C.blue:"#1e293b"}`, background:filter===f?C.blue:"transparent", color:filter===f?"#fff":"#64748b", fontSize:10, fontWeight:700, cursor:"pointer" }}>
                  {f}
                </button>
              ))}
              <button onClick={()=>setShowUpload(v=>!v)}
                style={{ padding:"5px 11px", borderRadius:8, border:"1px solid #334155", background:showUpload?"#1e293b":"transparent", color:"#94a3b8", fontSize:10, fontWeight:700, cursor:"pointer" }}>
                📄 Upload PDF
              </button>
            </div>
          </div>

          {/* Global PDF upload */}
          {showUpload && (
            <div style={{ marginBottom:12 }}>
              <PdfUpload onData={d => {
                setShowUpload(false)
                // If we can match to an existing IPO, show it
                if (d.name) {
                  const match = ipos.find(i => i.name.toLowerCase().includes((d.name||"").toLowerCase()))
                  if (match) { setSel({...match,...d}); setView("detail") }
                }
              }} />
            </div>
          )}

          {/* Dashboard stats */}
          {dash && (
            <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:6 }}>
              {[
                { l:"Open",      v:dash.openCount,     c:"#4ade80" },
                { l:"Upcoming",  v:dash.upcomingCount, c:"#60a5fa" },
                { l:"Listed",    v:dash.listedCount,   c:"#c084fc" },
                { l:"Apply",     v:dash.hotIpos,       c:"#fbbf24" },
                { l:"Avoid",     v:dash.avoidCount,    c:"#f87171" },
                { l:"Avg Score", v:dash.avgScore,      c:"#4ade80" },
              ].map(s => (
                <div key={s.l} style={{ background:"rgba(255,255,255,0.04)", borderRadius:9, padding:"7px 0", textAlign:"center" }}>
                  <div style={{ fontSize:7, color:"#475569", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:2 }}>{s.l}</div>
                  <div style={{ fontSize:16, fontWeight:900, color:s.c }}>{s.v}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* BODY */}
      <div style={{ maxWidth:960, margin:"0 auto", padding:"16px 20px" }}>
        {view === "list" && (
          <>
            {/* Post-Listing Opportunity Monitor */}
            <PostListingMonitor />

            <input value={search} onChange={e=>setSearch(e.target.value)}
              placeholder="Search by name or sector…"
              style={{ width:"100%", boxSizing:"border-box", border:"1px solid #e5e7eb", borderRadius:10, padding:"10px 14px", fontSize:13, marginBottom:16, outline:"none", background:"#fff" }} />
            {filtered.length === 0 ? (
              <div style={{ textAlign:"center", padding:"60px 20px", color:C.gray }}>
                <div style={{ fontSize:32, marginBottom:8 }}>🔍</div>
                <div>No IPOs match</div>
              </div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(290px,1fr))", gap:14 }}>
                {filtered.map(ipo => (
                  <IpoCard key={ipo.name} ipo={ipo} onClick={()=>{ setSel(ipo); setView("detail") }} />
                ))}
              </div>
            )}
          </>
        )}
        {view === "detail" && sel && (
          <IpoDetail ipo={sel} onBack={()=>setView("list")} />
        )}
      </div>

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}*{box-sizing:border-box}`}</style>
    </div>
  )
}

