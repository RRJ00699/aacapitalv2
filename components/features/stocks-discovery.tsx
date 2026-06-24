"use client"
// components/features/stocks-discovery.tsx
// Unified discovery — powered by /api/stocks/discovery
// Single endpoint returns technical_signals + stock_fundamentals combined

import { useState, useEffect, useCallback, useRef } from "react"
import { Search, Star, RefreshCw, ChevronRight } from "lucide-react"

const T = {
  bg:"#FAFAF8", surface:"#FFFFFF", border:"#E5E7EB", hover:"#F8FAFC",
  text:"#111827", textSub:"#374151", meta:"#6B7280",
  green:"#16A34A", greenBg:"#F0FDF4",
  blue:"#2563EB",  blueBg:"#EFF6FF",
  amber:"#D97706", amberBg:"#FFFBEB",
  red:"#DC2626",   redBg:"#FEF2F2",
  teal:"#0D9488",  tealBg:"#F0FDFA",
  orange:"#EA580C",
  purple:"#7C3AED",purpleBg:"#F5F3FF",
  grayBg:"#F3F4F6",
}
const scoreColor = (s:number) =>
  s>=80?T.green:s>=65?T.teal:s>=50?T.amber:T.red
const n = (v:unknown) => parseFloat(String(v??0))||0
const pct = (v:unknown) => { const x=n(v); return x===0?"":`${x>0?"+":""}${x.toFixed(1)}%` }

