"use client";
// app/dashboard/journal/JournalClient.tsx

import { useState } from "react";
import type { TradeEntry } from "./page";

const C = {
  green:"#16A34A",greenBg:"#F0FDF4",
  red:"#DC2626",redBg:"#FEF2F2",
  blue:"#2563EB",blueBg:"#EFF6FF",
  amber:"#D97706",amberBg:"#FFFBEB",
  gray:"#6B7280",grayBg:"#F9FAFB",grayBd:"#E5E7EB",
  text:"#111827",textSub:"#6B7280",surface:"#FFFFFF",bg:"#FAFAF8",border:"#E5E7EB",
};

function PnlBadge({pnl,pct}:{pnl:number|null;pct:number|null}) {
  if(pnl===null) return <span style={{color:C.gray}}>Open</span>;
  const pos=pnl>=0;
  return (
    <div>
      <div style={{fontWeight:700,color:pos?C.green:C.red,fontSize:14}}>
        {pos?"+":"-"}₹{Math.abs(Number(pnl)).toLocaleString("en-IN")}
      </div>
      {pct!==null&&<div style={{fontSize:11,color:pos?C.green:C.red}}>{pos?"+":""}{Number(pct).toFixed(1)}%</div>}
    </div>
  );
}

export default function JournalClient({trades,stats}:{trades:TradeEntry[];stats:Record<string,unknown>}) {
  const [filter,setFilter]=useState<"all"|"winners"|"losers"|"open">("all");
  const [expanded,setExpanded]=useState<number|null>(null);

  const total=Number(stats.total_trades??0);
  const winners=Number(stats.winners??0);
  const winRate=total>0?Math.round((winners/total)*100):0;

  const filtered=trades.filter(t=>{
    if(filter==="winners") return Number(t.pnl??0)>0;
    if(filter==="losers") return Number(t.pnl??0)<0;
    if(filter==="open") return t.exit_date===null;
    return true;
  });

  return (
    <div style={{padding:"20px 24px",background:C.bg,minHeight:"100vh"}}>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:20,fontWeight:800,color:C.text,margin:0}}>Trade Journal</h1>
        <p style={{fontSize:13,color:C.textSub,marginTop:4}}>Track every trade — learn from both wins and losses</p>
      </div>

      {/* Stats */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:12,marginBottom:20}}>
        {[
          {label:"Total trades",value:total,color:C.blue},
          {label:"Win rate",value:`${winRate}%`,color:winRate>=50?C.green:C.red},
          {label:"Total P&L",value:stats.total_pnl?`₹${Number(stats.total_pnl).toLocaleString("en-IN")}`:"—",color:Number(stats.total_pnl??0)>=0?C.green:C.red},
          {label:"Avg return",value:stats.avg_return_pct?`${Number(stats.avg_return_pct)>=0?"+":""}${Number(stats.avg_return_pct).toFixed(1)}%`:"—",color:Number(stats.avg_return_pct??0)>=0?C.green:C.red},
          {label:"Avg hold",value:stats.avg_holding_days?`${stats.avg_holding_days}d`:"—",color:C.blue},
        ].map(s=>(
          <div key={s.label} style={{background:C.surface,borderRadius:12,border:`1px solid ${C.border}`,padding:"12px 16px"}}>
            <div style={{fontSize:11,color:C.textSub,marginBottom:4}}>{s.label}</div>
            <div style={{fontSize:20,fontWeight:700,color:s.color}}>{String(s.value)}</div>
          </div>
        ))}
      </div>

      {/* Best/Worst */}
      {(stats.best_trade_pct||stats.worst_trade_pct)&&(
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:20}}>
          <div style={{background:C.greenBg,border:"1px solid #BBF7D0",borderRadius:12,padding:"12px 16px"}}>
            <div style={{fontSize:11,color:C.green,fontWeight:600,marginBottom:4}}>🏆 BEST TRADE</div>
            <div style={{fontSize:24,fontWeight:800,color:C.green}}>+{Number(stats.best_trade_pct).toFixed(1)}%</div>
          </div>
          <div style={{background:C.redBg,border:"1px solid #FECACA",borderRadius:12,padding:"12px 16px"}}>
            <div style={{fontSize:11,color:C.red,fontWeight:600,marginBottom:4}}>📉 WORST TRADE</div>
            <div style={{fontSize:24,fontWeight:800,color:C.red}}>{Number(stats.worst_trade_pct).toFixed(1)}%</div>
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{display:"flex",gap:8,marginBottom:16}}>
        {(["all","winners","losers","open"] as const).map(f=>(
          <button key={f} onClick={()=>setFilter(f)} style={{
            padding:"6px 14px",borderRadius:8,border:`1px solid ${C.border}`,
            background:filter===f?"#111827":C.surface,
            color:filter===f?"#fff":C.gray,fontSize:12,cursor:"pointer",fontWeight:filter===f?600:400,
          }}>{f==="all"?"All trades":f==="winners"?"Winners ✅":f==="losers"?"Losers ❌":"Open 🔄"}</button>
        ))}
        <span style={{marginLeft:"auto",fontSize:12,color:C.textSub,alignSelf:"center"}}>{filtered.length} trades</span>
      </div>

      {/* Trades */}
      {filtered.length===0?(
        <div style={{textAlign:"center",padding:60,color:C.textSub}}>
          <div style={{fontSize:40,marginBottom:12}}>📓</div>
          <div style={{fontSize:16,fontWeight:600,color:C.text}}>No trades yet</div>
          <div style={{fontSize:13,marginTop:6}}>Trades will appear here after you log them via the Zerodha integration</div>
        </div>
      ):(
        <div style={{display:"flex",flexDirection:"column",gap:8}}>
          {filtered.map(t=>(
            <div key={t.id} style={{background:C.surface,borderRadius:12,border:`1px solid ${C.border}`,overflow:"hidden"}}>
              <div
                style={{padding:"14px 16px",display:"flex",alignItems:"center",gap:16,cursor:"pointer"}}
                onClick={()=>setExpanded(expanded===t.id?null:t.id)}
              >
                <div style={{flex:1}}>
                  <div style={{display:"flex",alignItems:"center",gap:8}}>
                    <span style={{fontWeight:700,fontSize:15,color:C.text}}>{t.symbol}</span>
                    {t.trade_type&&<span style={{fontSize:10,padding:"2px 7px",borderRadius:4,background:t.trade_type==="LONG"?C.greenBg:C.redBg,color:t.trade_type==="LONG"?C.green:C.red,fontWeight:600}}>{t.trade_type}</span>}
                    {t.conviction_at_entry&&<span style={{fontSize:10,color:C.textSub,background:C.grayBg,padding:"2px 6px",borderRadius:4}}>{t.conviction_at_entry}</span>}
                  </div>
                  <div style={{fontSize:11,color:C.textSub,marginTop:3}}>
                    {t.entry_date?String(t.entry_date).substring(0,10):""}{t.exit_date?` → ${String(t.exit_date).substring(0,10)}`:" → Open"}
                    {t.holding_days&&` · ${t.holding_days}d`}
                  </div>
                </div>
                <div style={{textAlign:"right"}}>
                  <PnlBadge pnl={t.pnl} pct={t.pnl_pct}/>
                  <div style={{fontSize:11,color:C.textSub,marginTop:2}}>
                    {t.entry_price?`₹${Number(t.entry_price).toLocaleString("en-IN")}`:""}
                    {t.exit_price?` → ₹${Number(t.exit_price).toLocaleString("en-IN")}`:t.exit_date?"":" → Hold"}
                  </div>
                </div>
                <div style={{color:C.gray,fontSize:16}}>{expanded===t.id?"▲":"▼"}</div>
              </div>
              {expanded===t.id&&(
                <div style={{borderTop:`1px solid ${C.border}`,padding:"14px 16px",background:C.grayBg}}>
                  <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
                    {t.reason_entry&&(
                      <div>
                        <div style={{fontSize:11,fontWeight:600,color:C.textSub,marginBottom:4}}>WHY I ENTERED</div>
                        <div style={{fontSize:13,color:C.text}}>{t.reason_entry}</div>
                      </div>
                    )}
                    {t.reason_exit&&(
                      <div>
                        <div style={{fontSize:11,fontWeight:600,color:C.textSub,marginBottom:4}}>WHY I EXITED</div>
                        <div style={{fontSize:13,color:C.text}}>{t.reason_exit}</div>
                      </div>
                    )}
                    {t.lessons&&(
                      <div style={{gridColumn:"1/-1"}}>
                        <div style={{fontSize:11,fontWeight:600,color:C.amber,marginBottom:4}}>💡 LESSONS LEARNED</div>
                        <div style={{fontSize:13,color:C.text,background:"#FEF3C7",padding:"8px 12px",borderRadius:8}}>{t.lessons}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
