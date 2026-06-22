"use client"
// components/features/ipo-listing-dashboard.tsx
// Reads ONLY from Neon ipo_intelligence — no live scraping, no Yahoo
// Matches IPO Quick Profit Playbook card format exactly

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, Zap, TrendingUp, TrendingDown, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react"

const C = {
  bg:"#FAFAF8",surface:"#FFFFFF",border:"#E5E7EB",muted:"#F8FAFC",
  text:"#111827",sub:"#374151",meta:"#6B7280",
  green:"#16A34A",greenBg:"#F0FDF4",greenBd:"#BBF7D0",
  blue:"#2563EB", blueBg:"#EFF6FF", blueBd:"#BFDBFE",
  amber:"#D97706",amberBg:"#FFFBEB",amberBd:"#FDE68A",
  red:"#DC2626",  redBg:"#FEF2F2",  redBd:"#FECACA",
  teal:"#0D9488", tealBg:"#F0FDFA", tealBd:"#99F6E4",
  purple:"#7C3AED",purpleBg:"#F5F3FF",purpleBd:"#DDD6FE",
}

const PLAY: Record<string,{label:string;emoji:string;color:string;bg:string;bd:string;stop:number;target:number;hold:string}> = {
  BUY_AT_OPEN:    {label:"BUY AT OPEN",   emoji:"🟢",color:C.green, bg:C.greenBg, bd:C.greenBd, stop:4,  target:20, hold:"30 min → EOD"},
  WAIT_FOR_VWAP:  {label:"WAIT VWAP",     emoji:"🟡",color:C.amber, bg:C.amberBg, bd:C.amberBd, stop:5,  target:15, hold:"10:30 AM → EOD"},
  BUY_PANIC_DIP:  {label:"PANIC DIP",     emoji:"🔵",color:C.blue,  bg:C.blueBg,  bd:C.blueBd,  stop:6,  target:20, hold:"Day 1–3"},
  BUY_AFTER_DAY3: {label:"DAY 3+",        emoji:"⚪",color:C.teal,  bg:C.tealBg,  bd:C.tealBd,  stop:5,  target:12, hold:"1 week"},
  BUY_AFTER_ANCHOR:{label:"ANCHOR UNLOCK",emoji:"⚪",color:C.teal,  bg:C.tealBg,  bd:C.tealBd,  stop:8,  target:25, hold:"1–4 weeks"},
  BUY_PEER:       {label:"BUY PEER",      emoji:"🟠",color:"#EA580C",bg:"#FFF7ED", bd:"#FED7AA", stop:5,  target:15, hold:"normal"},
  AVOID:          {label:"AVOID",          emoji:"🔴",color:C.red,   bg:C.redBg,   bd:C.redBd,   stop:0,  target:0,  hold:"—"},
}
const playOf = (p?:string) => PLAY[p??""] ?? {label:p??"—",emoji:"⚪",color:C.meta,bg:"#F1F5F9",bd:C.border,stop:0,target:0,hold:"—"}

const n = (v:unknown) => parseFloat(String(v??0))||0
const fmt = (v:unknown,d=0) => n(v).toLocaleString("en-IN",{maximumFractionDigits:d})
const pct = (v:unknown) => { const x=n(v); return `${x>=0?"+":""}${x.toFixed(1)}%` }
const cr  = (v:unknown) => `₹${fmt(v)}Cr`

// The correct GMP field from ipo_intelligence (set by import_chittorgarh.py)
const gmpOf = (ipo:any): number|null => {
  const v = ipo.gmp_pct_t1 ?? ipo.gmp_day_before_pct ?? ipo.gmp_pct_t3 ?? null
  return v != null ? n(v) : null
}

