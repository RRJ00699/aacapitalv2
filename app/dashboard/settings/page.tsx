"use client";
// app/dashboard/settings/page.tsx — set service secrets from the phone.
import AppShell from "@/components/app-shell/AppShell";
import { useEffect, useState } from "react";
const C={bg:"var(--t-bg)",s:"var(--t-surface)",bd:"var(--t-border)",tx:"var(--t-text)",mt:"var(--t-meta)",gr:"var(--t-green)",grB:"var(--t-greenBg)",grD:"var(--t-greenBd)"};
const FIELDS=[["ipomatrix_cookie","IPOMatrix cookie / JWT (x-access-token — ~30d expiry, status shows the date)"],["screener_username","Screener.in email"],["screener_password","Screener.in password"],["screener_cookie","Screener.in cookie (bypasses login — paste from browser DevTools)"],["zerodha_totp_secret","Zerodha TOTP secret (for the 08:45 auto-login — from Kite 2FA setup)"],["kite_api_key","Kite Connect API key"],["kite_api_secret","Kite Connect API secret"],["kite_user_id","Zerodha user ID (auto-login)"],["kite_password","Zerodha password (auto-login)"],["ntfy_topic","ntfy topic (push notifications)"]];
function Settings(){
  const [state,setState]=useState<Record<string,string>>({});
  const [vals,setVals]=useState<Record<string,string>>({});
  const [msg,setMsg]=useState("");
  const [kite,setKite]=useState("");
  const load=()=>fetch("/api/admin/secrets").then(r=>r.json()).then(j=>{setState(j.state||{});setKite(j.kite||"");});
  useEffect(()=>{load();},[]);
  const save=(k:string)=>fetch("/api/admin/secrets",{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,value:vals[k]||""})})
    .then(r=>r.ok?(setMsg(k+" saved ✓"),setVals(v=>({...v,[k]:""})),load()):setMsg("save failed"));
  return(<div style={{padding:"18px clamp(14px,4vw,20px)",background:C.bg,minHeight:"100vh",maxWidth:640,margin:"auto",
    color:C.tx,font:'14px/1.5 var(--f-body)'}}>
      <a href="/dashboard/admin" style={{display:"inline-block",fontSize:13,fontWeight:600,
        color:"var(--t-blue)",textDecoration:"none",background:"var(--t-blueBg)",border:"1px solid var(--t-blueBd)",
        borderRadius:8,padding:"5px 10px",marginBottom:12}}>← Admin</a>
    <h1 style={{fontFamily:"var(--f-display)",letterSpacing:-0.3,fontSize:19,fontWeight:800,margin:"0 0 4px"}}>Service secrets</h1>
    <p style={{fontSize:12.5,color:C.mt,margin:"0 0 16px"}}>Stored in platform_config (same vault as the Kite token). Scripts &amp; auth read them automatically — no SSH, no Vercel.</p>
    {kite&&<div style={{background:kite.startsWith("LIVE")?C.grB:"var(--t-redBg)",border:`1px solid ${kite.startsWith("LIVE")?C.grD:"var(--t-redBd)"}`,color:kite.startsWith("LIVE")?C.gr:"var(--t-red)",borderRadius:8,padding:"8px 12px",fontSize:12.5,fontWeight:600,marginBottom:12}}>Kite worker session: {kite}</div>}
    {msg&&<div style={{background:C.grB,border:`1px solid ${C.grD}`,color:C.gr,borderRadius:8,padding:"8px 12px",fontSize:12.5,fontWeight:600,marginBottom:12}}>{msg}</div>}
    {FIELDS.map(([k,label])=>(
      <div key={k} style={{background:C.s,border:`1px solid ${C.bd}`,borderRadius:12,padding:14,marginBottom:12}}>
        <div style={{fontWeight:700,fontSize:13.5}}>{label}</div>
        <div style={{fontSize:11.5,color:C.mt,marginBottom:8}}>status: {state[k]||"…"}</div>
        <div style={{display:"flex",gap:8}}>
          <input type={k.includes("password")?"password":"text"} value={vals[k]||""}
            onChange={e=>setVals(v=>({...v,[k]:e.target.value}))}
            placeholder="new value" style={{flex:1,border:`1px solid ${C.bd}`,borderRadius:8,
            padding:"9px 11px",fontSize:13,fontFamily:"var(--f-mono)"}}/>
          <button onClick={()=>save(k)} disabled={!(vals[k]||"").trim()}
            style={{border:`1px solid ${C.grD}`,background:C.grB,color:C.gr,borderRadius:8,
            padding:"9px 14px",fontSize:13,fontWeight:700,cursor:"pointer"}}>Save</button>
        </div>
      </div>))}
    <h2 style={{fontFamily:"var(--f-display)",fontSize:16,fontWeight:800,margin:"22px 0 4px"}}>Pipeline health</h2>
    <p style={{fontSize:12,color:C.mt,margin:"0 0 10px"}}>Latest run, step by step — red names the step; the error is one tap away in Diagnostics.</p>
    <StepBoard/>
    <h2 style={{fontFamily:"var(--f-display)",fontSize:16,fontWeight:800,margin:"22px 0 4px"}}>Diagnostics</h2>
    <p style={{fontSize:12,color:C.mt,margin:"0 0 10px"}}>Read-only checks — no SQL console needed.</p>
    <Diagnostics/>
  </div>);}

