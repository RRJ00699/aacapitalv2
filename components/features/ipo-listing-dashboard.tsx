"use client"
// components/features/ipo-listing-dashboard.tsx — Complete rebuild
// Live prices · Fixed GMP · Price band · Subscription · All plays

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, TrendingUp, TrendingDown, Zap, AlertTriangle } from "lucide-react"

const C = {
  bg:"#FAFAF8",surface:"#FFFFFF",border:"#E5E7EB",slateBg:"#F8FAFC",
  text:"#111827",textSub:"#374151",textMeta:"#6B7280",slate:"#64748B",
  green:"#16A34A",greenBg:"#F0FDF4",greenBd:"#BBF7D0",
  blue:"#2563EB", blueBg:"#EFF6FF", blueBd:"#BFDBFE",
  amber:"#D97706",amberBg:"#FFFBEB",amberBd:"#FDE68A",
  red:"#DC2626",  redBg:"#FEF2F2",  redBd:"#FECACA",
  teal:"#0D9488", tealBg:"#F0FDFA", tealBd:"#99F6E4",
  orange:"#EA580C",orangeBg:"#FFF7ED",
  purple:"#7C3AED",purpleBg:"#F5F3FF",purpleBd:"#DDD6FE",
}

const PLAY: Record<string,{label:string;emoji:string;color:string;bg:string;bd:string;tip:string}> = {
  BUY_AT_OPEN:    {label:"BUY AT OPEN",   emoji:"🟢",color:C.green, bg:C.greenBg, bd:C.greenBd, tip:"Buy at market open. Exit EOD or on VWAP cross. Stop: −4% from open."},
  WAIT_FOR_VWAP:  {label:"WAIT VWAP",     emoji:"🟡",color:C.amber, bg:C.amberBg, bd:C.amberBd, tip:"Wait for VWAP crossover + 1.5x volume. Don't chase the open."},
  BUY_PANIC_DIP:  {label:"BUY PANIC DIP", emoji:"🔵",color:C.blue,  bg:C.blueBg,  bd:C.blueBd,  tip:"Listed below GMP + tier-1 anchors = buy the panic. Hold 3 days."},
  BUY_AFTER_DAY3: {label:"BUY DAY 3+",    emoji:"⚪",color:C.teal,  bg:C.tealBg,  bd:C.tealBd,  tip:"Day 1-2 distribution ends. Enter Day 3 close when selling slows."},
  APPLY:          {label:"APPLY",          emoji:"🟢",color:C.green, bg:C.greenBg, bd:C.greenBd, tip:"Apply for allotment — high conviction pre-listing."},
  WATCH:          {label:"WATCH",          emoji:"🟡",color:C.amber, bg:C.amberBg, bd:C.amberBd, tip:"Monitor GMP and subscription. Apply only if signals improve."},
  AVOID:          {label:"AVOID",          emoji:"🔴",color:C.red,   bg:C.redBg,   bd:C.redBd,   tip:"Insufficient conviction. Skip this IPO."},
}

const n   = (v:unknown) => parseFloat(String(v??0))||0
const fmt = (v:unknown,d=0) => n(v).toLocaleString("en-IN",{maximumFractionDigits:d})
const cr  = (v:unknown) => `₹${fmt(v)}Cr`
const pct = (v:unknown) => { const x=n(v); return `${x>=0?"+":""}${x.toFixed(1)}%` }
const inr = (v:unknown) => n(v)>0?`₹${fmt(v,0)}`:"—"

const gmpOf = (ipo:any): number|null => {
  const v = ipo.gmp_pct_t1 ?? ipo.gmp_day_before_pct ?? ipo.gmp_pct_t3
            ?? ipo.gmp_pct_t5 ?? ipo.gmp_pct ?? ipo.gmp_percentage ?? null
  return v!=null ? n(v) : null
}

const statusOf = (ipo:any) => {
  const now=Date.now()
  const o=ipo.open_date    ? new Date(ipo.open_date).getTime()    : 0
  const c=ipo.close_date   ? new Date(ipo.close_date).getTime()   : 0
  const l=ipo.listing_date ? new Date(ipo.listing_date).getTime() : 0
  if (l&&now>=l)          return "LISTED"
  if (c&&now>c&&l)        return "ALLOTMENT"
  if (o&&now>=o&&now<=c)  return "OPEN"
  return "UPCOMING"
}

