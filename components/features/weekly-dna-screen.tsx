"use client"
// components/features/weekly-dna-screen.tsx
// Weekly DNA Report — shows all stocks in technical_signals with DNA breakdown

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, Dna, TrendingUp, AlertTriangle } from "lucide-react"

const C = {
  green:"#16A34A",greenBg:"#F0FDF4",blue:"#2563EB",blueBg:"#EFF6FF",
  amber:"#D97706",amberBg:"#FFFBEB",purple:"#7C3AED",purpleBg:"#F5F3FF",
  red:"#DC2626",redBg:"#FEF2F2",gray:"#6B7280",grayBg:"#F9FAFB",
  text:"#111827",border:"#E5E7EB",surface:"#FFFFFF",
}
const n = (v: unknown) => parseFloat(String(v||0))||0
const pct = (v: unknown) => `${n(v)>=0?"+":""}${n(v).toFixed(1)}%`

function ScoreBadge({ score }: { score: number }) {
  const color = score>=75?C.green:score>=60?C.blue:score>=45?C.amber:C.gray
  const bg    = score>=75?C.greenBg:score>=60?C.blueBg:score>=45?C.amberBg:C.grayBg
  return <span style={{background:bg,color,fontWeight:700,fontSize:11,padding:"2px 8px",borderRadius:20,fontFamily:"monospace"}}>{Math.round(score)}</span>
}

