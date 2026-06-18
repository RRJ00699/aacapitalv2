"use client"
// components/features/earnings-screen.tsx
// Earnings Acceleration — shows upcoming results + acceleration scores
// Uses: /api/earnings?view=upcoming, /api/intelligence/earnings

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, TrendingUp, Calendar, Zap } from "lucide-react"

const C = {
  green:"#16A34A",greenBg:"#F0FDF4",blue:"#2563EB",blueBg:"#EFF6FF",
  amber:"#D97706",amberBg:"#FFFBEB",red:"#DC2626",redBg:"#FEF2F2",
  gray:"#6B7280",grayBg:"#F9FAFB",text:"#111827",border:"#E5E7EB",surface:"#FFFFFF",
}
const n = (v: unknown) => parseFloat(String(v||0))||0

function Score({ val, label }: { val: number; label: string }) {
  const color = val>=70?C.green:val>=50?C.blue:val>=35?C.amber:C.gray
  return (
    <div style={{textAlign:"center" as const}}>
      <div style={{fontSize:20,fontWeight:800,color}}>{Math.round(val)||"—"}</div>
      <div style={{fontSize:9,color:C.gray,marginTop:2}}>{label}</div>
    </div>
  )
}

function SurpriseBadge({ type }: { type: string }) {
  if (!type) return null
  const cfg: Record<string,[string,string]> = {
    BEAT: [C.green,C.greenBg], MISS: [C.red,C.redBg], INLINE: [C.gray,C.grayBg],
  }
  const [color,bg] = cfg[type]||[C.gray,C.grayBg]
  return <span style={{fontSize:9,fontWeight:700,padding:"2px 7px",borderRadius:10,background:bg,color}}>{type}</span>
}