const daysLeft = (d?:string|null) => {
  if (!d) return null
  const diff=new Date(d).getTime()-Date.now()
  return diff<0?null:Math.ceil(diff/86400000)
}

// ── Reusable components ────────────────────────────────────────────────────────
function Ring({lqi}:{lqi:number}) {
  const sz=44,r=(sz-6)/2,circ=2*Math.PI*r
  const col=lqi>=75?C.green:lqi>=55?C.teal:lqi>=40?C.amber:C.red
  return (
    <svg width={sz} height={sz} viewBox={`0 0 ${sz} ${sz}`} style={{flexShrink:0}}>
      <circle cx={sz/2} cy={sz/2} r={r} fill="none" stroke="#E2E8F0" strokeWidth={4}/>
      <circle cx={sz/2} cy={sz/2} r={r} fill="none" stroke={col} strokeWidth={4}
        strokeDasharray={`${Math.min(1,lqi/100)*circ} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${sz/2} ${sz/2})`}/>
      <text x={sz/2} y={sz/2} textAnchor="middle" dominantBaseline="central"
        style={{fontSize:11,fontWeight:900,fill:col}}>{lqi>0?Math.round(lqi):"—"}</text>
    </svg>
  )
}

function PlayBadge({play}:{play:string}) {
  const p=PLAY[play]??{label:play||"—",emoji:"⚪",color:C.slate,bg:"#F1F5F9",bd:C.border,tip:""}
  return <span style={{fontSize:10,fontWeight:800,padding:"3px 8px",borderRadius:6,
    background:p.bg,color:p.color,border:`1px solid ${p.bd}`}}>{p.emoji} {p.label}</span>
}

function GmpChip({ipo}:{ipo:any}) {
  const g=gmpOf(ipo); if(g===null) return null
  const mom=(ipo.gmp_momentum??"").toLowerCase()
  const up=mom.includes("ris")||mom.includes("up")
  const dn=mom.includes("fall")||mom.includes("col")
  const col=g>20?C.green:g>5?C.teal:g>0?C.amber:C.red
  const price=n(ipo.issue_price)>0?Math.round(n(ipo.issue_price)*(1+g/100)):null
  return (
    <div style={{display:"flex",alignItems:"center",gap:5,padding:"4px 10px",
      borderRadius:8,background:col+"12",border:`1px solid ${col}30`}}>
      <span style={{fontSize:11,fontWeight:800,color:col}}>GMP {g>=0?"+":""}{g.toFixed(0)}%</span>
      {price&&<span style={{fontSize:10,color:col,fontWeight:700}}>≈{inr(price)}</span>}
      {up&&<TrendingUp size={11} color={C.green}/>}
      {dn&&<TrendingDown size={11} color={C.red}/>}
    </div>
  )
}

function SubBar({label,value,max=100}:{label:string;value:number|null;max?:number}) {
  if(!value||value<=0) return null
  const p=Math.min(100,(value/Math.max(max,value))*100)
  const col=value>=100?C.green:value>=30?C.teal:value>=10?C.amber:C.red
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
      <span style={{fontSize:9,fontWeight:700,color:C.textMeta,width:24,flexShrink:0}}>{label}</span>
      <div style={{flex:1,height:6,background:"#E2E8F0",borderRadius:3}}>
        <div style={{width:`${p}%`,height:"100%",background:col,borderRadius:3}}/>
      </div>
      <span style={{fontSize:11,fontWeight:900,color:col,minWidth:42,textAlign:"right"}}>{value.toFixed(1)}x</span>
    </div>
  )
}

function Chip({label,value,color=C.textSub}:{label:string;value:string;color?:string}) {
  return (
    <div style={{background:C.slateBg,borderRadius:8,padding:"8px 10px",
      border:`1px solid ${C.border}`,textAlign:"center",minWidth:80}}>
      <div style={{fontSize:9,color:C.textMeta,fontWeight:600,marginBottom:2,
        textTransform:"uppercase" as const,letterSpacing:"0.05em"}}>{label}</div>
      <div style={{fontSize:15,fontWeight:900,color}}>{value}</div>
    </div>
  )
}

