"use client";
// app/dashboard/research/page.tsx — Score v0 evidence: factors, band history, live grades.
import AppShell from "@/components/app-shell/AppShell";
import { useEffect, useState } from "react";
const C={bg:"#FAFAF8",surface:"#FFF",border:"#E5E7EB",text:"#111827",sub:"#374151",meta:"#6B7280",dim:"#9CA3AF",
green:"#16A34A",greenBg:"#F0FDF4",greenBd:"#BBF7D0",blue:"#2563EB",blueBg:"#EFF6FF",blueBd:"#BFDBFE",
red:"#DC2626",redBg:"#FEF2F2",redBd:"#FECACA",grayBg:"#F3F4F6"};
const BANDS:Record<string,{c:string;bg:string;bd:string}>={STRONG:{c:C.green,bg:C.greenBg,bd:C.greenBd},
FAVORABLE:{c:C.blue,bg:C.blueBg,bd:C.blueBd},NEUTRAL:{c:C.meta,bg:C.grayBg,bd:C.border},AVOID:{c:C.red,bg:C.redBg,bd:C.redBd}};
const PERF=[{b:"STRONG",n:38,w:89.5,m:9.4,d:"score ≥ +3"},{b:"FAVORABLE",n:96,w:76.0,m:8.7,d:"+1..+2"},
{b:"NEUTRAL",n:152,w:75.7,m:5.9,d:"-1..0"},{b:"AVOID",n:84,w:51.2,m:0.8,d:"≤ -2 (2025+: 36%)"}];
const FACTORS=[["Gap MID","+2","69","84.1%","+9.4","the core edge; 78/88/84% across eras"],
["Size > ₹2000cr","+2","77","81.8%","+9.2","mega-issues run in every bucket"],
["Size ₹150-500cr","-2","73","58.9%","+1.5","the churner zone; LOW×this = 50%"],
["Peer-P/E < 0.6x","+1","30","76.7%","+7.6","cheap vs peers"],
["P/E > 60","+1","38","78.9%","+8.2","hype harvested by the 10-session exit"],
["P/E 30-60","-1","136","66.2%","+3.4","the mediocre middle"],
["Gap HIGH","-1","89","64.0%","+5.4","pop-and-fade; 50% in 2025+"]];
type R=Record<string,unknown>;
function Chip({b}:{b?:string|null}){const s=BANDS[b||""]||BANDS.NEUTRAL;
return <span style={{color:s.c,background:s.bg,border:`1px solid ${s.bd}`,borderRadius:8,padding:"2px 9px",fontSize:11,fontWeight:700}}>{b||"UNSCORED"}</span>;}
const th:React.CSSProperties={textAlign:"left",fontSize:10.5,color:C.meta,textTransform:"uppercase",letterSpacing:.5,padding:"7px 8px",borderBottom:`1px solid ${C.border}`};
const td:React.CSSProperties={fontSize:13,color:C.sub,padding:"7px 8px",borderBottom:`1px solid ${C.border}`};
function Research(){
  const [d,setD]=useState<{upcoming:R[];recent:R[]}|null>(null);
  const [err,setErr]=useState<string|null>(null);
  useEffect(()=>{fetch("/api/research").then(r=>r.json()).then(j=>j.error?setErr(j.error):setD(j)).catch(e=>setErr(String(e)));},[]);
  const card:React.CSSProperties={background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:16,marginBottom:16};
  return(<div style={{padding:"18px 22px",background:C.bg,minHeight:"100vh",maxWidth:1100,margin:"auto",color:C.text,font:'14px/1.45 -apple-system,"Segoe UI",Inter,sans-serif'}}>
    <div style={{display:"flex",gap:14,alignItems:"baseline",marginBottom:4}}>
      <a href="/dashboard/ipo2" style={{fontSize:13,fontWeight:600,color:C.blue,textDecoration:"none",background:C.blueBg,border:`1px solid ${C.blueBd}`,borderRadius:8,padding:"5px 10px"}}>← IPO Command Center</a>
      <h1 style={{fontSize:20,fontWeight:800,margin:0}}>🔬 Research · Score v0</h1></div>
    <p style={{fontSize:13,color:C.meta,margin:"4px 0 16px"}}>Every grade traces to these tables. n=370 (2010–26) · entry = listing open · exit = best close ≤10 sessions · baseline 72% / +5.9%. Research signal, not a buy call.</p>
    {err&&<div style={{...card,color:C.red,borderColor:C.redBd}}>{err}</div>}
    <div style={card}><b>Upcoming IPOs — live grades</b>
      <table style={{width:"100%",borderCollapse:"collapse",marginTop:8}}><thead><tr>
        <th style={th}>Lists</th><th style={th}>Company</th><th style={th}>Size ₹cr</th><th style={th}>Grade</th><th style={th}>Evidence</th></tr></thead>
      <tbody>{(d?.upcoming||[]).map((r,i)=>(<tr key={i}>
        <td style={td}>{String(r.listing_date||"").slice(0,10)}</td>
        <td style={{...td,fontWeight:600,color:C.text}}>{String(r.company_name||"")}</td>
        <td style={td}>{r.issue_size_cr==null?"—":Number(r.issue_size_cr).toLocaleString()}</td>
        <td style={td}><Chip b={r.score_band as string}/></td>
        <td style={{...td,fontSize:12,color:C.meta}}>{String(r.score_evidence||"—")}</td></tr>))}</tbody></table></div>
    <div style={card}><b>How each grade performed (validated 2026-07-05, monotonic = PASS)</b>
      <table style={{width:"100%",borderCollapse:"collapse",marginTop:8}}><thead><tr>
        <th style={th}>Grade</th><th style={th}>n</th><th style={th}>Made money</th><th style={th}>Typical</th><th style={th}>Definition</th></tr></thead>
      <tbody>{PERF.map((b,i)=>(<tr key={i}><td style={td}><Chip b={b.b}/></td><td style={td}>{b.n}</td>
        <td style={{...td,fontWeight:700,color:C.text}}>{b.w}% ({(b.w/10).toFixed(1)} of 10)</td>
        <td style={td}>+{b.m}%</td><td style={{...td,fontSize:12,color:C.meta}}>{b.d}</td></tr>))}</tbody></table></div>
    <div style={card}><b>Validated factors (n ≥ 30, era-consistent)</b>
      <table style={{width:"100%",borderCollapse:"collapse",marginTop:8}}><thead><tr>
        <th style={th}>Factor</th><th style={th}>Weight</th><th style={th}>n</th><th style={th}>Win</th><th style={th}>Median</th><th style={th}>Note</th></tr></thead>
      <tbody>{FACTORS.map((f,i)=>(<tr key={i}><td style={{...td,fontWeight:600,color:C.text}}>{f[0]}</td>
        <td style={{...td,fontWeight:700,color:f[1].startsWith("+")?C.green:C.red}}>{f[1]}</td>
        <td style={td}>{f[2]}</td><td style={td}>{f[3]}</td><td style={td}>{f[4]}%</td>
        <td style={{...td,fontSize:12,color:C.meta}}>{f[5]}</td></tr>))}</tbody></table>
      <p style={{fontSize:12,color:C.dim,margin:"8px 0 0"}}>Tested and NOT predictive: ROE, final QIB level, GMP level, OFS share, day-1→day-2 continuation. Pending data: anchors, QIB backloading, GMP trajectory.</p></div>
    <div style={card}><b>Recently listed — grade vs what happened</b>
      <table style={{width:"100%",borderCollapse:"collapse",marginTop:8}}><thead><tr>
        <th style={th}>Listed</th><th style={th}>Company</th><th style={th}>Grade</th><th style={th}>Gap</th><th style={th}>10-session best</th></tr></thead>
      <tbody>{(d?.recent||[]).map((r,i)=>(<tr key={i}>
        <td style={td}>{String(r.listing_date||"").slice(0,10)}</td>
        <td style={{...td,fontWeight:600,color:C.text}}>{String(r.company_name||"")}</td>
        <td style={td}><Chip b={r.score_band as string}/></td>
        <td style={td}>{String(r.gap_bucket||"—")}</td>
        <td style={{...td,fontWeight:700,color:r.d10_best_pct==null?C.dim:(Number(r.d10_best_pct)>0?C.green:C.red)}}>
          {r.d10_best_pct==null?"pending":`${Number(r.d10_best_pct).toFixed(1)}%`}</td></tr>))}</tbody></table></div>
  </div>);}

export default function ResearchRoute() {
  return (
    <AppShell current="research">
      <Research />
    </AppShell>
  );
}
