"use client"
import { useEffect, useMemo, useState } from "react"

/* Radar — cross-signal convergence grid. Pure aggregation over screens that already exist
   (DNA + Quality/Value, Rel. Strength, Breakout, Earnings beats). NO new signal, NO blended
   score. Shows which INDEPENDENT lenses each stock lights up — a research flag, not a buy call.
   Two modes: default convergence (2+ flags, never dumps the whole universe) + search override
   (type any symbol to see all its lenses even at 0 flags — the surprise-announcement lookup). */

const T = {
  green:"#16A34A", greenBg:"#EAF3DE", greenTx:"#3B6D11",
  blue:"#2563EB", blueBg:"#EEEDFE", blueTx:"#3C3489",
  amber:"#D97706", amberBg:"#FAEEDA", amberTx:"#854F0B",
  coral:"#D85A30", coralBg:"#FAECE7", coralTx:"#993C1D",
  red:"#DC2626", redBg:"#FCEBEB", redTx:"#A32D2D",
  text:"#111827", textSub:"#6B7280", textMeta:"#9CA3AF",
  border:"#E5E7EB", bg:"#F9FAFB", card:"#FFFFFF",
}
const num = (v:any):number|null => (v===null||v===undefined||v===""||isNaN(Number(v)))?null:Number(v)

type Row = {
  symbol:string; name:string;
  grade:string|null; dna_score:number|null;
  garp:boolean;
  rs:number|null;
  breakout:string|null;
  beatStreak:number|null; beatVerdict:string|null;
}

function Tag({txt,bg,fg}:{txt:string;bg:string;fg:string}){
  return <span style={{display:"inline-block",fontSize:10,fontWeight:600,background:bg,color:fg,
    padding:"2px 7px",borderRadius:6,whiteSpace:"nowrap"}}>{txt}</span>
}
const Dash = () => <span style={{color:T.textMeta}}>—</span>