export function WeeklyDNAScreen({ onStockSelect }: { onStockSelect?: (s: string) => void }) {
  const [loading, setLoading]   = useState(true)
  const [stocks, setStocks]     = useState<any[]>([])
  const [filter, setFilter]     = useState<"all"|"nr7"|"breakout"|"stage2">("all")
  const [lastUpdate, setLastUpdate] = useState<Date|null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch("/api/technical/screener?timeframe=daily&limit=100", { cache: "no-store" })
      const d = await r.json()
      const data = (d?.data ?? []) as any[]
      setStocks(data.filter((x:any) => !/^(ANTELOP|ACUTAAS)/i.test(x.symbol||"")))
      setLastUpdate(new Date())
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = stocks.filter(s => {
    if (filter === "nr7")      return s.is_nr7 || s.daily_nr7
    if (filter === "breakout") return n(s.buy_zone_score) >= 70
    if (filter === "stage2")   return s.stage === "2" || s.stage_label?.includes("2")
    return true
  })

  const nr7Count      = stocks.filter(s => s.is_nr7 || s.daily_nr7).length
  const breakoutCount = stocks.filter(s => n(s.buy_zone_score) >= 70).length

  return (
    <div style={{background:"#FAFAF8",minHeight:"100vh",paddingBottom:80}}>
      <div style={{maxWidth:900,margin:"0 auto",padding:"16px 16px 0"}}>

        {/* Header */}
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:14}}>
          <div>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <Dna size={20} color={C.purple}/>
              <span style={{fontSize:20,fontWeight:800,color:C.text}}>Weekly DNA Report</span>
            </div>
            <div style={{fontSize:11,color:C.gray,marginTop:2}}>
              {stocks.length} stocks · {nr7Count} NR7 setups · {breakoutCount} breakout-ready
              {lastUpdate ? ` · ${lastUpdate.toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit"})}` : ""}
            </div>
          </div>
          <button onClick={load} style={{display:"flex",alignItems:"center",gap:5,padding:"7px 12px",borderRadius:8,border:`1px solid ${C.border}`,background:C.surface,fontSize:12,color:C.gray,cursor:"pointer"}}>
            <RefreshCw size={12}/> Refresh
          </button>
        </div>

        {/* Summary cards */}
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:14}}>
          {[
            {label:"Total signals",  value:stocks.length,  color:C.blue,   bg:C.blueBg},
            {label:"NR7 coiling",    value:nr7Count,       color:C.purple, bg:C.purpleBg},
            {label:"Breakout ready", value:breakoutCount,  color:C.green,  bg:C.greenBg},
            {label:"Watch volume",   value:stocks.filter(s=>n(s.vol_expansion||s.volume_expansion)>0).length, color:C.amber, bg:C.amberBg},
          ].map(c=>(
            <div key={c.label} style={{background:c.bg,borderRadius:12,padding:"12px 14px",border:`1px solid ${c.color}20`}}>
              <div style={{fontSize:24,fontWeight:800,color:c.color}}>{c.value}</div>
              <div style={{fontSize:11,color:C.gray,marginTop:2}}>{c.label}</div>
            </div>
          ))}
        </div>

        {/* Filter tabs */}
        <div style={{display:"flex",gap:6,marginBottom:12}}>
          {([["all","All signals"],["nr7","NR7 only"],["breakout","Breakout ready"],["stage2","Stage 2"]] as const).map(([id,label])=>(
            <button key={id} onClick={()=>setFilter(id)} style={{padding:"6px 14px",borderRadius:20,border:`1px solid ${filter===id?C.blue:C.border}`,background:filter===id?C.blueBg:C.surface,color:filter===id?C.blue:C.gray,fontSize:12,fontWeight:filter===id?700:400,cursor:"pointer"}}>
              {label}
            </button>
          ))}
        </div>

        {/* Stock list */}
        {loading ? (
          <div style={{padding:"60px 0",textAlign:"center" as const,color:C.gray}}>
            <div style={{fontSize:30,marginBottom:8}}>🧬</div>
            <div>Loading DNA signals…</div>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{padding:"60px 0",textAlign:"center" as const,color:C.gray}}>
            <div style={{fontSize:30,marginBottom:8}}>📭</div>
            <div style={{fontSize:14,fontWeight:600}}>No stocks match this filter</div>
            <div style={{fontSize:12,marginTop:4}}>Run candle sync + signals engine to populate</div>
          </div>
        ) : filtered.map((s:any) => (
          <div key={s.symbol} onClick={()=>onStockSelect?.(s.symbol)}
            style={{background:C.surface,border:`1px solid ${C.border}`,borderLeft:`3px solid ${s.is_nr7||s.daily_nr7?C.purple:n(s.buy_zone_score)>=70?C.green:C.gray}`,borderRadius:12,padding:"12px 14px",marginBottom:8,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <div style={{flex:1,minWidth:0}}>
              <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                <span style={{fontSize:14,fontWeight:800,color:C.text}}>{s.symbol}</span>
                {(s.is_nr7||s.daily_nr7) && <span style={{fontSize:9,fontWeight:700,padding:"2px 7px",borderRadius:20,background:C.purpleBg,color:C.purple}}>NR7</span>}
                {n(s.buy_zone_score)>=70 && <span style={{fontSize:9,fontWeight:700,padding:"2px 7px",borderRadius:20,background:C.greenBg,color:C.green}}>BREAKOUT</span>}
                {s.above_ema200 && <span style={{fontSize:9,padding:"2px 7px",borderRadius:20,background:"#F0F9FF",color:"#0284C7",fontWeight:600}}>EMA200↑</span>}
              </div>
              <div style={{fontSize:11,color:C.gray}}>
                {s.company_name || s.name || s.symbol} · {s.stage_label||`Stage ${s.stage||"?"}`}
              </div>
              <div style={{display:"flex",gap:12,marginTop:5,fontSize:11}}>
                <span style={{color:n(s.momentum_6m)>=0?C.green:C.red}}>6M: {pct(s.momentum_6m)}</span>
                <span style={{color:C.gray}}>Vol: {n(s.vol_compression).toFixed(1)}x</span>
                <span style={{color:C.gray}}>Base: {s.base_months||0}M</span>
              </div>
            </div>
            <div style={{display:"flex",alignItems:"center",gap:12,flexShrink:0}}>
              <ScoreBadge score={n(s.buy_zone_score||s.convergence_score||s.score)}/>
              <TrendingUp size={14} color={C.gray}/>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