// ── IpoCard ────────────────────────────────────────────────────────────────────
function IpoCard({ipo,expanded,onToggle}:{ipo:any;expanded:boolean;onToggle:()=>void}) {
  const [livePrice,setLivePrice] = useState<number|null>(null)
  const [priceLoad,setPriceLoad] = useState(false)
  const status = statusOf(ipo)
  const play   = PLAY[ipo.play_recommendation??ipo.suggested_action??""]
                 ??{label:"—",emoji:"⚪",color:C.slate,bg:"#F1F5F9",bd:C.border,tip:""}
  const lqi    = Math.round(n(ipo.lqi_final??ipo.lqi??0))
  const gmp    = gmpOf(ipo)
  const daysO  = status==="OPEN"?daysLeft(ipo.close_date):status==="UPCOMING"?daysLeft(ipo.open_date):null
  const maxSub = Math.max(n(ipo.qib_subscription_x),n(ipo.nii_subscription_x),n(ipo.rii_subscription_x),30)
  const hasSub = ipo.qib_subscription_x||ipo.nii_subscription_x||ipo.rii_subscription_x

  // Fetch live price for listed IPOs
  useEffect(()=>{
    if(!ipo.symbol||status!=="LISTED") return
    setPriceLoad(true)
    fetch(`/api/broker/quote?sym=${ipo.symbol}&exchange=NSE`,{cache:"no-store"})
      .then(r=>r.json()).then(d=>{if(d.last_price>0)setLivePrice(d.last_price)})
      .catch(()=>{}).finally(()=>setPriceLoad(false))
  },[ipo.symbol,status])

  const liveGain = livePrice&&n(ipo.issue_price)>0
    ? ((livePrice-n(ipo.issue_price))/n(ipo.issue_price))*100 : null

  return (
    <div style={{background:C.surface,border:`1px solid ${ipo.play_recommendation==="AVOID"?C.redBd:C.border}`,
      borderLeft:`3px solid ${play.color}`,borderRadius:14,marginBottom:10,overflow:"hidden"}}>

      {/* Header */}
      <div onClick={onToggle} style={{padding:"14px 16px",cursor:"pointer"}}>
        <div style={{display:"flex",alignItems:"flex-start",gap:12}}>
          <Ring lqi={lqi}/>
          <div style={{flex:1,minWidth:0}}>
            {/* Name + play + status */}
            <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap",marginBottom:5}}>
              <span style={{fontSize:15,fontWeight:900,color:C.text}}>{ipo.company_name}</span>
              <PlayBadge play={ipo.play_recommendation??ipo.suggested_action??""}/>
              {status!=="LISTED"&&(
                <span style={{fontSize:10,fontWeight:700,padding:"2px 7px",borderRadius:5,
                  ...(status==="OPEN"?{background:C.greenBg,color:C.green,border:`1px solid ${C.greenBd}`}
                    :status==="UPCOMING"?{background:C.blueBg,color:C.blue,border:`1px solid ${C.blueBd}`}
                    :{background:C.amberBg,color:C.amber,border:`1px solid ${C.amberBd}`})
                }}>{status}</span>
              )}
              {ipo.is_sme&&<span style={{fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:3,
                background:C.purpleBg,color:C.purple,border:`1px solid ${C.purpleBd}`}}>SME</span>}
            </div>

            {/* Price + lot + size + sector + days */}
            <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginBottom:6}}>
              {n(ipo.issue_price)>0&&<span style={{fontSize:12,fontWeight:800,color:C.textSub}}>₹{fmt(ipo.issue_price)}</span>}
              {n(ipo.lot_size)>0&&<span style={{fontSize:11,color:C.textMeta}}>Lot {fmt(ipo.lot_size)}</span>}
              {n(ipo.issue_size_cr)>0&&<span style={{fontSize:11,color:C.textMeta}}>{cr(ipo.issue_size_cr)}</span>}
              {ipo.sector&&<span style={{fontSize:10,color:C.textMeta,background:"#F1F5F9",padding:"1px 7px",borderRadius:4}}>{ipo.sector}</span>}
              {daysO!=null&&daysO>=0&&(
                <span style={{fontSize:10,fontWeight:700,color:daysO<=2?C.amber:C.textMeta}}>
                  {status==="OPEN"?`Closes in ${daysO}d`:`Opens in ${daysO}d`}
                </span>
              )}
            </div>

            {/* GMP + live price */}
            <div style={{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center"}}>
              <GmpChip ipo={ipo}/>
              {status==="LISTED"&&ipo.symbol&&(
                priceLoad?<span style={{fontSize:10,color:C.textMeta}}>Loading price...</span>
                :livePrice?(
                  <div style={{display:"flex",alignItems:"center",gap:6}}>
                    <span style={{fontSize:14,fontWeight:900,color:C.text}}>₹{fmt(livePrice)}</span>
                    {liveGain!=null&&(
                      <span style={{fontSize:12,fontWeight:800,
                        color:liveGain>=0?C.green:C.red,
                        padding:"2px 7px",borderRadius:6,
                        background:liveGain>=0?C.greenBg:C.redBg}}>
                        {pct(liveGain)} vs issue
                      </span>
                    )}
                    <span style={{fontSize:9,color:C.textMeta,padding:"1px 5px",borderRadius:3,background:"#F1F5F9"}}>LIVE</span>
                  </div>
                ):null
              )}
              {status==="LISTED"&&ipo.listing_date&&(
                <span style={{fontSize:10,color:C.textMeta}}>Listed {ipo.listing_date}</span>
              )}
            </div>
          </div>

          {/* Right: BRLM + anchors + expand */}
          <div style={{textAlign:"right",flexShrink:0}}>
            {ipo.brlm_score!=null&&(
              <div style={{fontSize:10,fontWeight:800,color:n(ipo.brlm_score)>=70?C.green:C.amber,marginBottom:2}}>
                BRLM {n(ipo.brlm_score).toFixed(0)}
              </div>
            )}
            {n(ipo.anchor_tier1_count)>0&&(
              <div style={{fontSize:10,color:C.teal,fontWeight:700,marginBottom:2}}>
                🏛 {n(ipo.anchor_tier1_count)} tier-1
              </div>
            )}
            <div style={{fontSize:11,color:C.textMeta}}>{expanded?"▲":"▼"}</div>
          </div>
        </div>

        {/* Subscription bars */}
        {hasSub&&(
          <div style={{marginTop:10}}>
            <SubBar label="QIB" value={ipo.qib_subscription_x} max={maxSub}/>
            <SubBar label="NII" value={ipo.nii_subscription_x} max={maxSub}/>
            <SubBar label="RII" value={ipo.rii_subscription_x} max={maxSub}/>
            {n(ipo.total_subscription_x)>0&&(
              <div style={{fontSize:10,color:C.textSub,textAlign:"right",marginTop:2,fontWeight:800}}>
                Total: {n(ipo.total_subscription_x).toFixed(1)}x subscribed
              </div>
            )}
          </div>
        )}
      </div>

      {/* Expanded */}
      {expanded&&(
        <div style={{borderTop:`1px solid ${C.border}`,background:C.slateBg,padding:"14px 16px"}}>

          {/* Play tip */}
          {play.tip&&(
            <div style={{background:play.bg,border:`1px solid ${play.bd}`,borderRadius:8,
              padding:"10px 14px",marginBottom:12,fontSize:12,color:play.color,fontWeight:600}}>
              {play.emoji} {play.tip}
              <div style={{display:"flex",gap:12,marginTop:5}}>
                {ipo.play_stop_loss_pct&&<span style={{fontSize:11,color:C.red,fontWeight:700}}>Stop: −{Math.abs(n(ipo.play_stop_loss_pct)).toFixed(0)}%</span>}
                {ipo.play_target_pct&&<span style={{fontSize:11,color:C.green,fontWeight:700}}>Target: +{n(ipo.play_target_pct).toFixed(0)}%</span>}
                {ipo.play_hold_window&&<span style={{fontSize:11,color:C.textMeta}}>Hold: {ipo.play_hold_window}</span>}
              </div>
            </div>
          )}

          {/* Stats grid */}
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:12}}>
            {lqi>0&&<Chip label="LQI" value={String(lqi)} color={lqi>=70?C.green:lqi>=50?C.teal:C.amber}/>}
            {n(ipo.buy_at_open_score)>0&&<Chip label="Open Score" value={n(ipo.buy_at_open_score).toFixed(0)} color={n(ipo.buy_at_open_score)>=70?C.green:C.amber}/>}
            {n(ipo.prob_10pct_profit)>0&&<Chip label="P(+10%)" value={`${n(ipo.prob_10pct_profit).toFixed(0)}%`} color={C.green}/>}
            {n(ipo.prob_loss_gt10)>0&&<Chip label="P(loss)" value={`${n(ipo.prob_loss_gt10).toFixed(0)}%`} color={C.red}/>}
            {n(ipo.ipo_pe)>0&&<Chip label="P/E" value={n(ipo.ipo_pe).toFixed(0)}/>}
            {n(ipo.peer_median_pe)>0&&<Chip label="Peer P/E" value={n(ipo.peer_median_pe).toFixed(0)}/>}
            {n(ipo.ofs_pct)>0&&<Chip label="OFS%" value={`${n(ipo.ofs_pct).toFixed(0)}%`} color={n(ipo.ofs_pct)>60?C.red:C.textSub}/>}
            {gmp!=null&&<Chip label="GMP" value={pct(gmp)} color={gmp>=0?C.green:C.red}/>}
          </div>

          {/* GMP trend bars */}
          {(ipo.gmp_pct_t10||ipo.gmp_pct_t7||ipo.gmp_pct_t5||ipo.gmp_pct_t3||ipo.gmp_pct_t1)&&(
            <div style={{marginBottom:12,padding:"10px 12px",background:C.surface,borderRadius:8,border:`1px solid ${C.border}`}}>
              <div style={{fontSize:10,fontWeight:700,color:C.textMeta,marginBottom:8}}>GMP Trend</div>
              <div style={{display:"flex",gap:4,alignItems:"flex-end",height:44}}>
                {[{l:"T-10",v:ipo.gmp_pct_t10},{l:"T-7",v:ipo.gmp_pct_t7},
                  {l:"T-5",v:ipo.gmp_pct_t5},{l:"T-3",v:ipo.gmp_pct_t3},
                  {l:"T-1",v:ipo.gmp_pct_t1??ipo.gmp_day_before_pct}]
                  .filter(p=>p.v!=null).map(p=>{
                  const v=n(p.v),col=v>=20?C.green:v>=5?C.teal:v>=0?C.amber:C.red
                  const h=Math.max(4,Math.min(36,Math.abs(v)/60*36))
                  return (
                    <div key={p.l} style={{flex:1,display:"flex",flexDirection:"column" as const,alignItems:"center",gap:2}}>
                      <span style={{fontSize:8,fontWeight:700,color:col}}>{v>=0?"+":""}{v.toFixed(0)}%</span>
                      <div style={{width:"100%",height:h,background:col,borderRadius:3,minHeight:4}}/>
                      <span style={{fontSize:8,color:C.textMeta}}>{p.l}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* BRLM */}
          {ipo.brlm_names&&(
            <div style={{padding:"10px 12px",background:C.surface,borderRadius:8,
              border:`1px solid ${C.border}`,marginBottom:10}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div>
                  <div style={{fontSize:9,fontWeight:700,color:C.textMeta,marginBottom:2,textTransform:"uppercase" as const}}>BRLM</div>
                  <div style={{fontSize:12,fontWeight:700,color:C.text}}>{ipo.brlm_names}</div>
                  {ipo.brlm_pct_negative!=null&&n(ipo.brlm_pct_negative)>20&&(
                    <div style={{fontSize:10,color:C.red,marginTop:2}}>
                      {n(ipo.brlm_pct_negative).toFixed(0)}% negative listing history
                    </div>
                  )}
                </div>
                {ipo.brlm_score&&(
                  <div style={{textAlign:"right"}}>
                    <div style={{fontSize:20,fontWeight:900,color:n(ipo.brlm_score)>=70?C.green:C.amber}}>
                      {n(ipo.brlm_score).toFixed(0)}
                    </div>
                    {ipo.brlm_avg_listing_gain&&(
                      <div style={{fontSize:9,color:C.green,fontWeight:700}}>
                        avg +{n(ipo.brlm_avg_listing_gain).toFixed(1)}%
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Anchors */}
          {(n(ipo.anchor_tier1_count)>0||n(ipo.anchor_count)>0)&&(
            <div style={{padding:"8px 12px",background:C.tealBg,borderRadius:8,
              border:`1px solid ${C.tealBd}`,marginBottom:10}}>
              <span style={{fontSize:11,fontWeight:700,color:C.teal}}>
                🏛 {n(ipo.anchor_count)} anchors · {n(ipo.anchor_tier1_count)} Tier-1
              </span>
              {ipo.anchor_stalwart_names&&(
                <div style={{fontSize:10,color:C.teal,marginTop:3,opacity:.8}}>{ipo.anchor_stalwart_names}</div>
              )}
              {(ipo.anchor_lock30_date||ipo.anchor_lock90_date)&&(
                <div style={{fontSize:9,color:C.teal,marginTop:2}}>
                  Unlock: {ipo.anchor_lock30_date} (30d) · {ipo.anchor_lock90_date} (90d)
                </div>
              )}
            </div>
          )}

          {/* Post-listing live returns */}
          {status==="LISTED"&&(
            <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:10}}>
              {livePrice&&liveGain!=null&&<Chip label="Live vs Issue" value={pct(liveGain)} color={liveGain>=0?C.green:C.red}/>}
              {ipo.return_listing_open!=null&&<Chip label="Day 1 Open" value={pct(ipo.return_listing_open)} color={n(ipo.return_listing_open)>=0?C.green:C.red}/>}
              {ipo.return_day7!=null&&<Chip label="Day 7" value={pct(ipo.return_day7)} color={n(ipo.return_day7)>=0?C.green:C.red}/>}
              {ipo.return_day30!=null&&<Chip label="Day 30" value={pct(ipo.return_day30)} color={n(ipo.return_day30)>=0?C.green:C.red}/>}
              {ipo.return_day90!=null&&<Chip label="Day 90" value={pct(ipo.return_day90)} color={n(ipo.return_day90)>=0?C.green:C.red}/>}
              {livePrice&&n(ipo.listing_open)>0&&(
                <Chip label="vs Listing" value={pct(((livePrice-n(ipo.listing_open))/n(ipo.listing_open))*100)} color={(livePrice-n(ipo.listing_open))>=0?C.green:C.red}/>
              )}
            </div>
          )}

          {/* Play reasons */}
          {ipo.play_reasons&&(
            <div style={{fontSize:11,color:C.textMeta,lineHeight:1.8,marginBottom:8}}>
              {(()=>{
                try {
                  const r=typeof ipo.play_reasons==="string"?JSON.parse(ipo.play_reasons):ipo.play_reasons
                  return Array.isArray(r)?r.map((s:string,i:number)=><div key={i}>• {s}</div>):String(r)
                }catch{return String(ipo.play_reasons)}
              })()}
            </div>
          )}

          {/* Operator risk */}
          {n(ipo.operator_risk_score)>=60&&(
            <div style={{display:"flex",alignItems:"center",gap:8,padding:"8px 12px",
              background:C.redBg,borderRadius:8,border:`1px solid ${C.redBd}`,fontSize:11,color:C.red}}>
              <AlertTriangle size={14}/>
              <b>Operator Risk {n(ipo.operator_risk_score).toFixed(0)}</b> — SME/operator pattern
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Skel() {
  return <div style={{background:"#F1F5F9",borderRadius:14,height:120,marginBottom:10,opacity:.7}}/>
}

function AccuracyStrip() {
  return (
    <div style={{background:"linear-gradient(135deg,#0f172a,#1e3a5f)",borderRadius:14,
      padding:"14px 18px",marginBottom:14,display:"flex",gap:20,flexWrap:"wrap",alignItems:"center"}}>
      <div>
        <div style={{fontSize:9,color:"#475569",textTransform:"uppercase" as const,letterSpacing:"0.1em",marginBottom:2}}>AACapital IPO Engine</div>
        <div style={{fontSize:13,fontWeight:900,color:"#F8FAFC"}}>333 IPOs backtested</div>
      </div>
      {[{l:"BUY AT OPEN",v:"98%",s:"192/195"},{l:"GMP Disappoint Q≥80",v:"87%",s:"+28% avg 6M"},{l:"High Conviction",v:"87%",s:"QIB≥60x"}]
        .map(s=>(
        <div key={s.l} style={{textAlign:"center"}}>
          <div style={{fontSize:9,color:"#64748b",marginBottom:2}}>{s.l}</div>
          <div style={{fontSize:18,fontWeight:900,color:"#f8fafc"}}>{s.v}</div>
          <div style={{fontSize:9,color:"#475569"}}>{s.s}</div>
        </div>
      ))}
    </div>
  )
}

function BrlmBoard({ipos}:{ipos:any[]}) {
  const map: Record<string,{name:string;count:number;avg:number;score:number}> = {}
  ipos.filter(i=>i.brlm_names&&i.brlm_score!=null).forEach(i=>{
    const name=i.brlm_names.split(",")[0].trim()
    if(!map[name]) map[name]={name,count:0,avg:n(i.brlm_avg_listing_gain??0),score:n(i.brlm_score)}
    map[name].count++
  })
  const list=Object.values(map).sort((a,b)=>b.score-a.score).slice(0,10)
  if(!list.length) return <div style={{padding:24,textAlign:"center",color:C.textMeta,fontSize:12}}>No BRLM data yet</div>
  return <div>{list.map((b,i)=>(
    <div key={b.name} style={{display:"flex",alignItems:"center",gap:12,padding:"12px 16px",borderBottom:`1px solid #F3F4F6`}}>
      <div style={{fontSize:16,fontWeight:900,color:C.textMeta,width:24}}>{i+1}</div>
      <div style={{flex:1}}>
        <div style={{fontSize:13,fontWeight:700,color:C.text}}>{b.name}</div>
        <div style={{fontSize:10,color:C.textMeta}}>{b.count} IPOs</div>
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
  const [expanded,setExpanded]= useState<string|null>(null)
  const [search,  setSearch]  = useState("")
  const [ts,      setTs]      = useState("")

  const load = useCallback(async()=>{
    setLoading(true)
    try {
      const r=await fetch("/api/ipo/playbook?limit=100",{cache:"no-store"})
      const j=await r.json()
      setIpos(j.ipos??[])
      setTs(new Date().toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit"}))
    }catch{setIpos([])}finally{setLoading(false)}
  },[])

  useEffect(()=>{load()},[load])

  const q=search.trim().toLowerCase()
  const all=ipos.filter(i=>!q||(i.company_name??"").toLowerCase().includes(q))

  const command  = all.filter(i=>{const s=statusOf(i);const p=i.play_recommendation??"";return(s==="OPEN"||s==="UPCOMING"||s==="ALLOTMENT")&&p!=="AVOID"})
  const openIpos = all.filter(i=>statusOf(i)==="OPEN")
  const upcoming = all.filter(i=>statusOf(i)==="UPCOMING")
  const listed   = all.filter(i=>{const s=statusOf(i);return s==="LISTED"||s==="ALLOTMENT"})
    .sort((a,b)=>new Date(b.listing_date??0).getTime()-new Date(a.listing_date??0).getTime())

  const TABS=[
    {id:"command", label:"⚡ Command",     count:command.length},
    {id:"open",    label:"📋 Open Now",    count:openIpos.length},
    {id:"upcoming",label:"📅 Upcoming",    count:upcoming.length},
    {id:"listed",  label:"📈 Post-Listing",count:listed.length},
    {id:"brlm",    label:"🏆 BRLM",        count:null},
  ]

  const active=tab==="command"?command:tab==="open"?openIpos:tab==="upcoming"?upcoming:tab==="listed"?listed:all

  return (
    <div style={{background:C.bg,minHeight:"100vh",paddingBottom:80}}>
      <div style={{maxWidth:720,margin:"0 auto",padding:"16px 16px 0"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div>
            <div style={{fontSize:20,fontWeight:900,color:C.text,display:"flex",alignItems:"center",gap:8}}>
              <Zap size={18} color={C.blue}/> IPO Command Center
            </div>
            {ts&&<div style={{fontSize:10,color:C.textMeta}}>Updated {ts} IST · Live prices from NSE</div>}
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <input value={search} onChange={e=>setSearch(e.target.value)}
              placeholder="Search..."
              style={{padding:"6px 12px",borderRadius:8,border:`1px solid ${C.border}`,
                fontSize:12,outline:"none",width:120}}/>
            <button onClick={load}
              style={{display:"flex",alignItems:"center",gap:4,padding:"6px 12px",
                borderRadius:8,border:`1px solid ${C.border}`,background:C.surface,
                fontSize:11,color:C.textSub,cursor:"pointer"}}>
              <RefreshCw size={11}/> Refresh
            </button>
          </div>
        </div>

        <AccuracyStrip/>

        {/* Tabs */}
        <div style={{display:"flex",gap:6,marginBottom:12,overflowX:"auto",paddingBottom:2}}>
          {TABS.map(t=>(
            <button key={t.id} onClick={()=>{setTab(t.id);setExpanded(null)}} style={{
              padding:"6px 14px",borderRadius:20,fontSize:11,cursor:"pointer",whiteSpace:"nowrap",
              border:`1px solid ${tab===t.id?C.blue:C.border}`,
              background:tab===t.id?C.blueBg:"transparent",
              color:tab===t.id?C.blue:C.textSub,
              fontWeight:tab===t.id?700:400}}>
              {t.label}{t.count!=null&&t.count>0?` (${t.count})`:""}
            </button>
          ))}
        </div>

        <div style={{fontSize:11,color:C.textMeta,marginBottom:10}}>
          {tab==="command"&&"Active BUY plays — open and upcoming IPOs ranked by conviction. Tap to expand."}
          {tab==="open"   &&"Currently accepting applications. GMP + subscription data shown where available."}
          {tab==="upcoming"&&"Opening soon. Monitor GMP trend to time your application decision."}
          {tab==="listed" &&"Recently listed. Tap to expand — live current price shown for tracked symbols."}
          {tab==="brlm"   &&"Investment banker quality score from 333 historical IPOs."}
        </div>

        {tab==="brlm"?(
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,overflow:"hidden"}}>
            <div style={{padding:"12px 16px",borderBottom:`1px solid ${C.border}`}}>
              <div style={{fontSize:14,fontWeight:800,color:C.text}}>BRLM Leaderboard</div>
              <div style={{fontSize:11,color:C.textMeta}}>Track record drives IPO outcome probability</div>
            </div>
            {loading?<Skel/>:<BrlmBoard ipos={ipos}/>}
          </div>
        ):loading?[1,2,3].map(i=><Skel key={i}/>)
        :active.length===0?(
          <div style={{padding:"48px 0",textAlign:"center",color:C.textMeta}}>
            <TrendingUp size={32} color="#CBD5E1" style={{margin:"0 auto 12px",display:"block"}}/>
            <div style={{fontSize:14,color:C.textSub,fontWeight:600,marginBottom:6}}>
              {tab==="command"?"No active BUY plays right now":`No ${tab} IPOs found`}
            </div>
            <div style={{fontSize:12}}>
              {tab==="command"?"All current IPOs are AVOID or already listed — check back during active IPO window":
               tab==="open"?"No IPOs currently accepting applications":
               tab==="upcoming"?"No upcoming IPOs in database":""}
            </div>
          </div>
        ):active.map((ipo,i)=>(
          <IpoCard key={ipo.id??i} ipo={ipo}
            expanded={expanded===(ipo.id??i).toString()}
            onToggle={()=>setExpanded(expanded===(ipo.id??i).toString()?null:(ipo.id??i).toString())}/>
        ))}

        <div style={{fontSize:10,color:"#CBD5E1",textAlign:"center",marginTop:8,lineHeight:1.6}}>
          Engine accuracy: 333 historical IPOs · GMP from ipo_intelligence · Live prices via Yahoo Finance
          <br/>Not SEBI registered advice · Always verify on Chittorgarh before trading
        </div>
      </div>
    </div>
  )
}
