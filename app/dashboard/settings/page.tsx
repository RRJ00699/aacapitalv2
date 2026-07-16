"use client";
// app/dashboard/settings/page.tsx — set service secrets from the phone.
import AppShell from "@/components/app-shell/AppShell";
import { useEffect, useState } from "react";
const C={bg:"var(--t-bg)",s:"var(--t-surface)",bd:"var(--t-border)",tx:"var(--t-text)",mt:"var(--t-meta)",gr:"var(--t-green)",grB:"var(--t-greenBg)",grD:"var(--t-greenBd)"};
const FIELDS=[["ipomatrix_cookie","IPOMatrix cookie / JWT (x-access-token — ~30d expiry, status shows the date)"],["screener_username","Screener.in email"],["screener_password","Screener.in password"],["screener_cookie","Screener.in cookie (bypasses login — paste from browser DevTools)"],["zerodha_totp_secret","Zerodha TOTP secret (for the 08:45 auto-login — from Kite 2FA setup)"],["kite_api_key","Kite Connect API key"],["kite_api_secret","Kite Connect API secret"],["ntfy_topic","ntfy topic (push notifications)"]];
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
  </div>);}

export default function SettingsRoute() {
  return (
    <AppShell current="admin">
      <Settings />
    </AppShell>
  );
}
