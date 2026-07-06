"use client";
// app/dashboard/settings/page.tsx — set service secrets from the phone.
import { useEffect, useState } from "react";
const C={bg:"#FAFAF8",s:"#FFF",bd:"#E5E7EB",tx:"#111827",mt:"#6B7280",gr:"#16A34A",grB:"#F0FDF4",grD:"#BBF7D0"};
const FIELDS=[["screener_username","Screener.in email"],["screener_password","Screener.in password"],["ntfy_topic","ntfy topic (push notifications)"]];
export default function Settings(){
  const [state,setState]=useState<Record<string,string>>({});
  const [vals,setVals]=useState<Record<string,string>>({});
  const [msg,setMsg]=useState("");
  const load=()=>fetch("/api/admin/secrets").then(r=>r.json()).then(j=>setState(j.state||{}));
  useEffect(()=>{load();},[]);
  const save=(k:string)=>fetch("/api/admin/secrets",{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,value:vals[k]||""})})
    .then(r=>r.ok?(setMsg(k+" saved ✓"),setVals(v=>({...v,[k]:""})),load()):setMsg("save failed"));
  return(<div style={{padding:"18px 20px",background:C.bg,minHeight:"100vh",maxWidth:640,margin:"auto",
    color:C.tx,font:'14px/1.5 -apple-system,"Segoe UI",Inter,sans-serif'}}>
    <h1 style={{fontSize:19,fontWeight:800,margin:"0 0 4px"}}>⚙️ Service secrets</h1>
    <p style={{fontSize:12.5,color:C.mt,margin:"0 0 16px"}}>Stored in platform_config (same vault as the Kite token). Scripts &amp; auth read them automatically — no SSH, no Vercel.</p>
    {msg&&<div style={{background:C.grB,border:`1px solid ${C.grD}`,color:C.gr,borderRadius:8,padding:"8px 12px",fontSize:12.5,fontWeight:600,marginBottom:12}}>{msg}</div>}
    {FIELDS.map(([k,label])=>(
      <div key={k} style={{background:C.s,border:`1px solid ${C.bd}`,borderRadius:12,padding:14,marginBottom:12}}>
        <div style={{fontWeight:700,fontSize:13.5}}>{label}</div>
        <div style={{fontSize:11.5,color:C.mt,marginBottom:8}}>status: {state[k]||"…"}</div>
        <div style={{display:"flex",gap:8}}>
          <input type={k.includes("password")?"password":"text"} value={vals[k]||""}
            onChange={e=>setVals(v=>({...v,[k]:e.target.value}))}
            placeholder="new value" style={{flex:1,border:`1px solid ${C.bd}`,borderRadius:8,
            padding:"9px 11px",fontSize:13}}/>
          <button onClick={()=>save(k)} disabled={!(vals[k]||"").trim()}
            style={{border:`1px solid ${C.grD}`,background:C.grB,color:C.gr,borderRadius:8,
            padding:"9px 14px",fontSize:13,fontWeight:700,cursor:"pointer"}}>Save</button>
        </div>
      </div>))}
  </div>);}