function Ring({score,size=36}:{score:number;size?:number}) {
  const r=(size-5)/2,circ=2*Math.PI*r,dash=Math.min(1,score/100)*circ,col=scoreColor(score)
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{flexShrink:0}}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={T.border} strokeWidth={3.5}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={col} strokeWidth={3.5}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`}/>
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        style={{fontSize:10,fontWeight:800,fill:col}}>{score}</text>
    </svg>
  )
}

function Tag({text,color=T.blue}:{text:string;color?:string}) {
  return (
    <span style={{fontSize:9,fontWeight:700,padding:"2px 6px",borderRadius:4,
      background:color+"18",color,border:`1px solid ${color}30`,whiteSpace:"nowrap"}}>
      {text}
    </span>
  )
}

const TIER: Record<string,{label:string;color:string;bg:string}> = {
  "elite":   {label:"🏆 Elite",  color:T.purple,bg:T.purpleBg},
  "strong":  {label:"⭐ Strong", color:T.blue,  bg:T.blueBg},
  "decent":  {label:"🟡 Decent", color:T.amber, bg:T.amberBg},
  "unrated": {label:"· Unrated", color:T.meta,  bg:T.grayBg},
  "watch":   {label:"👁 Watch",  color:T.meta,  bg:T.grayBg},
}

function StockRow({stock,onSelect,onWatchlist,inWatchlist}:{
  stock:any;onSelect:(s:string)=>void;
  onWatchlist:(s:string,add:boolean)=>void;inWatchlist:boolean
}) {
  const sym   = stock.symbol??stock.tradingsymbol??""
  const name  = stock.company_name??sym
  const dna   = Math.round(n(stock.dna_score??0))
  const tier  = TIER[stock.predicted_tier??"watch"]
  const biz   = Math.round(n(stock.business_dna_score??0))
  const sm    = Math.round(n(stock.smart_money_score??0))
  const earn  = Math.round(n(stock.earnings_score??0))
  const roce  = n(stock.roce??0)
  const mom   = n(stock.momentum_6m??0)
  const sigs: string[] = stock.signals??[]
  const change= n(stock.change_pct??0)

  return (
    <div onClick={()=>onSelect(sym)}
      style={{display:"flex",alignItems:"center",gap:10,padding:"12px 16px",
        cursor:"pointer",borderBottom:`1px solid #F3F4F6`}}
      onMouseEnter={e=>(e.currentTarget.style.background=T.hover)}
      onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
      <Ring score={dna}/>
      <div style={{flex:1,minWidth:0}}>
        {/* Row 1 */}
        <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3,flexWrap:"wrap"}}>
          <span style={{fontSize:13,fontWeight:800,color:T.text}}>{sym}</span>
          <span style={{fontSize:9,fontWeight:700,padding:"2px 6px",borderRadius:4,
            background:tier.bg,color:tier.color,border:`1px solid ${tier.color}30`}}>
            {tier.label}
          </span>
          {stock.business_dna_grade && ["A+","A"].includes(stock.business_dna_grade) &&
            <Tag text={stock.business_dna_grade} color={T.green}/>}
          {sm>=75 && <Tag text="🏛 SM↑" color={T.green}/>}
          {stock.is_nr7&&<Tag text="NR7" color={T.orange}/>}
          {stock.mf_conviction && <Tag
            text={n(stock.mf_conviction_funds)>=2 ? `💎 New conviction ×${n(stock.mf_conviction_funds)}` : "💎 New conviction"}
            color={T.purple}/>}
        </div>
        {/* Row 2 */}
        <div style={{fontSize:10,color:T.meta,overflow:"hidden",whiteSpace:"nowrap",
          textOverflow:"ellipsis",maxWidth:240,marginBottom:3}}>{name}</div>
        {/* Row 3: scores */}
        <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
          {biz>0&&<span style={{fontSize:9,color:T.meta}}>Biz <b style={{color:scoreColor(biz)}}>{biz}</b></span>}
          {sm>0 &&<span style={{fontSize:9,color:T.meta}}>SM <b style={{color:scoreColor(sm)}}>{sm}</b></span>}
          {earn>0&&<span style={{fontSize:9,color:T.meta}}>EPS <b style={{color:scoreColor(earn)}}>{earn}</b></span>}
          {roce>0&&<span style={{fontSize:9,color:T.meta}}>ROCE <b style={{color:roce>=20?T.green:T.meta}}>{roce.toFixed(0)}%</b></span>}
          {stock.stage&&<span style={{fontSize:9,color:T.meta}}>Stage <b style={{color:stock.stage==="2"||stock.stage===2?T.green:T.meta}}>{stock.stage}</b></span>}
          {mom>10&&<span style={{fontSize:9,color:T.green,fontWeight:700}}>+{mom.toFixed(0)}% 6M</span>}
        </div>
        {/* Row 4: signal tags */}
        {sigs.length>0&&(
          <div style={{display:"flex",gap:4,marginTop:4,flexWrap:"wrap"}}>
            {sigs.slice(0,3).map((s:string)=><Tag key={s} text={s} color={T.teal}/>)}
          </div>
        )}
      </div>
      {change!==0&&(
        <span style={{fontSize:11,fontWeight:700,color:change>=0?T.green:T.red,flexShrink:0}}>
          {pct(change)}
        </span>
      )}
      <button onClick={e=>{e.stopPropagation();onWatchlist(sym,!inWatchlist)}}
        style={{background:"none",border:"none",cursor:"pointer",padding:"2px 4px",flexShrink:0}}>
        <Star size={14} fill={inWatchlist?T.amber:"none"} color={inWatchlist?T.amber:T.meta}/>
      </button>
      <ChevronRight size={12} color={T.meta} style={{flexShrink:0}}/>
    </div>
  )
}