const statusOf = (ipo:any) => {
  const now=Date.now()
  const o=ipo.open_date    ?new Date(ipo.open_date).getTime():0
  const c=ipo.close_date   ?new Date(ipo.close_date).getTime():0
  const l=ipo.listing_date ?new Date(ipo.listing_date).getTime():0
  if(l&&now>=l)          return "LISTED"
  if(c&&now>c&&l)        return "ALLOTMENT"
  if(o&&now>=o&&now<=c)  return "OPEN"
  const hasListedData =
    ipo.listing_open!=null || ipo.listing_day_close!=null ||
    ipo.return_listing_open!=null || ipo.return_day1_close!=null ||
    ipo.return_day7!=null || ipo.return_day30!=null
  if(!o&&!c&&!l && hasListedData) return "LISTED"
  return "UPCOMING"
}

const daysLeft = (d?:string|null) => {
  if(!d) return null
  const diff=new Date(d).getTime()-Date.now()
  return diff<0?null:Math.ceil(diff/86400000)
}

// ── Ring ───────────────────────────────────────────────────────────────────────
function Ring({v,size=44}:{v:number;size?:number}) {
  const r=(size-5)/2,circ=2*Math.PI*r
  const col=v>=75?C.green:v>=55?C.teal:v>=40?C.amber:C.red
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{flexShrink:0}}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#E2E8F0" strokeWidth={4}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={col} strokeWidth={4}
        strokeDasharray={`${Math.min(1,v/100)*circ} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`}/>
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        style={{fontSize:11,fontWeight:900,fill:col}}>{v>0?Math.round(v):"—"}</text>
    </svg>
  )
}

function PlayBadge({play}:{play:string}) {
  const p=playOf(play)
  return <span style={{fontSize:10,fontWeight:800,padding:"3px 9px",borderRadius:6,
    background:p.bg,color:p.color,border:`1px solid ${p.bd}`}}>{p.emoji} {p.label}</span>
}

function GmpBadge({ipo}:{ipo:any}) {
  const g=gmpOf(ipo); if(g===null) return null
  const col=g>20?C.green:g>5?C.teal:g>0?C.amber:C.red
  const mom=(ipo.gmp_momentum??"").toLowerCase()
  const up=mom.includes("ris")||mom.includes("up")
  const dn=mom.includes("fall")||mom.includes("col")
  const implied=n(ipo.issue_price)>0?Math.round(n(ipo.issue_price)*(1+g/100)):null
  return (
    <span style={{display:"inline-flex",alignItems:"center",gap:4,padding:"3px 9px",
      borderRadius:8,background:col+"15",border:`1px solid ${col}30`,fontSize:11,fontWeight:800,color:col}}>
      GMP {g>=0?"+":""}{g.toFixed(0)}%
      {implied&&<span style={{fontSize:10}}>≈₹{fmt(implied)}</span>}
      {up&&<TrendingUp size={10} color={C.green}/>}
      {dn&&<TrendingDown size={10} color={C.red}/>}
    </span>
  )
}

function SubBar({label,value,max}:{label:string;value:unknown;max:number}) {
  const v=n(value); if(!v||v<=0) return null
  const pct=Math.min(100,(v/Math.max(max,v,1))*100)
  const col=v>=100?C.green:v>=30?C.teal:v>=10?C.amber:C.red
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
      <span style={{fontSize:9,fontWeight:700,color:C.meta,width:22,flexShrink:0}}>{label}</span>
      <div style={{flex:1,height:5,background:"#E2E8F0",borderRadius:3}}>
        <div style={{width:`${pct}%`,height:"100%",background:col,borderRadius:3}}/>
      </div>
      <span style={{fontSize:11,fontWeight:900,color:col,minWidth:40,textAlign:"right"}}>{v.toFixed(1)}x</span>
    </div>
  )
}

function Stat({label,value,color=C.sub}:{label:string;value:string;color?:string}) {
  return (
    <div style={{background:C.muted,borderRadius:8,padding:"7px 10px",border:`1px solid ${C.border}`,textAlign:"center",minWidth:72}}>
      <div style={{fontSize:9,color:C.meta,fontWeight:600,marginBottom:2,textTransform:"uppercase" as const,letterSpacing:"0.05em"}}>{label}</div>
      <div style={{fontSize:15,fontWeight:900,color}}>{value}</div>
    </div>
  )
}