const CHECKS: Array<[string,string]> = [
  ["rhp_status","RHP status (upcoming/recent)"],["sbi_notes","SBI notes parsed"],
  ["rhp_run_log","RHP run log ($ budget)"],["kite_session","Kite session"],
  ["preopen_book","Pre-open book captures"],["eps_coverage","EPS coverage"],
  ["twin_census","Twin census"],["pipeline_failures","Pipeline failures (7d)"]];

function Diagnostics(){
  const [sel,setSel]=useState<string|null>(null);
  const [res,setRes]=useState<{rows:Array<Record<string,unknown>>;ranAt?:string}|null>(null);
  const [busy,setBusy]=useState(false);
  const run=(k:string)=>{setSel(k);setBusy(true);setRes(null);
    fetch(`/api/admin/diagnostics?check=${k}`).then(r=>r.json())
      .then(j=>{setRes(j.ok?j:{rows:[{error:String(j.error||"failed")}]});})
      .catch(()=>setRes({rows:[{error:"network"}]})).finally(()=>setBusy(false));};
  return (<div>
    <div style={{display:"flex",flexWrap:"wrap",gap:8,marginBottom:10}}>
      {CHECKS.map(([k,label])=>(
        <button key={k} onClick={()=>run(k)} style={{background:sel===k?"#0F172A":C.s,color:sel===k?"#fff":C.tx,
          border:`1px solid ${C.bd}`,borderRadius:999,padding:"7px 13px",fontSize:12,fontWeight:600,cursor:"pointer"}}>
          {label}</button>))}
    </div>
    {busy && <div style={{fontSize:12,color:C.mt}}>running…</div>}
    {res && (res.rows?.length
      ? <div style={{overflowX:"auto"}}>{res.rows.map((r,i)=>(
          <div key={i} style={{background:C.s,border:`1px solid ${C.bd}`,borderRadius:10,padding:"9px 12px",marginBottom:6}}>
            {Object.entries(r).map(([k,v])=>(
              <div key={k} style={{display:"flex",gap:8,fontSize:11.5,lineHeight:1.5}}>
                <span style={{color:C.mt,minWidth:96,flexShrink:0}}>{k}</span>
                <span style={{fontFamily:"var(--f-mono)",fontSize:11,overflowWrap:"anywhere"}}>{v==null?"—":typeof v==="object"?JSON.stringify(v):String(v)}</span>
              </div>))}
          </div>))}
          {res.ranAt?<div style={{fontSize:10,color:C.mt}}>ran {res.ranAt}</div>:null}</div>
      : <div style={{background:C.grB,border:`1px solid ${C.grD}`,color:C.gr,borderRadius:10,
          padding:"10px 12px",fontSize:12.5,fontWeight:600}}>Empty — nothing to report ✓</div>)}
  </div>);}