function Section({title,count,badge,desc,children}:{
  title:string;count?:number;badge?:string;desc?:string;children:React.ReactNode
}) {
  const [open,setOpen]=useState(true)
  return (
    <div style={{marginBottom:8}}>
      <button onClick={()=>setOpen(o=>!o)}
        style={{width:"100%",display:"flex",alignItems:"center",justifyContent:"space-between",
          padding:"8px 16px",background:T.grayBg,border:"none",cursor:"pointer",
          borderTop:`1px solid ${T.border}`,borderBottom:open?`1px solid ${T.border}`:"none"}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <span style={{fontSize:11,fontWeight:700,color:T.textSub,textTransform:"uppercase" as const,letterSpacing:"0.07em"}}>
            {title} {count!=null&&<span style={{color:T.meta,fontWeight:400}}>({count})</span>}
          </span>
          {badge&&<span style={{fontSize:9,padding:"1px 6px",borderRadius:3,background:T.blueBg,color:T.blue,fontWeight:700}}>{badge}</span>}
        </div>
        <span style={{fontSize:11,color:T.meta}}>{open?"▲":"▼"}</span>
      </button>
      {open&&<div style={{background:T.surface}}>
        {desc&&<div style={{padding:"5px 16px 2px",fontSize:10,color:T.meta}}>{desc}</div>}
        {children}
      </div>}
    </div>
  )
}

function Skel({count=3}:{count?:number}) {
  return <>{Array.from({length:count}).map((_,i)=>
    <div key={i} style={{height:80,background:"#F3F4F6",margin:"1px 0",opacity:0.5+i*0.15}}/>
  )}</>
}
function Empty({msg,sub}:{msg:string;sub?:string}) {
  return (
    <div style={{padding:"24px 16px",textAlign:"center",color:T.meta}}>
      <div style={{fontSize:12,color:T.textSub,fontWeight:600}}>{msg}</div>
      {sub&&<div style={{fontSize:11,marginTop:3}}>{sub}</div>}
    </div>
  )
}

export function StocksDiscovery({onStockSelect}:{onStockSelect:(s:string)=>void}) {
  const [stocks,   setStocks]   = useState<any[]>([])
  const [watchlist,setWatchlist]= useState<string[]>([])
  const [regime,   setRegime]   = useState("NORMAL")
  const [loading,  setLoading]  = useState(true)
  const [filter,   setFilter]   = useState("all")
  const [query,    setQuery]    = useState("")
  const [ts,       setTs]       = useState("")
  const [hasMb,    setHasMb]    = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async()=>{
    setLoading(true)
    try {
      const [dRes,wlRes,snapRes] = await Promise.all([
        fetch("/api/stocks/discovery",    {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/watchlists",          {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/market/snapshot",     {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
      ])
      const data = dRes?.data ?? []
      setStocks(data)
      setHasMb(dRes?.has_session9_cols ?? false)
      setWatchlist((wlRes?.stocks??[]).map((s:any)=>s.symbol))
      setRegime((snapRes?.data?.regime??snapRes?.data?.market_regime??"NORMAL").toUpperCase())
      setTs(new Date().toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit"}))
    } catch{}
    setLoading(false)
  },[])

  useEffect(()=>{load()},[load])

  const toggleWatchlist = useCallback(async(sym:string,add:boolean)=>{
    setWatchlist(p=>add?[...p,sym]:p.filter(s=>s!==sym))
    await fetch("/api/watchlists",{method:add?"POST":"DELETE",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol:sym})}).catch(()=>{})
  },[])

  const q=query.trim().toLowerCase()
  const filt=(arr:any[])=>!q?arr:arr.filter(s=>
    (s.symbol??s.tradingsymbol??"").toLowerCase().includes(q)||
    (s.company_name??"").toLowerCase().includes(q))

  const all       = filt([...stocks].sort((a,b)=>n(b.dna_score)-n(a.dna_score)))
  const elite     = filt(stocks.filter(s=>s.predicted_tier==="elite"))
  const strong    = filt(stocks.filter(s=>s.predicted_tier==="strong"))
  const smartMoney= filt(stocks.filter(s=>n(s.smart_money_score)>=70||
    (s.smart_money_signal??"").toLowerCase().includes("accum"))
    .sort((a,b)=>n(b.smart_money_score)-n(a.smart_money_score)))
  const earnings  = filt(stocks.filter(s=>n(s.earnings_score)>=65)
    .sort((a,b)=>n(b.earnings_score)-n(a.earnings_score)))
  const technical = filt(stocks.filter(s=>s.is_nr7||s.nr7||s.vr7))
  const conviction= filt(stocks.filter(s=>s.mf_conviction)
    .sort((a,b)=>n(b.mf_conviction_funds)-n(a.mf_conviction_funds)))
  const wlStocks  = filt(stocks.filter(s=>watchlist.includes(s.symbol??s.tradingsymbol))
    .concat(watchlist.filter(sym=>!stocks.some(s=>s.symbol===sym)).map(sym=>({symbol:sym,predicted_tier:"watch"}))))

  const FILTERS=[
    {id:"all",        label:"All",            count:all.length},
    {id:"elite",      label:"🏆 Elite",       count:elite.length},
    {id:"strong",     label:"⭐ Strong",      count:strong.length},
    {id:"smartmoney", label:"🏛 Smart Money", count:smartMoney.length},
    {id:"conviction", label:"💎 New conviction", count:conviction.length},
    {id:"earnings",   label:"📈 Earnings",    count:earnings.length},
    {id:"technical",  label:"⚡ Technical",   count:technical.length},
    {id:"watchlist",  label:"⭐ Watchlist",   count:wlStocks.length},
  ]

  const show=(s:string)=>filter==="all"||filter===s
  const rp=(stock:any)=>({stock,onSelect:onStockSelect,onWatchlist:toggleWatchlist,
    inWatchlist:watchlist.includes(stock.symbol??stock.tradingsymbol??"")})

  const regimeCfg:{[k:string]:{color:string;msg:string}}={
    HOT:    {color:T.green,msg:"HOT market — engine at peak accuracy (89% positive, 2024)"},
    NORMAL: {color:T.teal, msg:"NORMAL market — deploy selectively, 50-70% capital"},
    CAUTION:{color:T.amber,msg:"CAUTION — high conviction only, protect capital"},
    COLD:   {color:T.red,  msg:"COLD market (2026, 42% positive) — only highest-conviction plays"},
    BEARISH:{color:T.red,  msg:"BEARISH — capital preservation, no fresh positions"},
  }
  const rc=regimeCfg[regime]??regimeCfg.NORMAL

  return (
    <div style={{background:T.bg,minHeight:"100vh",paddingBottom:80}}>
      {/* Search */}
      <div style={{background:T.surface,borderBottom:`1px solid ${T.border}`,
        padding:"10px 14px",position:"sticky",top:44,zIndex:20}}>
        <div style={{display:"flex",alignItems:"center",gap:8,background:T.grayBg,
          borderRadius:10,padding:"7px 12px"}}>
          <Search size={14} color={T.meta}/>
          <input ref={inputRef} value={query} onChange={e=>setQuery(e.target.value)}
            onKeyDown={e=>{if(e.key==="Enter"&&query.trim())onStockSelect(query.trim().toUpperCase())}}
            placeholder="Search or type symbol + Enter to open"
            style={{flex:1,background:"none",border:"none",outline:"none",fontSize:13,color:T.text}}/>
          {query&&<button onClick={()=>setQuery("")}
            style={{background:"none",border:"none",cursor:"pointer",color:T.meta,fontSize:14}}>×</button>}
          <button onClick={load} style={{background:"none",border:"none",cursor:"pointer",color:T.meta}}>
            <RefreshCw size={13}/></button>
        </div>
        <div style={{display:"flex",gap:6,marginTop:8,overflowX:"auto",paddingBottom:2}}>
          {FILTERS.map(f=>(
            <button key={f.id} onClick={()=>setFilter(f.id)} style={{
              padding:"4px 12px",borderRadius:20,fontSize:11,cursor:"pointer",whiteSpace:"nowrap",
              border:`1px solid ${filter===f.id?T.blue:T.border}`,
              background:filter===f.id?T.blueBg:"transparent",
              color:filter===f.id?T.blue:T.meta,
              fontWeight:filter===f.id?700:400}}>
              {f.label} {f.count>0&&<span style={{opacity:.7}}>({f.count})</span>}
            </button>
          ))}
          {ts&&<span style={{fontSize:10,color:T.meta,marginLeft:"auto",alignSelf:"center",whiteSpace:"nowrap"}}>{ts} IST</span>}
        </div>
      </div>

      {/* Regime banner */}
      <div style={{padding:"7px 16px",background:rc.color+"12",borderBottom:`1px solid ${rc.color}30`,
        fontSize:11,color:rc.color,fontWeight:600}}>
        ⚡ {rc.msg}
        {!hasMb&&<span style={{marginLeft:8,fontWeight:400,opacity:.8}}>
          · Tiers reflect business quality (ROCE/ROE/debt/promoter), not return predictions
        </span>}
      </div>

      <div style={{maxWidth:800,margin:"0 auto"}}>
        {/* All */}
        {filter==="all"&&(
          <Section title="All stocks" count={all.length} badge="by DNA score">
            {loading?<Skel count={5}/>:all.length===0
              ?<Empty msg="No stocks found" sub="Check if generate_signals.py has run and technical_signals table has data"/>
              :all.slice(0,50).map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* 5x */}
        {show("elite")&&filter!=="all"&&(
          <Section title="🏆 Elite quality" count={elite.length} badge="ROCE≥20 · promoter≥55 · strong B/S"
            desc="Long base (12M+) + volume compression + 6M momentum. Pattern from 120K+ historical winner entry points.">
            {loading?<Skel/>:elite.length===0
              ?<Empty msg="No 5x candidates" sub={hasMb?"Signals are current — no stocks match threshold":"Run generate_signals.py to compute mb_score"}/>
              :elite.map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* 2x */}
        {show("strong")&&filter!=="all"&&(
          <Section title="⭐ Strong quality" count={strong.length} badge="ROCE≥15 · sound fundamentals"
            desc="Base forming (6-12M) + volume compressing. Earlier stage than 5x.">
            {loading?<Skel/>:strong.length===0
              ?<Empty msg="No 2x candidates" sub={hasMb?"No stocks meet threshold currently":"Run generate_signals.py to compute mb_score"}/>
              :strong.map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* Smart Money */}
        {show("smartmoney")&&filter!=="all"&&(
          <Section title="🏛 Smart Money" count={smartMoney.length} badge="SM score≥70"
            desc="Institutional accumulation from 147,861 bulk/block deal records (10yr). WABAG scored SM=91 before its move.">
            {loading?<Skel/>:smartMoney.length===0
              ?<Empty msg="No smart money signals" sub="Data from NSE bulk/block deals via stock_fundamentals table"/>
              :smartMoney.map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* New conviction — the one backtested signal */}
        {show("conviction")&&filter!=="all"&&(
          <Section title="💎 New conviction" count={conviction.length} badge="a conviction fund just initiated"
            desc="A high-conviction active fund (Nippon/Quant/Canara/PPFAS small-mid-flexi) initiated a brand-new position. Backtested edge: EDGE+ in 3 of 4 years, strongest 1–3 months — regime-sensitive. A research signal, not a guarantee. ×N = multiple funds bought independently (stronger).">
            {loading?<Skel/>:conviction.length===0
              ?<Empty msg="No fresh conviction buys in window" sub="Flags expire after 90 days; refresh MF holdings monthly to keep current"/>
              :conviction.map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* Earnings */}
        {show("earnings")&&filter!=="all"&&(
          <Section title="📈 Earnings Momentum" count={earnings.length} badge="earnings_score≥65"
            desc="Revenue and PAT accelerating QoQ. Run run-intelligence-scoring.ts quarterly to refresh.">
            {loading?<Skel/>:earnings.length===0
              ?<Empty msg="No earnings signals" sub="Run node scripts/earnings-seed.mjs to populate earnings data"/>
              :earnings.map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* Technical */}
        {show("technical")&&filter!=="all"&&(
          <Section title="⚡ Technical Setup" count={technical.length} badge="NR7 / VR7"
            desc="Use as ENTRY TIMING — after a stock passes 5x/2x or Smart Money filter, wait for NR7 to enter.">
            {loading?<Skel/>:technical.length===0
              ?<Empty msg="No NR7/VR7 setups today"/>
              :technical.map(s=><StockRow key={s.symbol} {...rp(s)}/>)}
          </Section>
        )}
        {/* Watchlist */}
        {show("watchlist")&&filter!=="all"&&(
          <Section title="⭐ Watchlist" count={wlStocks.length}>
            {loading?<Skel count={2}/>:wlStocks.length===0
              ?<Empty msg="No stocks in watchlist" sub="Tap ⭐ on any stock to add"/>
              :wlStocks.map(s=><StockRow key={s.symbol??s.tradingsymbol} {...rp(s)}/>)}
          </Section>
        )}
        {!loading&&all.length===0&&query&&(
          <Empty msg={`No results for "${query}"`} sub="Press Enter to open the stock directly"/>
        )}
      </div>
    </div>
  )
}
