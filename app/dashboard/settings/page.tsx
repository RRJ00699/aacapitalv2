"use client";
import { Skeleton } from "@/components/ui/primitives";
import AppShell from "@/components/app-shell/AppShell";
import { useEffect, useState } from "react";

const C={bg:"var(--t-bg)",s:"var(--t-surface)",bd:"var(--t-border)",tx:"var(--t-text)",mt:"var(--t-meta)",gr:"var(--t-green)",grB:"var(--t-greenBg)",grD:"var(--t-greenBd)"};

const CHECKS: Array<[string,string]> = [
  ["rhp_status","RHP status (upcoming/recent)"],
  ["preopen_book","Pre-open captures"],
  ["eps_coverage","Valuation coverage"],
  ["twin_census","Twin census"],
  ["pipeline_failures","Pipeline failures (7d)"],
];

function Diagnostics(){
  const [sel,setSel]=useState<string|null>(null);
  const [res,setRes]=useState<{rows:Array<Record<string,unknown>>;ranAt?:string}|null>(null);
  const [busy,setBusy]=useState(false);
  const run=(k:string)=>{setSel(k);setBusy(true);setRes(null);
    fetch(`/api/admin/diagnostics?check=${k}`).then(r=>r.json())
      .then(j=>setRes(j.ok?j:{rows:[{error:String(j.error||"failed")}]}))
      .catch(()=>setRes({rows:[{error:"network"}]})).finally(()=>setBusy(false));};
  return <div>
    <div style={{display:"flex",flexWrap:"wrap",gap:8,marginBottom:10}}>{CHECKS.map(([k,label])=>(
      <button key={k} onClick={()=>run(k)} style={{background:sel===k?"#0F172A":C.s,color:sel===k?"#fff":C.tx,border:`1px solid ${C.bd}`,borderRadius:999,padding:"7px 13px",fontSize:12,fontWeight:600,cursor:"pointer"}}>{label}</button>
    ))}</div>
    {busy&&<div style={{fontSize:12,color:C.mt}}>running…</div>}
    {res&&(res.rows?.length?<div style={{overflowX:"auto"}}>{res.rows.map((r,i)=>(
      <div key={i} style={{background:C.s,border:`1px solid ${C.bd}`,borderRadius:10,padding:"9px 12px",marginBottom:6}}>
        {Object.entries(r).map(([k,v])=><div key={k} style={{display:"flex",gap:8,fontSize:11.5,lineHeight:1.5}}><span style={{color:C.mt,minWidth:96,flexShrink:0}}>{k}</span><span style={{fontFamily:"var(--f-mono)",fontSize:11,overflowWrap:"anywhere"}}>{v==null?"—":typeof v==="object"?JSON.stringify(v):String(v)}</span></div>)}
      </div>))}</div>:<div style={{background:C.grB,border:`1px solid ${C.grD}`,color:C.gr,borderRadius:10,padding:"10px 12px",fontSize:12.5,fontWeight:600}}>Empty — nothing to report ✓</div>)}
  </div>;
}

function StepBoard(){
  const [steps,setSteps]=useState<Array<{step:string;ok:boolean;error?:string;ran_at:string}>|null>(null);
  const [expected,setExpected]=useState<Array<{step:string;weekly?:boolean}>>([]);
  useEffect(()=>{fetch("/api/admin/pipeline-steps").then(r=>r.json()).then(j=>{setSteps(j.steps||[]);setExpected(j.expected||[]);}).catch(()=>setSteps([]));},[]);
  if(steps===null)return <Skeleton h={30} n={6}/>;
  if(!steps.length)return <div style={{fontSize:12,color:C.mt}}>No D1 step log yet — populates after the pipeline writer cutover.</div>;
  const fails=steps.filter(s=>!s.ok).length;
  const ranNames=new Set(steps.map(s=>s.step));
  const weeklyRan=expected.some(e=>e.weekly&&ranNames.has(e.step));
  const lastMs=Date.parse(String(steps[steps.length-1]?.ran_at||0));
  const inProgress=Number.isFinite(lastMs)&&(Date.now()-lastMs)<15*60*1000;
  const missed=inProgress?[]:expected.filter(e=>!ranNames.has(e.step)&&(!e.weekly||weeklyRan));
  return <div>
    <div style={{fontSize:12,fontWeight:700,marginBottom:8,color:fails||missed.length?"#B42318":C.gr}}>{steps.length} steps · {steps.length-fails} ✓ · {fails} ✕{missed.length?` · ${missed.length} MISSED`:""}{inProgress?" · RUN IN PROGRESS":""}</div>
    <div style={{display:"grid",gridTemplateColumns:"1fr",gap:3}}>{steps.map((s2,i)=><div key={i} style={{display:"flex",alignItems:"flex-start",gap:8,padding:"5px 10px",background:s2.ok?C.s:"#FEF3F2",border:`1px solid ${s2.ok?C.bd:"#FECDCA"}`,borderRadius:8}}><span style={{fontWeight:800,color:s2.ok?C.gr:"#B42318"}}>{s2.ok?"✓":"✕"}</span><span style={{fontSize:12,flex:1}}>{s2.step}</span>{!s2.ok&&s2.error?<span style={{fontFamily:"var(--f-mono)",fontSize:9.5,color:"#B42318",maxWidth:"46%"}}>{s2.error.slice(0,90)}</span>:null}</div>)}</div>
  </div>;
}

function Settings(){
  return <div style={{padding:"18px clamp(14px,4vw,20px)",background:C.bg,minHeight:"100vh",maxWidth:640,margin:"auto",color:C.tx,font:'14px/1.5 var(--f-body)'}}>
    <a href="/dashboard/admin" style={{display:"inline-block",fontSize:13,fontWeight:600,color:"var(--t-blue)",textDecoration:"none",background:"var(--t-blueBg)",border:"1px solid var(--t-blueBd)",borderRadius:8,padding:"5px 10px",marginBottom:12}}>← Admin</a>
    <h1 style={{fontFamily:"var(--f-display)",fontSize:19,fontWeight:800,margin:"0 0 4px"}}>Settings</h1>
    <div style={{background:C.grB,border:`1px solid ${C.grD}`,color:C.gr,borderRadius:10,padding:"10px 12px",fontSize:12.5,fontWeight:600,margin:"12px 0 20px"}}>Service credentials and tokens are managed in Cloudflare Secrets / the dedicated Kite broker worker. This page no longer stores credentials in a database.</div>
    <h2 style={{fontFamily:"var(--f-display)",fontSize:16,fontWeight:800,margin:"22px 0 4px"}}>Pipeline health</h2>
    <StepBoard/>
    <h2 style={{fontFamily:"var(--f-display)",fontSize:16,fontWeight:800,margin:"22px 0 4px"}}>Diagnostics</h2>
    <Diagnostics/>
  </div>;
}

export default function SettingsRoute(){return <AppShell current="admin"><Settings/></AppShell>}