function StepBoard(){
  const [steps,setSteps]=useState<Array<{step:string;ok:boolean;error?:string;ran_at:string}>|null>(null);
  const [expected,setExpected]=useState<Array<{step:string;weekly?:boolean}>>([]);
  useEffect(()=>{fetch("/api/admin/pipeline-steps").then(r=>r.json())
    .then(j=>{setSteps(j.steps||[]);setExpected(j.expected||[]);}).catch(()=>setSteps([]));},[]);
  if(steps===null)return <div style={{fontSize:12,color:C.mt}}>loading…</div>;
  if(!steps.length)return <div style={{fontSize:12,color:C.mt}}>No step log yet — populates from the next pipeline run.</div>;
  const fails=steps.filter(s=>!s.ok).length;
  // 2026-07-21: steps that SHOULD have run but left no row (the peer-PE ghost
  // was invisible for weeks). Weekly-only steps excluded unless a weekly ran.
  const ranNames=new Set(steps.map(s=>s.step));
  const weeklyRan=expected.some(e=>e.weekly&&ranNames.has(e.step));
  // 2026-07-21: comparing a HALF-FINISHED run against the full list showed
  // "26 MISSED" mid-run. If the newest row is fresh, the run is in progress —
  // suppress the missed lane until it settles.
  const lastMs=Date.parse(String(steps[steps.length-1]?.ran_at||0));
  const inProgress=Number.isFinite(lastMs)&&(Date.now()-lastMs)<15*60*1000;
  const missed=inProgress?[]:expected.filter(e=>!ranNames.has(e.step)&&(!e.weekly||weeklyRan));
  return (<div>
    <div style={{fontSize:12,fontWeight:700,marginBottom:8,color:fails||missed.length?"#B42318":C.gr}}>
      {steps.length} steps · {steps.length-fails} ✓ · {fails} ✕{missed.length?` · ${missed.length} MISSED`:""}{inProgress?" · RUN IN PROGRESS":""} · {String(steps[steps.length-1]?.ran_at).slice(0,16).replace("T"," ")}</div>
    <div style={{display:"grid",gridTemplateColumns:"1fr",gap:3}}>
      {steps.map((s2,i)=>(
        <div key={i} style={{display:"flex",alignItems:"flex-start",gap:8,padding:"5px 10px",
          background:s2.ok?C.s:"#FEF3F2",border:`1px solid ${s2.ok?C.bd:"#FECDCA"}`,borderRadius:8}}>
          <span style={{fontWeight:800,color:s2.ok?C.gr:"#B42318",flexShrink:0}}>{s2.ok?"✓":"✕"}</span>
          <span style={{fontSize:12,flex:1}}>{s2.step}</span>
          {!s2.ok&&s2.error?<span style={{fontFamily:"var(--f-mono)",fontSize:9.5,color:"#B42318",maxWidth:"46%",overflowWrap:"anywhere"}}>{s2.error.slice(0,90)}</span>:null}
        </div>))}
      {missed.map((m,i)=>(
        <div key={`m${i}`} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 10px",
          background:"#FFFAEB",border:"1px solid #FEDF89",borderRadius:8}}>
          <span style={{fontWeight:800,color:"#B54708",flexShrink:0}}>◌</span>
          <span style={{fontSize:12,flex:1,color:"#B54708"}}>{m.step}</span>
          <span style={{fontSize:9.5,color:"#B54708",fontWeight:700}}>EXPECTED — NO ROW RECORDED</span>
        </div>))}
    </div>
  </div>);}

function Failures(){
  const [rows,setRows]=useState<Array<{step:string;script:string;stderr_tail:string;failed_at:string}>|null>(null);
  useEffect(()=>{fetch("/api/admin/pipeline-failures").then(r=>r.json())
    .then(j=>setRows(j.failures||[])).catch(()=>setRows([]));},[]);
  if(rows===null)return <div style={{fontSize:12,color:C.mt}}>loading…</div>;
  if(!rows.length)return <div style={{background:C.grB,border:`1px solid ${C.grD}`,color:C.gr,
    borderRadius:10,padding:"10px 12px",fontSize:12.5,fontWeight:600}}>No failures in the last 7 days ✓</div>;
  return <div>{rows.map((f,i)=>(
    <div key={i} style={{background:C.s,border:`1px solid ${C.bd}`,borderRadius:10,padding:"10px 12px",marginBottom:8}}>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:12.5}}>
        <b>{f.step}</b><span style={{color:C.mt,fontFamily:"var(--f-mono)",fontSize:10.5}}>{String(f.failed_at).slice(0,16).replace("T"," ")}</span></div>
      <div style={{fontFamily:"var(--f-mono)",fontSize:10.5,color:C.mt,marginTop:4,whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{(f.stderr_tail||"").slice(-220)}</div>
    </div>))}</div>;}

export default function SettingsRoute() {
  return (
    <AppShell current="admin">
      <Settings />
    </AppShell>
  );
}