// ── The Playbook Card ──────────────────────────────────────────────────────────
function PlaybookCard({ipo,expanded,onToggle}:{ipo:any;expanded:boolean;onToggle:()=>void}) {
  const status  = statusOf(ipo)
  const play    = playOf(ipo.play_recommendation ?? ipo.suggested_action ?? "")
  const lqi     = Math.round(n(ipo.lqi_final ?? ipo.lqi ?? 0))
  const gmp     = gmpOf(ipo)
  const daysO   = status==="OPEN"?daysLeft(ipo.close_date):status==="UPCOMING"?daysLeft(ipo.open_date):null
  const maxSub  = Math.max(n(ipo.qib_subscription_x),n(ipo.nii_subscription_x),n(ipo.rii_subscription_x),30)
  const hasSub  = n(ipo.qib_subscription_x)>0||n(ipo.nii_subscription_x)>0||n(ipo.rii_subscription_x)>0
  const stop    = n(ipo.play_stop_loss_pct ?? play.stop)
  const target  = n(ipo.play_target_pct   ?? play.target)
  const hold    = ipo.play_hold_window    ?? play.hold
  const conf    = Math.round(n(ipo.play_confidence ?? 0))

  const statusCfg:{[k:string]:React.CSSProperties} = {
    OPEN:      {background:C.greenBg,color:C.green,border:`1px solid ${C.greenBd}`},
    UPCOMING:  {background:C.blueBg, color:C.blue, border:`1px solid ${C.blueBd}`},
    ALLOTMENT: {background:C.amberBg,color:C.amber,border:`1px solid ${C.amberBd}`},
    LISTED:    {background:C.muted,  color:C.meta, border:`1px solid ${C.border}`},
  }

  // Parse play reasons
  let reasons: string[] = []
  if (ipo.play_reasons) {
    try { reasons = typeof ipo.play_reasons==="string" ? JSON.parse(ipo.play_reasons) : ipo.play_reasons }
    catch {}
  }

  return (
    <div style={{background:C.surface,borderLeft:`3px solid ${play.color}`,
      border:`1px solid ${play.color==="AVOID"?C.redBd:C.border}`,
      borderRadius:14,marginBottom:12,overflow:"hidden"}}>

      {/* ── Card header (always visible — The Playbook Card format) ─────── */}
      <div onClick={onToggle} style={{padding:"14px 16px",cursor:"pointer"}}>
        <div style={{display:"flex",alignItems:"flex-start",gap:12}}>
          <Ring v={lqi}/>
          <div style={{flex:1,minWidth:0}}>
            {/* Row 1: Company + play + status */}
            <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap",marginBottom:4}}>
              <span style={{fontSize:15,fontWeight:900,color:C.text}}>{ipo.company_name}</span>
              <PlayBadge play={ipo.play_recommendation??ipo.suggested_action??""}/>
              {status!=="LISTED"&&(
                <span style={{fontSize:10,fontWeight:700,padding:"2px 7px",borderRadius:5,...(statusCfg[status]||{})}}>
                  {status}
                </span>
              )}
              {conf>0&&<span style={{fontSize:10,color:C.meta}}>Confidence: {conf}%</span>}
              {ipo.is_sme&&<span style={{fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:3,background:C.purpleBg,color:C.purple,border:`1px solid ${C.purpleBd}`}}>SME</span>}
            </div>

            {/* Row 2: Price + lot + size + sector + days */}
            <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginBottom:5}}>
              {n(ipo.issue_price)>0&&<span style={{fontSize:12,fontWeight:800,color:C.sub}}>₹{fmt(ipo.issue_price)}</span>}
              {n(ipo.lot_size)>0&&<span style={{fontSize:11,color:C.meta}}>Lot {fmt(ipo.lot_size)}</span>}
              {n(ipo.issue_size_cr)>0&&<span style={{fontSize:11,color:C.meta}}>{cr(ipo.issue_size_cr)}</span>}
              {ipo.sector&&<span style={{fontSize:10,color:C.meta,background:"#F1F5F9",padding:"1px 7px",borderRadius:4}}>{ipo.sector}</span>}
              {daysO!=null&&daysO>=0&&(
                <span style={{fontSize:10,fontWeight:700,color:daysO<=2?C.amber:C.meta}}>
                  {status==="OPEN"?`Closes in ${daysO}d`:`Opens in ${daysO}d`}
                </span>
              )}
            </div>

            {/* Row 3: GMP + stop/target/hold pills */}
            <div style={{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center"}}>
              <GmpBadge ipo={ipo}/>
              {stop>0&&<span style={{fontSize:10,color:C.red,fontWeight:700}}>Stop: −{stop}%</span>}
              {target>0&&<span style={{fontSize:10,color:C.green,fontWeight:700}}>Target: +{target}%</span>}
              {hold&&hold!=="—"&&<span style={{fontSize:10,color:C.meta}}>Hold: {hold}</span>}
            </div>
          </div>

          {/* Right: BRLM + anchors + expand */}
          <div style={{textAlign:"right",flexShrink:0}}>
            {ipo.brlm_score!=null&&<div style={{fontSize:10,fontWeight:800,color:n(ipo.brlm_score)>=70?C.green:C.amber,marginBottom:2}}>BRLM {n(ipo.brlm_score).toFixed(0)}</div>}
            {n(ipo.anchor_tier1_count)>0&&<div style={{fontSize:10,color:C.teal,fontWeight:700,marginBottom:2}}>🏛 {n(ipo.anchor_tier1_count)} tier-1</div>}
            {expanded?<ChevronUp size={14} color={C.meta}/>:<ChevronDown size={14} color={C.meta}/>}
          </div>
        </div>

        {/* Subscription bars */}
        {hasSub&&(
          <div style={{marginTop:10}}>
            <SubBar label="QIB" value={ipo.qib_subscription_x} max={maxSub}/>
            <SubBar label="NII" value={ipo.nii_subscription_x} max={maxSub}/>
            <SubBar label="RII" value={ipo.rii_subscription_x} max={maxSub}/>
            {n(ipo.total_subscription_x)>0&&(
              <div style={{fontSize:10,color:C.sub,textAlign:"right",marginTop:2,fontWeight:800}}>
                Total: {n(ipo.total_subscription_x).toFixed(1)}x
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Expanded detail (tap to expand) ──────────────────────────────── */}
      {expanded&&(
        <div style={{borderTop:`1px solid ${C.border}`,background:C.muted,padding:"14px 16px"}}>

          {/* Why this play — The Playbook Card "Why" section */}
          {reasons.length>0&&(
            <div style={{background:play.bg,border:`1px solid ${play.bd}`,borderRadius:8,
              padding:"10px 14px",marginBottom:12}}>
              <div style={{fontSize:11,fontWeight:800,color:play.color,marginBottom:6}}>
                {play.emoji} Why this play:
              </div>
              {reasons.map((r:string,i:number)=>(
                <div key={i} style={{fontSize:11,color:play.color,marginBottom:3}}>→ {r}</div>
              ))}
              {status==="OPEN"&&(
                <div style={{marginTop:8,paddingTop:8,borderTop:`1px solid ${play.bd}30`,fontSize:11,color:play.color}}>
                  <div>10:00 AM → Watch OI buy/sell</div>
                  <div>10:15 AM → Decision deadline</div>
                  <div>10:25 AM → Enter or walk away</div>
                </div>
              )}
            </div>
          )}

          {/* Key numbers */}
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:12}}>
            {lqi>0&&<Stat label="LQI" value={String(lqi)} color={lqi>=70?C.green:lqi>=50?C.teal:C.amber}/>}
            {n(ipo.buy_at_open_score)>0&&<Stat label="Open Score" value={n(ipo.buy_at_open_score).toFixed(0)} color={n(ipo.buy_at_open_score)>=70?C.green:C.amber}/>}
            {n(ipo.prob_10pct_profit)>0&&<Stat label="P(+10%)" value={`${n(ipo.prob_10pct_profit).toFixed(0)}%`} color={C.green}/>}
            {n(ipo.prob_loss_gt10)>0&&<Stat label="P(loss)" value={`${n(ipo.prob_loss_gt10).toFixed(0)}%`} color={C.red}/>}
            {n(ipo.ipo_pe)>0&&<Stat label="P/E" value={n(ipo.ipo_pe).toFixed(0)}/>}
            {n(ipo.peer_median_pe)>0&&<Stat label="Peer P/E" value={n(ipo.peer_median_pe).toFixed(0)}/>}
            {gmp!=null&&<Stat label="GMP T-1" value={pct(gmp)} color={gmp>=0?C.green:C.red}/>}
          </div>

          {/* GMP trend */}
          {[ipo.gmp_pct_t10,ipo.gmp_pct_t7,ipo.gmp_pct_t5,ipo.gmp_pct_t3,ipo.gmp_pct_t1].some(v=>v!=null)&&(
            <div style={{padding:"10px 12px",background:C.surface,borderRadius:8,border:`1px solid ${C.border}`,marginBottom:10}}>
              <div style={{fontSize:10,fontWeight:700,color:C.meta,marginBottom:8}}>GMP T−10 → T−1</div>
              <div style={{display:"flex",gap:4,alignItems:"flex-end",height:40}}>
                {([{l:"T-10",v:ipo.gmp_pct_t10},{l:"T-7",v:ipo.gmp_pct_t7},{l:"T-5",v:ipo.gmp_pct_t5},{l:"T-3",v:ipo.gmp_pct_t3},{l:"T-1",v:ipo.gmp_pct_t1??ipo.gmp_day_before_pct}] as {l:string;v:unknown}[])
                  .filter(p=>p.v!=null).map(p=>{
                    const val=n(p.v),col=val>=20?C.green:val>=5?C.teal:val>=0?C.amber:C.red
                    return (
                      <div key={p.l} style={{flex:1,display:"flex",flexDirection:"column" as const,alignItems:"center",gap:2}}>
                        <span style={{fontSize:8,fontWeight:700,color:col}}>{val>=0?"+":""}{val.toFixed(0)}%</span>
                        <div style={{width:"100%",height:Math.max(4,Math.min(34,Math.abs(val)/60*34)),background:col,borderRadius:2,minHeight:4}}/>
                        <span style={{fontSize:8,color:C.meta}}>{p.l}</span>
                      </div>
                    )
                  })}
              </div>
            </div>
          )}

          {/* Optional context (collapsible sections from playbook) */}
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:10}}>
            {/* Fundamentals */}
            {n(ipo.ipo_pe)>0&&<Stat label="P/E" value={n(ipo.ipo_pe).toFixed(0)}/>}
            {n(ipo.ofs_pct)>0&&<Stat label="OFS%" value={`${n(ipo.ofs_pct).toFixed(0)}%`} color={n(ipo.ofs_pct)>60?C.red:C.sub}/>}
            {n(ipo.fresh_issue_ratio)>0&&<Stat label="Fresh%" value={`${(n(ipo.fresh_issue_ratio)*100).toFixed(0)}%`} color={C.green}/>}
          </div>

          {/* Anchor detail */}
          {(n(ipo.anchor_tier1_count)>0||n(ipo.anchor_count)>0)&&(
            <div style={{padding:"8px 12px",background:C.tealBg,borderRadius:8,border:`1px solid ${C.tealBd}`,marginBottom:10}}>
              <span style={{fontSize:11,fontWeight:700,color:C.teal}}>
                🏛 Anchors: {n(ipo.anchor_count)} total · {n(ipo.anchor_tier1_count)} Tier-1 (LIC/SBI/ICICI/Nippon)
              </span>
              {ipo.anchor_stalwart_names&&<div style={{fontSize:10,color:C.teal,marginTop:3,opacity:.8}}>{ipo.anchor_stalwart_names}</div>}
              {ipo.anchor_lock30_date&&<div style={{fontSize:9,color:C.teal,marginTop:2}}>Unlock: {ipo.anchor_lock30_date} (30d) · {ipo.anchor_lock90_date||"—"} (90d)</div>}
            </div>
          )}

          {/* BRLM history */}
          {ipo.brlm_names&&(
            <div style={{padding:"10px 12px",background:C.surface,borderRadius:8,border:`1px solid ${C.border}`,marginBottom:10}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div>
                  <div style={{fontSize:9,fontWeight:700,color:C.meta,textTransform:"uppercase" as const}}>BRLM</div>
                  <div style={{fontSize:12,fontWeight:700,color:C.text}}>{ipo.brlm_names}</div>
                  {n(ipo.brlm_pct_negative)>20&&<div style={{fontSize:10,color:C.red,marginTop:1}}>{n(ipo.brlm_pct_negative).toFixed(0)}% negative listing history</div>}
                </div>
                {ipo.brlm_score&&<div style={{textAlign:"right"}}>
                  <div style={{fontSize:20,fontWeight:900,color:n(ipo.brlm_score)>=70?C.green:C.amber}}>{n(ipo.brlm_score).toFixed(0)}</div>
                  {ipo.brlm_avg_listing_gain&&<div style={{fontSize:9,color:C.green,fontWeight:700}}>avg +{n(ipo.brlm_avg_listing_gain).toFixed(1)}%</div>}
                </div>}
              </div>
            </div>
          )}

          {/* Post-listing returns */}
          {status==="LISTED"&&(
            <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
              {ipo.return_listing_open!=null&&<Stat label="Day 1 Open" value={pct(ipo.return_listing_open)} color={n(ipo.return_listing_open)>=0?C.green:C.red}/>}
              {ipo.return_day7!=null&&<Stat label="Day 7" value={pct(ipo.return_day7)} color={n(ipo.return_day7)>=0?C.green:C.red}/>}
              {ipo.return_day30!=null&&<Stat label="Day 30" value={pct(ipo.return_day30)} color={n(ipo.return_day30)>=0?C.green:C.red}/>}
              {ipo.return_day90!=null&&<Stat label="Day 90" value={pct(ipo.return_day90)} color={n(ipo.return_day90)>=0?C.green:C.red}/>}
            </div>
          )}

          {/* Operator risk warning */}
          {n(ipo.operator_risk_score)>=60&&(
            <div style={{display:"flex",alignItems:"center",gap:8,padding:"8px 12px",background:C.redBg,borderRadius:8,border:`1px solid ${C.redBd}`,fontSize:11,color:C.red,marginTop:8}}>
              <AlertTriangle size={13}/>
              <span><b>Operator Risk {n(ipo.operator_risk_score).toFixed(0)}/100</b> — avoid</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Skel() {
  return <div style={{background:"#F1F5F9",borderRadius:14,height:110,marginBottom:12,opacity:.7}}/>
}

function BrlmBoard({ipos}:{ipos:any[]}) {
  const map: Record<string,{name:string;score:number;avg:number;count:number}> = {}
  ipos.filter(i=>i.brlm_names&&i.brlm_score!=null).forEach(i=>{
    const name=String(i.brlm_names).split(",")[0].trim()
    if(!map[name]) map[name]={name,score:n(i.brlm_score),avg:n(i.brlm_avg_listing_gain??0),count:0}
    map[name].count++
  })
  const list=Object.values(map).sort((a,b)=>b.score-a.score).slice(0,10)
  if(!list.length) return <div style={{padding:24,textAlign:"center",color:C.meta,fontSize:12}}>Run compute_brlm_scores.py to populate</div>
  return <div>{list.map((b,i)=>(
    <div key={b.name} style={{display:"flex",alignItems:"center",gap:12,padding:"12px 16px",borderBottom:`1px solid #F3F4F6`}}>
      <div style={{fontSize:16,fontWeight:900,color:C.meta,width:24}}>{i+1}</div>
      <div style={{flex:1}}>
        <div style={{fontSize:13,fontWeight:700,color:C.text}}>{b.name}</div>
        <div style={{fontSize:10,color:C.meta}}>{b.count} IPOs tracked</div>
      </div>
      <div style={{textAlign:"right"}}>
        <div style={{fontSize:20,fontWeight:900,color:b.score>=70?C.green:C.amber}}>{b.score.toFixed(0)}</div>
        {b.avg>0&&<div style={{fontSize:10,color:C.green,fontWeight:700}}>avg +{b.avg.toFixed(1)}%</div>}
      </div>
    </div>
  ))}</div>
}

export function IpoListingDashboard() {
  const [ipos,    setIpos]    = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState("command")
  const [expanded,setExpanded]= useState<number|null>(null)
  const [search,  setSearch]  = useState("")
  const [ts,      setTs]      = useState("")

  const load = useCallback(async()=>{
    setLoading(true)
    try {
      const d=await fetch("/api/ipo/playbook?limit=100",{cache:"no-store"}).then(r=>r.json())
      setIpos(d.ipos??[])
      setTs(new Date().toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit"}))
    }catch{setIpos([])}
    setLoading(false)
  },[])

  useEffect(()=>{load()},[load])

  const q   = search.trim().toLowerCase()
  const all = ipos.filter(i=>!q||(i.company_name??"").toLowerCase().includes(q))

  const command  = all.filter(i=>{const s=statusOf(i);const p=i.play_recommendation??"";return(s==="OPEN"||s==="UPCOMING"||s==="ALLOTMENT")&&p!=="AVOID"})
  const openIpos = all.filter(i=>statusOf(i)==="OPEN")
  const upcoming = all.filter(i=>statusOf(i)==="UPCOMING")
  const listed   = all.filter(i=>{const s=statusOf(i);return s==="LISTED"||s==="ALLOTMENT"})
    .sort((a,b)=>new Date(b.listing_date??0).getTime()-new Date(a.listing_date??0).getTime())

  const TABS=[
    {id:"command", label:"⚡ Command",      count:command.length},
    {id:"open",    label:"📋 Open Now",     count:openIpos.length},
    {id:"upcoming",label:"📅 Upcoming",     count:upcoming.length},
    {id:"listed",  label:"📈 Post-Listing", count:listed.length},
    {id:"brlm",    label:"🏆 BRLM",         count:null},
  ]

  const active=tab==="command"?command:tab==="open"?openIpos:tab==="upcoming"?upcoming:listed

  return (
    <div style={{background:C.bg,minHeight:"100vh",paddingBottom:80}}>
      <div style={{maxWidth:720,margin:"0 auto",padding:"16px 16px 0"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div>
            <div style={{display:"flex",alignItems:"center",gap:8,fontSize:20,fontWeight:900,color:C.text}}>
              <Zap size={18} color={C.blue}/> IPO Command Center
            </div>
            <div style={{fontSize:10,color:C.meta}}>
              {ts?`Updated ${ts} IST`:"Loading..."} · Data from Chittorgarh Pro via ipo_intelligence
            </div>
          </div>
          <div style={{display:"flex",gap:8}}>
            <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search..."
              style={{padding:"6px 10px",borderRadius:8,border:`1px solid ${C.border}`,fontSize:12,outline:"none",width:110}}/>
            <button onClick={load} style={{display:"flex",alignItems:"center",gap:4,padding:"6px 12px",
              borderRadius:8,border:`1px solid ${C.border}`,background:C.surface,fontSize:11,color:C.meta,cursor:"pointer"}}>
              <RefreshCw size={11}/> Refresh
            </button>
          </div>
        </div>

        {/* Accuracy strip */}
        <div style={{background:"#fff",border:"1px solid #E5E7EB",borderRadius:14,
          padding:"12px 16px",marginBottom:14,display:"flex",gap:16,flexWrap:"wrap",alignItems:"center"}}>
          <div>
            <div style={{fontSize:8,color:"#475569",textTransform:"uppercase" as const,letterSpacing:"0.1em",marginBottom:1}}>
              AACapital IPO Engine · base rates measured on 333 IPOs
            </div>
            <div style={{fontSize:12,fontWeight:900,color:"#0F172A"}}>Decision support · selection shows no reliable edge</div>
          </div>
          {[{l:"Buy at open → close",v:"+0.6%",s:"49% win · ≈ flat"},{l:"Below-GMP listing",v:"+8.5%",s:"≈ market (+8.7%)"},{l:"Above-GMP listing",v:"+13.3%",s:"6-mo avg"}].map(s=>(
            <div key={s.l} style={{textAlign:"center"}}>
              <div style={{fontSize:8,color:"#64748b",marginBottom:1}}>{s.l}</div>
              <div style={{fontSize:17,fontWeight:900,color:"#0F172A"}}>{s.v}</div>
              <div style={{fontSize:8,color:"#475569"}}>{s.s}</div>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div style={{display:"flex",gap:6,marginBottom:12,overflowX:"auto",paddingBottom:2}}>
          {TABS.map(t=>(
            <button key={t.id} onClick={()=>{setTab(t.id);setExpanded(null)}} style={{
              padding:"6px 14px",borderRadius:20,fontSize:11,cursor:"pointer",whiteSpace:"nowrap",
              border:`1px solid ${tab===t.id?C.blue:C.border}`,
              background:tab===t.id?C.blueBg:"transparent",
              color:tab===t.id?C.blue:C.meta,fontWeight:tab===t.id?700:400}}>
              {t.label}{t.count!=null&&t.count>0?` (${t.count})`:""}
            </button>
          ))}
        </div>

        {/* Content */}
        {tab==="brlm"?(
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,overflow:"hidden"}}>
            <div style={{padding:"12px 16px",borderBottom:`1px solid ${C.border}`}}>
              <div style={{fontSize:14,fontWeight:800,color:C.text}}>BRLM Leaderboard</div>
              <div style={{fontSize:11,color:C.meta}}>Refreshed by compute_brlm_scores.py · Track record drives outcome probability</div>
            </div>
            {loading?<Skel/>:<BrlmBoard ipos={ipos}/>}
          </div>
        ):loading?[1,2,3].map(i=><Skel key={i}/>)
        :active.length===0?(
          <div style={{padding:"48px 0",textAlign:"center",color:C.meta}}>
            <TrendingUp size={32} color="#CBD5E1" style={{margin:"0 auto 12px",display:"block"}}/>
            <div style={{fontSize:14,color:C.sub,fontWeight:600,marginBottom:6}}>
              {tab==="command"?"No active BUY plays right now":tab==="open"?"No IPOs open for subscription":
               tab==="upcoming"?"No upcoming IPOs in database":"No recently listed IPOs"}
            </div>
            <div style={{fontSize:12,color:C.meta}}>
              {tab==="command"?"Export from Chittorgarh Pro → run import_chittorgarh.py → ipo_play_selector.py":""}
            </div>
          </div>
        ):(
          active.map((ipo,i)=>(
            <PlaybookCard key={ipo.id??i} ipo={ipo}
              expanded={expanded===(ipo.id??i)}
              onToggle={()=>setExpanded(expanded===(ipo.id??i)?null:(ipo.id??i))}/>
          ))
        )}

        <div style={{fontSize:10,color:"#CBD5E1",textAlign:"center",marginTop:8,lineHeight:1.6}}>
          Data: Chittorgarh Pro → ipo_intelligence · Engine: import_chittorgarh.py + ipo_play_selector.py<br/>
          Listing day: listing_day_monitor.py (Kite API) · Not SEBI registered advice
        </div>
      </div>
    </div>
  )
}