export function EarningsScreen({ onStockSelect }: { onStockSelect?: (s:string)=>void }) {
  const [loading, setLoading] = useState(true)
  const [upcoming, setUpcoming] = useState<any[]>([])
  const [accel, setAccel] = useState<any[]>([])
  const [tab, setTab] = useState<"upcoming"|"accelerating">("upcoming")
  const [lastUpdate, setLastUpdate] = useState<Date|null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [upRes, accRes] = await Promise.all([
        fetch("/api/earnings?view=upcoming&days=45").then(r=>r.json()).catch(()=>null),
        fetch("/api/intelligence/earnings?limit=30").then(r=>r.json()).catch(()=>null),
      ])
      setUpcoming(upRes?.data||[])
      const accData = accRes?.data ?? accRes ?? []
      setAccel(Array.isArray(accData)?accData:[])
      setLastUpdate(new Date())
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(()=>{ load() },[load])

  const tabs = [
    {id:"upcoming",     label:"📅 Upcoming results"},
    {id:"accelerating", label:"⚡ Accelerating earnings"},
  ]

  return (
    <div style={{background:"#FAFAF8",minHeight:"100vh",paddingBottom:80}}>
      <div style={{maxWidth:720,margin:"0 auto",padding:"16px 16px 0"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:14}}>
          <div>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <TrendingUp size={18} color={C.blue}/>
              <div style={{fontSize:20,fontWeight:800,color:C.text}}>Earnings intelligence</div>
            </div>
            <div style={{fontSize:11,color:C.gray,marginTop:2}}>
              Upcoming results · Acceleration scores{lastUpdate?` · ${lastUpdate.toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit"})}`:""}
            </div>
          </div>
          <button onClick={load} style={{display:"flex",alignItems:"center",gap:5,padding:"7px 12px",borderRadius:8,border:`1px solid ${C.border}`,background:C.surface,fontSize:12,color:C.gray,cursor:"pointer"}}>
            <RefreshCw size={12}/> Refresh
          </button>
        </div>

        {/* Tabs */}
        <div style={{borderBottom:`1px solid ${C.border}`,display:"flex",marginBottom:14}}>
          {tabs.map(t=>(
            <button key={t.id} onClick={()=>setTab(t.id as any)} style={{padding:"10px 14px",border:"none",fontSize:12,whiteSpace:"nowrap" as const,fontWeight:tab===t.id?700:500,color:tab===t.id?C.blue:C.gray,background:"transparent",cursor:"pointer",borderBottom:tab===t.id?`2px solid ${C.blue}`:"2px solid transparent"}}>
              {t.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{padding:"48px 0",textAlign:"center" as const,color:C.gray}}>
            <div style={{fontSize:24,marginBottom:8}}>📊</div>
            <div>Loading earnings data…</div>
          </div>
        ) : tab==="upcoming" ? (
          upcoming.length===0 ? (
            <div style={{padding:"48px 0",textAlign:"center" as const,color:C.gray}}>
              <div style={{fontSize:24,marginBottom:8}}>📅</div>
              <div style={{fontSize:14,fontWeight:600}}>No upcoming results in next 45 days</div>
              <div style={{fontSize:12,marginTop:4}}>Earnings events data will populate as results are announced</div>
            </div>
          ) : upcoming.map((e:any,i:number)=>(
            <div key={i} onClick={()=>onStockSelect?.(e.nse_symbol)}
              style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,marginBottom:10,padding:14,cursor:"pointer"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
                <div>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:3}}>
                    <span style={{fontSize:14,fontWeight:800,color:C.text}}>{e.nse_symbol}</span>
                    <SurpriseBadge type={e.last_surprise}/>
                    {e.consecutive_beats>1&&<span style={{fontSize:9,background:C.greenBg,color:C.green,padding:"2px 7px",borderRadius:10,fontWeight:700}}>{e.consecutive_beats}× beats</span>}
                  </div>
                  <div style={{fontSize:12,color:C.gray}}>{e.company_name}</div>
                  <div style={{display:"flex",alignItems:"center",gap:6,marginTop:4}}>
                    <Calendar size={11} color={C.gray}/>
                    <span style={{fontSize:11,color:C.text,fontWeight:600}}>{e.result_date}</span>
                    <span style={{fontSize:10,color:C.gray}}>({e.days_away}d away) · {e.quarter}</span>
                  </div>
                </div>
                <Score val={n(e.convergence_proxy)} label="Convergence"/>
              </div>
            </div>
          ))
        ) : (
          accel.length===0 ? (
            <div style={{padding:"48px 0",textAlign:"center" as const,color:C.gray}}>
              <div style={{fontSize:24,marginBottom:8}}>⚡</div>
              <div style={{fontSize:14,fontWeight:600}}>No acceleration scores yet</div>
              <div style={{fontSize:12,marginTop:4}}>Run: <code style={{background:C.grayBg,padding:"2px 6px",borderRadius:4}}>npx tsx _scripts/run-intelligence-scoring.ts --module=earnings</code></div>
            </div>
          ) : accel.map((e:any,i:number)=>(
            <div key={i} onClick={()=>onStockSelect?.(e.symbol||e.nse_symbol)}
              style={{background:C.surface,border:`1px solid ${C.border}`,borderLeft:`3px solid ${e.acceleration_status==="ACCELERATING"?C.green:e.acceleration_status==="TURNAROUND"?C.blue:C.amber}`,borderRadius:12,marginBottom:10,padding:14,cursor:"pointer"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
                <div>
                  <div style={{fontSize:14,fontWeight:800,color:C.text,marginBottom:2}}>{e.symbol||e.nse_symbol}</div>
                  <div style={{fontSize:12,color:C.gray,marginBottom:6}}>{e.company_name}</div>
                  <span style={{fontSize:10,fontWeight:700,padding:"3px 9px",borderRadius:20,background:e.acceleration_status==="ACCELERATING"?C.greenBg:C.blueBg,color:e.acceleration_status==="ACCELERATING"?C.green:C.blue}}>
                    {e.acceleration_status||"STABLE"}
                  </span>
                </div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
                  <Score val={n(e.revenue_acceleration_score)} label="Revenue accel"/>
                  <Score val={n(e.total_score)} label="Total score"/>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
