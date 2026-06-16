"use client";
// app/dashboard/watchlist/WatchlistClient.tsx
import { useState } from "react";
import type { WatchlistItem } from "./page";

const C = {
  green:"#16A34A",greenBg:"#F0FDF4",greenBd:"#BBF7D0",
  amber:"#D97706",amberBg:"#FFFBEB",amberBd:"#FDE68A",
  red:"#DC2626",redBg:"#FEF2F2",redBd:"#FECACA",
  blue:"#2563EB",blueBg:"#EFF6FF",blueBd:"#BFDBFE",
  gray:"#6B7280",grayBg:"#F9FAFB",grayBd:"#E5E7EB",
  text:"#111827",textSub:"#6B7280",surface:"#FFFFFF",bg:"#FAFAF8",border:"#E5E7EB",
};
const CONV:Record<string,{color:string;bg:string}> = {
  HIGH:{color:C.green,bg:C.greenBg},MEDIUM:{color:C.amber,bg:C.amberBg},LOW:{color:C.gray,bg:C.grayBg},
};

function UpsideBadge({pct}:{pct:number|null}) {
  if(pct===null) return <span style={{color:C.gray,fontSize:12}}>—</span>;
  const color=pct>=20?C.green:pct>=0?C.blue:C.red;
  return <span style={{color,fontWeight:600,fontSize:13}}>{pct>=0?"+":""}{Number(pct).toFixed(1)}%</span>;
}

export default function WatchlistClient({items}:{items:WatchlistItem[]}) {
  const [search,setSearch]=useState("");
  const [sortKey,setSortKey]=useState<"added"|"upside"|"conviction">("added");

  const filtered=items
    .filter(i=>!search||i.symbol.toLowerCase().includes(search.toLowerCase())||(i.company_name??"").toLowerCase().includes(search.toLowerCase()))
    .sort((a,b)=>{
      if(sortKey==="upside") return (Number(b.upside_pct??-999))-(Number(a.upside_pct??-999));
      if(sortKey==="conviction"){const o={HIGH:0,MEDIUM:1,LOW:2};return (o[a.conviction as keyof typeof o]??3)-(o[b.conviction as keyof typeof o]??3);}
      return new Date(b.added_date??"").getTime()-new Date(a.added_date??"").getTime();
    });

  return (
    <div style={{padding:"20px 24px",background:C.bg,minHeight:"100vh"}}>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:20,fontWeight:800,color:C.text,margin:0}}>Watchlist</h1>
        <p style={{fontSize:13,color:C.textSub,marginTop:4}}>{items.length} stocks tracked</p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:20}}>
        {[
          {label:"Total",value:items.length,color:C.blue},
          {label:"High conviction",value:items.filter(i=>i.conviction==="HIGH").length,color:C.green},
          {label:"Avg upside",value:items.filter(i=>i.upside_pct!==null).length>0?`${(items.filter(i=>i.upside_pct!==null).reduce((s,i)=>s+Number(i.upside_pct),0)/items.filter(i=>i.upside_pct!==null).length).toFixed(1)}%`:"—",color:C.amber},
          {label:"Sectors",value:new Set(items.map(i=>i.sector).filter(Boolean)).size,color:C.blue},
        ].map(s=>(
          <div key={s.label} style={{background:C.surface,borderRadius:12,border:`1px solid ${C.border}`,padding:"12px 16px"}}>
            <div style={{fontSize:11,color:C.textSub,marginBottom:4}}>{s.label}</div>
            <div style={{fontSize:22,fontWeight:700,color:s.color}}>{s.value}</div>
          </div>
        ))}
      </div>
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:"12px 16px",marginBottom:16,display:"flex",gap:12,alignItems:"center",flexWrap:"wrap"}}>
        <input type="text" placeholder="Search..." value={search} onChange={e=>setSearch(e.target.value)}
          style={{border:`1px solid ${C.border}`,borderRadius:8,padding:"6px 12px",fontSize:13,outline:"none",width:220}}/>
        <div style={{display:"flex",gap:6,marginLeft:"auto"}}>
          {(["added","upside","conviction"] as const).map(k=>(
            <button key={k} onClick={()=>setSortKey(k)} style={{
              padding:"5px 12px",borderRadius:6,border:`1px solid ${C.border}`,
              background:sortKey===k?"#111827":C.surface,color:sortKey===k?"#fff":C.gray,
              fontSize:11,cursor:"pointer",fontWeight:sortKey===k?600:400,
            }}>{k==="added"?"Latest":k==="upside"?"Upside":"Conviction"}</button>
          ))}
        </div>
      </div>
      {filtered.length===0?(
        <div style={{textAlign:"center",padding:60,color:C.textSub}}>
          <div style={{fontSize:40,marginBottom:12}}>📋</div>
          <div style={{fontSize:16,fontWeight:600,color:C.text}}>Watchlist is empty</div>
          <div style={{fontSize:13,marginTop:6}}>Add stocks from the Research workspace</div>
        </div>
      ):(
        <div style={{background:C.surface,borderRadius:12,border:`1px solid ${C.border}`,overflow:"hidden"}}>
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
              <thead>
                <tr style={{borderBottom:`1px solid ${C.border}`,background:C.grayBg}}>
                  {["Symbol","Sector","CMP","Target","Upside","Stop Loss","Conviction","Notes","Added"].map(h=>(
                    <th key={h} style={{padding:"10px 14px",textAlign:"left",fontSize:11,fontWeight:600,color:C.textSub,textTransform:"uppercase",whiteSpace:"nowrap"}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((item,i)=>{
                  const cfg=CONV[item.conviction??""]??CONV.LOW;
                  return (
                    <tr key={item.id} style={{borderBottom:`1px solid ${C.border}`,background:i%2===0?C.surface:C.bg}}>
                      <td style={{padding:"12px 14px",fontWeight:700,color:C.text}}>
                        {item.symbol}
                        {item.company_name&&item.company_name!==item.symbol&&<div style={{fontSize:11,color:C.textSub,fontWeight:400}}>{item.company_name}</div>}
                      </td>
                      <td style={{padding:"12px 14px",color:C.textSub,fontSize:12}}>{item.sector??"—"}</td>
                      <td style={{padding:"12px 14px",fontWeight:600}}>{item.current_price?`₹${Number(item.current_price).toLocaleString("en-IN")}`:"—"}</td>
                      <td style={{padding:"12px 14px"}}>{item.target_price?`₹${Number(item.target_price).toLocaleString("en-IN")}`:"—"}</td>
                      <td style={{padding:"12px 14px"}}><UpsideBadge pct={item.upside_pct}/></td>
                      <td style={{padding:"12px 14px",color:C.red,fontSize:12}}>{item.stop_loss?`₹${Number(item.stop_loss).toLocaleString("en-IN")}`:"—"}</td>
                      <td style={{padding:"12px 14px"}}>
                        {item.conviction?<span style={{padding:"3px 8px",borderRadius:20,fontSize:11,fontWeight:600,color:cfg.color,background:cfg.bg}}>{item.conviction}</span>:"—"}
                      </td>
                      <td style={{padding:"12px 14px",color:C.textSub,fontSize:12,maxWidth:200}}>{item.notes??"—"}</td>
                      <td style={{padding:"12px 14px",color:C.textSub,fontSize:11}}>{item.added_date?String(item.added_date).substring(0,10):"—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