export default function RadarScreen({ onStockSelect }:{ onStockSelect:(s:string)=>void }){
  const [rows,setRows]   = useState<Row[]>([])
  const [loading,setLoad]= useState(true)
  const [err,setErr]     = useState<string|null>(null)
  const [q,setQ]         = useState("")
  const [minFlags,setMin]= useState(2)
  const [sortBy,setSort] = useState<"flags"|"dna"|"rs">("flags")

  useEffect(()=>{ (async()=>{
    try{
      setLoad(true); setErr(null)
      // pull each screen's universe view in parallel; tolerate any one failing
      const [fnd, tech, bo, earn] = await Promise.all([
        fetch("/api/fundamentals/universe",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/technical-features",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/breakout-watch",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/earnings-surprise",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
      ])
      const map = new Map<string,Row>()
      const get = (s:string,name="") => {
        const k=s.toUpperCase()
        if(!map.has(k)) map.set(k,{symbol:k,name,grade:null,dna_score:null,garp:false,
          rs:null,breakout:null,beatStreak:null,beatVerdict:null})
        return map.get(k)!
      }
      // DNA + Quality/Value (GARP rule mirrors the Quality+Value screen)
      for(const s of (fnd?.stocks||[])){
        const r=get(s.symbol, s.company_name||s.name||"")
        r.grade=s.grade||null; r.dna_score=num(s.dna_score)
        const gradeOK = ["AAA","AA+","AA","A+","A"].includes(String(s.grade||""))
        const valOK   = num(s.pe_percentile)!==null ? Number(s.pe_percentile)<=40 : false
        const growOK  = num(s.np_yoy)!==null ? Number(s.np_yoy)>0
                        : num(s.sales_yoy)!==null ? Number(s.sales_yoy)>0 : false
        r.garp = gradeOK && valOK && growOK
      }
      // Relative Strength
      for(const s of (tech?.stocks||[])){
        const r=get(s.symbol); r.rs = num(s.rs_score)
      }
      // Breakout watch (route returns { data: rows } from technical_signals)
      const boList = bo?.data || bo?.stocks || bo?.watchlist || bo?.results || []
      for(const s of boList){
        const r=get(s.symbol||s.tradingsymbol)
        r.breakout = s.breakout_watch_tier || s.tier
          || (num(s.breakout_watch_score)!==null && Number(s.breakout_watch_score)>=48 ? "Watch" : null)
      }
      // Earnings beat streaks
      for(const s of (earn?.stocks||[])){
        const r=get(s.symbol)
        r.beatVerdict = s.verdict||null; r.beatStreak = num(s.streak)
      }
      setRows([...map.values()])
    }catch(e:any){ setErr(String(e?.message||e)) }
    finally{ setLoad(false) }
  })() },[])

  const flagCount = (r:Row) => {
    let c=0
    if(r.garp) c++
    if(r.rs!==null && r.rs>=80) c++
    if(r.breakout) c++
    if(r.beatVerdict==="BEAT" && (r.beatStreak||0)>=2) c++
    if(["AAA","AA+","AA"].includes(String(r.grade||""))) c++
    return c
  }

  const view = useMemo(()=>{
    const term=q.trim().toUpperCase()
    let list=rows.map(r=>({...r,fc:flagCount(r)}))
    if(term){ list=list.filter(r=>r.symbol.includes(term)||r.name.toUpperCase().includes(term)) }
    else    { list=list.filter(r=>r.fc>=minFlags) }
    list.sort((a,b)=> sortBy==="dna" ? (b.dna_score||0)-(a.dna_score||0)
                    : sortBy==="rs"  ? (b.rs||0)-(a.rs||0)
                    : (b.fc-a.fc) || (b.dna_score||0)-(a.dna_score||0))
    return list
  },[rows,q,minFlags,sortBy])

  const gradeColors = (g:string|null):[string,string] =>
    ["AAA","AA+","AA"].includes(String(g)) ? [T.greenBg,T.greenTx]
    : ["A+","A"].includes(String(g)) ? [T.blueBg,T.blueTx]
    : [T.redBg,T.redTx]

  return (
    <div style={{padding:"12px 16px",maxWidth:1100,margin:"0 auto"}}>
      <div style={{display:"flex",alignItems:"baseline",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
        <div style={{fontSize:18,fontWeight:800,color:T.text}}>Radar</div>
        <div style={{fontSize:12,color:T.textMeta}}>Which screens each stock lights up — convergence is a research flag, not a buy call.</div>
      </div>

      <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"12px 0"}}>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search any stock — e.g. ABCAPITAL"
          style={{flex:1,minWidth:200,padding:"8px 12px",border:`1px solid ${T.border}`,borderRadius:8,fontSize:13}} />
        <select value={minFlags} onChange={e=>setMin(Number(e.target.value))}
          style={{padding:"8px 10px",border:`1px solid ${T.border}`,borderRadius:8,fontSize:13}}>
          <option value={2}>2+ flags (convergence)</option>
          <option value={3}>3+ flags</option>
          <option value={1}>Any flag</option>
        </select>
        <select value={sortBy} onChange={e=>setSort(e.target.value as any)}
          style={{padding:"8px 10px",border:`1px solid ${T.border}`,borderRadius:8,fontSize:13}}>
          <option value="flags">Sort: most flags</option>
          <option value="dna">Sort: DNA score</option>
          <option value="rs">Sort: RS</option>
        </select>
      </div>

      <div style={{fontSize:11,color:T.textMeta,marginBottom:8}}>
        {q.trim()
          ? "Search mode — showing all matches regardless of flag count (look up a specific name)."
          : `Convergence mode — stocks lighting up across ${minFlags}+ independent screens. Type a symbol to look up any stock.`}
      </div>

      {loading && <div style={{padding:24,textAlign:"center",color:T.textSub,fontSize:13}}>Loading signals…</div>}
      {err && <div style={{padding:16,color:T.red,fontSize:13}}>Couldn't load: {err}</div>}

      {!loading && !err && (
        <div style={{overflowX:"auto",border:`1px solid ${T.border}`,borderRadius:12}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,minWidth:640}}>
            <thead><tr style={{background:T.bg,borderBottom:`1px solid ${T.border}`}}>
              {["Stock","DNA","Quality+Value","Rel. Strength","Breakout","Earnings","Flags"].map((h,i)=>(
                <th key={h} style={{textAlign:i===0?"left":"center",padding:"8px 10px",fontWeight:600,color:T.textSub}}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {view.map((r,i)=>{
                const [gb,gf]=gradeColors(r.grade)
                return (
                  <tr key={r.symbol} onClick={()=>onStockSelect(r.symbol)}
                    style={{borderBottom:`1px solid ${T.border}`,cursor:"pointer",background:i%2?"transparent":T.bg}}>
                    <td style={{padding:"8px 10px"}}>
                      <div style={{fontWeight:700,color:T.text}}>{r.symbol}</div>
                      <div style={{fontSize:10,color:T.textMeta,maxWidth:160,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{r.name}</div>
                    </td>
                    <td style={{textAlign:"center",padding:"8px 6px"}}>
                      {r.grade ? <>{<Tag txt={r.grade} bg={gb} fg={gf}/>} <span style={{color:T.textMeta,fontSize:10}}>{r.dna_score??""}</span></> : <Dash/>}
                    </td>
                    <td style={{textAlign:"center",padding:"8px 6px"}}>{r.garp ? <Tag txt="GARP" bg={T.greenBg} fg={T.greenTx}/> : <Dash/>}</td>
                    <td style={{textAlign:"center",padding:"8px 6px"}}>
                      {r.rs!==null && r.rs>=80 ? <Tag txt={`RS ${r.rs.toFixed(0)}`} bg={T.blueBg} fg={T.blueTx}/>
                        : r.rs!==null ? <span style={{color:T.textSub,fontSize:11}}>{r.rs.toFixed(0)}</span> : <Dash/>}
                    </td>
                    <td style={{textAlign:"center",padding:"8px 6px"}}>{r.breakout ? <Tag txt={r.breakout} bg={T.amberBg} fg={T.amberTx}/> : <Dash/>}</td>
                    <td style={{textAlign:"center",padding:"8px 6px"}}>
                      {r.beatVerdict==="BEAT" && (r.beatStreak||0)>=2 ? <Tag txt={`Beat ×${r.beatStreak}`} bg={T.coralBg} fg={T.coralTx}/>
                        : r.beatVerdict ? <span style={{color:T.textMeta,fontSize:10}}>{r.beatVerdict}</span> : <Dash/>}
                    </td>
                    <td style={{textAlign:"center",padding:"8px 6px"}}>
                      <span style={{display:"inline-flex",alignItems:"center",justifyContent:"center",minWidth:22,height:22,borderRadius:6,
                        fontWeight:700,fontSize:12,
                        background:r.fc>=4?T.greenBg:r.fc>=3?T.amberBg:T.bg,
                        color:r.fc>=4?T.greenTx:r.fc>=3?T.amberTx:T.textSub}}>{r.fc}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!view.length && (
            <div style={{textAlign:"center",padding:24,fontSize:13,color:T.textMeta}}>
              {q.trim() ? `No stock matches "${q.trim().toUpperCase()}".` : "No stocks meet this flag threshold — loosen it."}
            </div>
          )}
        </div>
      )}

      <div style={{fontSize:10,color:T.textMeta,marginTop:10,lineHeight:1.5}}>
        Each tag is membership in an independent screen — DNA grade, GARP value, relative strength, breakout watch, earnings beat-streak.
        Convergence means several lenses flagged the same name; it is <b>not</b> a blended probability or a buy rating. Research signal, not a buy call.
      </div>
    </div>
  )
}
