"use client";
// app/dashboard/access/page.tsx — approve/deny access requests, on the fly.
import { useEffect, useState, useCallback } from "react";
const C = { bg:"#FAFAF8", s:"#FFF", bd:"#E5E7EB", tx:"#111827", mt:"#6B7280", dim:"#9CA3AF",
  gr:"#16A34A", grB:"#F0FDF4", grD:"#BBF7D0", rd:"#DC2626", rdB:"#FEF2F2", rdD:"#FECACA", gy:"#F3F4F6" };
type R = Record<string, unknown>;
export default function Access() {
  const [d, setD] = useState<{requests:R[];allowed:R[]}|null>(null);
  const [err, setErr] = useState<string|null>(null);
  const load = useCallback(() => {
    fetch("/api/admin/access").then(r=>r.json())
      .then(j => j.error ? setErr(j.error) : (setErr(null), setD(j)))
      .catch(e=>setErr(String(e)));
  }, []);
  useEffect(() => { load(); }, [load]);
  const act = (email:string, action:string) =>
    fetch("/api/admin/access", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ email, action }) }).then(load);
  const card: React.CSSProperties = { background:C.s, border:`1px solid ${C.bd}`,
    borderRadius:12, padding:16, marginBottom:14 };
  const btn = (bg:string,bd:string,c:string): React.CSSProperties => ({ border:`1px solid ${bd}`,
    background:bg, color:c, borderRadius:8, padding:"6px 12px", fontSize:12.5, fontWeight:700, cursor:"pointer" });
  const pending = (d?.requests||[]).filter(r=>r.status==="pending");
  return (
    <div style={{padding:"18px 20px",background:C.bg,minHeight:"100vh",maxWidth:760,margin:"auto",
      color:C.tx,font:'14px/1.5 -apple-system,"Segoe UI",Inter,sans-serif'}}>
        <a href="/dashboard/admin" style={{display:"inline-block",fontSize:13,fontWeight:600,
        color:"#2563EB",textDecoration:"none",background:"#EFF6FF",border:"1px solid #BFDBFE",
        borderRadius:8,padding:"5px 10px",marginBottom:12}}>← Admin</a>
    <h1 style={{fontSize:19,fontWeight:800,margin:"0 0 2px"}}>🔑 Access requests</h1>
      <p style={{fontSize:12.5,color:C.mt,margin:"0 0 16px"}}>Approve on the fly — the person just signs in again after approval. No Google console, ever.</p>
      {err && <div style={{...card,borderColor:C.rdD,color:C.rd}}>{err}</div>}
      <div style={card}>
        <b style={{fontSize:14}}>Pending {pending.length ? `(${pending.length})` : ""}</b>
        {!pending.length && <div style={{fontSize:13,color:C.dim,marginTop:8}}>No pending requests.</div>}
        {pending.map((r,i)=>(
          <div key={i} style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap",
            padding:"10px 0",borderTop:i? `1px solid ${C.bd}`:"none",marginTop:i?4:8}}>
            <div style={{flex:1,minWidth:200}}>
              <div style={{fontWeight:700}}>{String(r.name||"(no name)")}</div>
              <div style={{fontSize:12.5,color:C.mt}}>{String(r.email)} · {String(r.requested_at||"").slice(0,16).replace("T"," ")}</div>
              {r.note ? <div style={{fontSize:12.5,color:C.tx,marginTop:2}}>&ldquo;{String(r.note)}&rdquo;</div> : null}
            </div>
            <button style={btn(C.grB,C.grD,C.gr)} onClick={()=>act(String(r.email),"approve")}>✓ Approve</button>
            <button style={btn(C.rdB,C.rdD,C.rd)} onClick={()=>act(String(r.email),"deny")}>✕ Deny</button>
          </div>))}
      </div>
      <div style={card}>
        <b style={{fontSize:14}}>Approved users</b>
        {(d?.allowed||[]).map((r,i)=>(
          <div key={i} style={{display:"flex",gap:10,alignItems:"center",padding:"9px 0",
            borderTop:i?`1px solid ${C.bd}`:"none",marginTop:i?4:8}}>
            <div style={{flex:1,fontSize:13}}>{String(r.email)}
              <span style={{color:C.dim,fontSize:12}}> · added {String(r.added_at||"").slice(0,10)}</span></div>
            <button style={btn(C.gy,C.bd,C.mt)} onClick={()=>act(String(r.email),"revoke")}>Revoke</button>
          </div>))}
        {!(d?.allowed||[]).length && <div style={{fontSize:13,color:C.dim,marginTop:8}}>None yet — family stays on the env allowlist; this list is for on-the-fly grants.</div>}
      </div>
      <p style={{fontSize:11.5,color:C.dim}}>Push notifications: install the free <b>ntfy</b> app, subscribe to your topic, set NTFY_TOPIC in Vercel env. Requests appear here regardless.</p>
    </div>);
}
