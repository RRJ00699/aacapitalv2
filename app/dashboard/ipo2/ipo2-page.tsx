"use client";
// app/dashboard/ipo2/page.tsx — the locked redesign, wired to /api/ipo-command.
// Self-contained: no imports from the 3 legacy shells. Polls every 20s while a
// live capture exists. Ships at /dashboard/ipo2 for side-by-side verification;
// cutover to /dashboard/ipo is a separate one-line commit after approval.
import { useEffect, useState, useCallback } from "react";

const C = { bg:"#FAFAF8", surface:"#FFFFFF", border:"#E5E7EB", text:"#111827",
  sub:"#374151", meta:"#6B7280", dim:"#9CA3AF",
  green:"#16A34A", greenBg:"#F0FDF4", greenBd:"#BBF7D0",
  blue:"#2563EB", blueBg:"#EFF6FF", blueBd:"#BFDBFE",
  amber:"#D97706", amberBg:"#FFFBEB", amberBd:"#FDE68A",
  red:"#DC2626", redBg:"#FEF2F2", redBd:"#FECACA", grayBg:"#F3F4F6" };
const MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace";

const BAND: Record<string,{c:string;bg:string;bd:string}> = {
  STRONG:{c:C.green,bg:C.greenBg,bd:C.greenBd}, FAVORABLE:{c:C.blue,bg:C.blueBg,bd:C.blueBd},
  NEUTRAL:{c:C.meta,bg:C.grayBg,bd:C.border}, AVOID:{c:C.red,bg:C.redBg,bd:C.redBd} };
const PLAYS = [
  { t:"MID gap (+4% to +15% open) — THE EDGE", s:"84.1% · +9.4% · n=69", c:C.green,
    d:"Let it run. Peak strength ~session 8-18. Best cell: MID × 500-2000cr = 82%/+10.9. No day-1 profit-taking." },
  { t:"Mega issue (>₹2000cr) — any gap", s:"81.8% · +9.2% · n=77", c:C.blue,
    d:"Institutions must build positions after listing. Works even on HIGH gaps (92%, n=12 hint)." },
  { t:"LOW gap (<+4%)", s:"70.8% · +5.2% · n=212", c:C.meta,
    d:"Steady, manage to floor. Only ≥₹500cr — LOW × 150-500cr is a coin flip (50%/+0.4)." },
  { t:"HIGH gap (>+15%)", s:"64.0% · +5.4% · n=89", c:C.amber,
    d:"Pop & fade — exit fast if taken. Decayed to 50% in 2025+. Exception: mega-size." },
  { t:"SKIP: ₹150-500cr + LOW/HIGH · PE 30-60 middles", s:"51.2% · +0.8% · n=84", c:C.red,
    d:"The AVOID band wins only 36% in 2025+. Skipping these IS the profit." } ];

type R = Record<string, unknown>;
const N = (v: unknown) => (v == null ? null : Number(v));
const D = (v: unknown) => String(v ?? "").slice(0, 10);

function Chip({ b }: { b?: string | null }) {
  const s = BAND[b || ""] || BAND.NEUTRAL;
  return <span style={{color:s.c,background:s.bg,border:`1px solid ${s.bd}`,borderRadius:8,
    padding:"2px 9px",fontSize:11,fontWeight:700}}>{b || "UNSCORED"}</span>;
}
function State({ s }: { s?: string | null }) {
  const m: Record<string,[string,string,string]> = {
    LISTING:[C.red,C.redBg,C.redBd], OPEN:[C.green,C.greenBg,C.greenBd],
    UPCOMING:[C.blue,C.blueBg,C.blueBd], INWINDOW:[C.meta,C.grayBg,C.border] };
  const [c,bg,bd] = m[s || ""] || m.INWINDOW;
  return <span style={{color:c,background:bg,border:`1px solid ${bd}`,borderRadius:8,
    padding:"2px 9px",fontSize:11,fontWeight:700}}>{s || ""}</span>;
}
const card: React.CSSProperties = { background:C.surface, border:`1px solid ${C.border}`,
  borderRadius:12, padding:"14px 16px", marginBottom:12 };
const th: React.CSSProperties = { textAlign:"left", fontSize:10.5, color:C.meta,
  textTransform:"uppercase", letterSpacing:.5, padding:"7px 8px", borderBottom:`1px solid ${C.border}` };
const td: React.CSSProperties = { fontSize:13, color:C.sub, padding:"7px 8px",
  borderBottom:`1px solid ${C.border}` };
const num: React.CSSProperties = { fontFamily:MONO, fontVariantNumeric:"tabular-nums" };

function Spark({ ticks, floor, ceil }: { ticks: R[]; floor: number|null; ceil: number|null }) {
  const px = ticks.map(t => N(t.ltp)).filter((x): x is number => x != null);
  const vw = ticks.map(t => N(t.vwap)).filter((x): x is number => x != null);
  if (px.length < 2) return <div style={{fontSize:12,color:C.dim,padding:"18px 0"}}>Collecting ticks…</div>;
  const all = [...px, ...vw, ...(floor?[floor]:[]), ...(ceil?[ceil]:[])];
  const lo = Math.min(...all), hi = Math.max(...all), sp = hi - lo || 1;
  const W = 640, H = 150, y = (v:number) => 12 + (1-(v-lo)/sp)*(H-24);
  const path = (a:number[]) => a.map((v,i)=>`${i?"L":"M"}${(i/(a.length-1))*W},${y(v)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%"}}>
      {ceil != null && floor != null &&
        <rect x="0" y={y(ceil)} width={W} height={Math.max(0,y(floor)-y(ceil))} fill="#EFF6FF"/>}
      {ceil != null && <><line x1="0" y1={y(ceil)} x2={W} y2={y(ceil)} stroke={C.blue} strokeDasharray="6 4"/>
        <text x="5" y={y(ceil)-4} fontSize="10" fill={C.blue}>ceiling ₹{ceil}</text></>}
      {floor != null && <><line x1="0" y1={y(floor)} x2={W} y2={y(floor)} stroke={C.red} strokeDasharray="6 4"/>
        <text x="5" y={y(floor)+12} fontSize="10" fill={C.red}>floor ₹{floor} · respected 78%/75% hist.</text></>}
      <path d={path(vw)} fill="none" stroke={C.dim} strokeWidth="1.7" strokeDasharray="2 4"/>
      <path d={path(px)} fill="none" stroke={C.green} strokeWidth="2.3"/>
    </svg>);
}

export default function IpoCommand() {
  const [d, setD] = useState<{cards:R[];live:R[];levels:R[];blocks:R[];post:R[];brlm:R[]}|null>(null);
  const [err, setErr] = useState<string|null>(null);
  const [view, setView] = useState("command");
  const loadData = useCallback(() => {
    fetch("/api/ipo-command").then(r=>r.json())
      .then(j => j.error ? setErr(j.error) : (setErr(null), setD(j)))
      .catch(e => setErr(String(e)));
  }, []);
  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    if (!d?.live?.length) return;
    const id = setInterval(loadData, 20000);
    return () => clearInterval(id);
  }, [d?.live?.length, loadData]);

  const cards = d?.cards || [];
  const liveSyms = Array.from(new Set((d?.live||[]).map(t=>String(t.symbol))));
  const next = cards.find(c=>c.state==="UPCOMING");
  const pills: [string,string][] = [["command","⚡ Command Center"],["pb","🎯 Quick Profit Playbook"],
    ["open","📋 Open Now"],["upcoming","📅 Upcoming"],["post","📈 Post-Listing"],["brlm","🏆 BRLM"]];

  return (
    <div style={{padding:"16px 20px",background:C.bg,minHeight:"100vh",maxWidth:1180,margin:"auto",
      font:'14px/1.45 -apple-system,"Segoe UI",Inter,Roboto,sans-serif',color:C.text}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",flexWrap:"wrap",gap:10}}>
        <div><h1 style={{fontSize:20,fontWeight:800,margin:0}}>⚡ IPO Command Center</h1>
          <div style={{fontSize:12,color:C.meta}}>Nightly pipeline · Chittorgarh + SBI + NSE + Kite ·
            {d ? ` refreshed ${new Date().toLocaleTimeString()}` : " loading…"}</div></div>
        <button onClick={loadData} style={{border:`1px solid ${C.border}`,background:C.surface,
          borderRadius:10,padding:"6px 13px",fontSize:12.5,fontWeight:600,cursor:"pointer"}}>↻ Refresh</button>
      </div>

      {/* engine strip — validated score v0 */}
      <div style={{...card,marginTop:12,display:"flex",gap:22,alignItems:"center",flexWrap:"wrap"}}>
        <div style={{maxWidth:290}}><div style={{fontWeight:800,fontSize:13}}>SCORE v0 · buy open → best close ≤10 sessions</div>
          <div style={{fontSize:12,color:C.meta}}>n=370 (2010–26) · validated 2026-07-05 · monotonic</div></div>
        {[["Strong","89.5%","+9.4% · n=38",C.green],["Favorable","76.0%","+8.7% · n=96",C.blue],
          ["Baseline","72%","+5.9% · n=370",C.text],["Avoid","51.2%","+0.8% · n=84",C.red]].map((s,i)=>(
          <div key={i}><div style={{fontSize:10.5,color:C.meta,textTransform:"uppercase"}}>{s[0]}</div>
            <div style={{...num,fontSize:19,fontWeight:800,color:s[3] as string}}>{s[1]}</div>
            <div style={{...num,fontSize:12,color:C.meta}}>{s[2]}</div></div>))}
        <a href="/dashboard/research" style={{marginLeft:"auto",fontSize:12.5,color:C.blue,fontWeight:600}}>Full evidence →</a>
      </div>

      <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"12px 0"}}>
        {pills.map(([k,l])=>(
          <span key={k} onClick={()=>setView(k)} style={{cursor:"pointer",userSelect:"none",
            border:`1px solid ${view===k?C.blueBd:C.border}`,background:view===k?C.blueBg:C.surface,
            color:view===k?C.blue:C.sub,borderRadius:20,padding:"7px 15px",fontSize:13,fontWeight:600}}>{l}</span>))}
      </div>
      {err && <div style={{...card,borderColor:C.redBd,color:C.red,fontSize:13}}>API error: {err}</div>}

      {/* COMMAND */}
      {view==="command" && <>
        <div style={{fontSize:12,color:C.meta,margin:"0 2px 8px"}}>
          {liveSyms.length ? `🔴 ${liveSyms.length} live capture` : "no live capture"} ·
          next listing {next ? `${next.company_name} ${D(next.listing_date)}` : "—"} ·
          launcher 09:10 · self-check 09:25 &amp; 13:00
        </div>
        {liveSyms.map(sym => {
          const ticks = (d!.live).filter(t=>t.symbol===sym);
          const last = ticks[ticks.length-1] || {};
          const lv = (d!.levels).find(l=>l.symbol===sym) || {};
          const meta = cards.find(c=>c.sym===sym) || {};
          const blk = (d!.blocks).filter(b=>b.symbol===sym);
          const ltp = N(last.ltp), vwap = N(last.vwap), open = N(lv.listing_open);
          return (
            <div key={sym} style={{...card,borderColor:C.greenBd,borderWidth:2}}>
              <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
                <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
                  <b style={{fontSize:16}}>{sym} · {String(meta.company_name||"")}</b>
                  <span style={{color:C.green,fontWeight:700,fontSize:12}}>● LIVE</span>
                  <Chip b={meta.score_band as string}/>
                  <span style={{fontSize:12,color:C.meta}}>{String(meta.score_evidence||"")}</span>
                </div>
                <span style={{fontSize:12,color:C.meta}}>gap {lv.gap_pct!=null?`${lv.gap_pct}% ${lv.gap_bucket||""}`:"—"} · verdict: {String(lv.verdict||"—")}</span>
              </div>
              <div style={{display:"flex",gap:14,flexWrap:"wrap",marginTop:10}}>
                <div style={{flex:2,minWidth:420}}>
                  <div style={{display:"flex",gap:16,alignItems:"baseline",flexWrap:"wrap"}}>
                    <span style={{...num,fontSize:28,fontWeight:800}}>{ltp!=null?`₹${ltp}`:"—"}</span>
                    {ltp!=null&&open!=null&&open>0&&<span style={{...num,fontWeight:700,
                      color:ltp>=open?C.green:C.red}}>{((ltp-open)/open*100).toFixed(1)}% vs open ₹{open}</span>}
                    {vwap!=null&&<span style={{...num,fontSize:12,color:C.meta}}>VWAP ₹{vwap} · {ltp!=null&&ltp>=vwap?"above":"below"}</span>}
                  </div>
                  <Spark ticks={ticks} floor={N(lv.floor_price)} ceil={N(lv.ceiling_price)}/>
                  <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8,marginTop:8}}>
                    {[["OBIR",last.obir,N(last.obir)!=null&&N(last.obir)!>=1?C.green:C.red],
                      ["Momentum",last.momentum,C.text],["Signal",last.signal,C.text],
                      ["Floor defenses",lv.floor_defenses,C.text]].map((t,i)=>(
                      <div key={i} style={{border:`1px solid ${C.border}`,borderRadius:9,padding:"8px 10px"}}>
                        <div style={{fontSize:10,color:C.meta,textTransform:"uppercase"}}>{t[0] as string}</div>
                        <div style={{...num,fontSize:15,fontWeight:800,color:t[2] as string}}>{String(t[1]??"—")}</div></div>))}
                  </div>
                </div>
                <div style={{flex:1,minWidth:290}}>
                  <div style={{fontSize:10.5,color:C.meta,fontWeight:700,textTransform:"uppercase",marginBottom:6}}>Order flow · blocks (≥3× median clip)</div>
                  {blk.length===0&&<div style={{fontSize:12.5,color:C.dim}}>No outsized prints yet.</div>}
                  {blk.map((b,i)=>(
                    <div key={i} style={{display:"flex",gap:8,fontSize:12.5,padding:"6px 9px",borderRadius:8,
                      border:`1px solid ${C.greenBd}`,background:C.greenBg,marginBottom:6}}>
                      <span style={{...num,fontSize:10.5,color:C.dim,minWidth:42}}>{String(b.at).slice(11,16)}</span>
                      <span><b>{Number(b.qty).toLocaleString()} @ ₹{String(b.price)}</b> — {String(b.mult)}× median</span></div>))}
                  <div style={{fontSize:12,color:C.meta,marginTop:8}}>
                    {String(lv.risk_note||"")} {lv.circuit_locked?" · ⚠ circuit locked":""}</div>
                </div>
              </div>
            </div>);
        })}
        {cards.filter(c=>c.state!=="INWINDOW"||liveSyms.includes(String(c.sym))===false).map((c,i)=>(
          liveSyms.includes(String(c.sym)) ? null :
          <div key={i} style={card}>
            <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
              <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
                <b>{String(c.company_name||"")}</b><State s={c.state as string}/><Chip b={c.score_band as string}/>
                <span style={{fontSize:12,color:C.meta}}>{String(c.score_evidence||"")}</span></div>
              <span style={{...num,fontSize:12,color:C.meta}}>
                {c.issue_price!=null?`₹${c.issue_price} · `:""}{c.issue_size_cr!=null?`₹${Number(c.issue_size_cr).toLocaleString()}Cr`:""}
                {c.listing_date?` · lists ${D(c.listing_date)}`:""}</span></div>
            {c.final_qib!=null&&<div style={{display:"flex",gap:12,alignItems:"center",marginTop:8,flexWrap:"wrap"}}>
              <span style={{fontSize:12,color:C.meta,minWidth:30}}>QIB</span>
              <div style={{height:7,borderRadius:4,background:C.grayBg,flex:1,minWidth:120,position:"relative",overflow:"hidden"}}>
                <div style={{position:"absolute",inset:0,width:`${Math.min(100,Number(c.final_qib))}%`,background:C.green,borderRadius:4}}/></div>
              <span style={{...num,fontWeight:700,color:C.green}}>{Number(c.final_qib).toFixed(1)}×</span>
              {c.final_total!=null&&<span style={{...num,fontSize:12,color:C.meta}}>Total {Number(c.final_total).toFixed(1)}×</span>}
              <span style={{fontSize:12,color:C.dim}}>demand ≠ edge — QIB level tested non-predictive</span></div>}
          </div>))}
      </>}

      {/* PLAYBOOK */}
      {view==="pb" && <>
        <div style={card}><b style={{fontSize:14}}>The playbook — what to do, by setup.</b>
          <div style={{fontSize:12.5,color:C.meta,marginTop:4}}>Entry: buy at listing open only when the setup qualifies.
            Exit: best close ≤10 sessions · hard invalidation on a close below the floor.</div></div>
        {PLAYS.map((p,i)=>(
          <div key={i} style={{...card,borderLeft:`4px solid ${p.c}`,borderRadius:"0 12px 12px 0"}}>
            <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:6}}>
              <b>{p.t}</b><span style={{...num,fontWeight:800,color:p.c}}>{p.s}</span></div>
            <div style={{fontSize:12.5,color:C.meta,marginTop:4}}>{p.d}</div></div>))}
        <div style={card}><b style={{fontSize:13}}>Risk, always on screen</b>
          <div style={{fontSize:12.5,color:C.meta,marginTop:4}}>Drawdown median −9% · tail −22% — size for the tail.
            Floor = first-5-session low, respected 78%; a close below it is the exit, not a dip-buy.
            GMP = context only · QIB level = priced in · ROE = noise. All tested.</div></div>
      </>}

      {/* OPEN NOW */}
      {view==="open" && <>
        {cards.filter(c=>c.state==="OPEN").map((c,i)=>(
          <div key={i} style={card}>
            <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
              <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
                <b>{String(c.company_name||"")}</b>
                <span style={{fontSize:12,color:C.meta}}>closes {D(c.close_date)}</span>
                <Chip b={c.score_band as string}/></div>
              <span style={{...num,fontSize:12,color:C.meta}}>₹{String(c.issue_price??"—")} · ₹{Number(c.issue_size_cr||0).toLocaleString()}Cr</span></div>
            {[["QIB",c.final_qib],["NII",c.final_nii],["Retail",c.final_retail]].map(([k,v],j)=>(
              v==null?null:
              <div key={j} style={{display:"flex",gap:12,alignItems:"center",marginTop:7}}>
                <span style={{fontSize:12,color:C.meta,minWidth:40}}>{k as string}</span>
                <div style={{height:7,borderRadius:4,background:C.grayBg,flex:1,position:"relative",overflow:"hidden"}}>
                  <div style={{position:"absolute",inset:0,width:`${Math.min(100,Number(v))}%`,background:C.green,borderRadius:4}}/></div>
                <span style={{...num,fontWeight:700}}>{Number(v).toFixed(1)}×</span></div>))}
            <div style={{fontSize:12,color:C.dim,marginTop:8}}>Figures = last nightly sync · live intraday capture is the next data build. QIBs bid late — a low day-1 is normal.</div>
          </div>))}
        {cards.filter(c=>c.state==="OPEN").length===0&&<div style={card}><span style={{fontSize:13,color:C.meta}}>No IPO is open for bidding right now.</span></div>}
      </>}

      {/* UPCOMING */}
      {view==="upcoming" && <div style={card}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead><tr><th style={th}>Lists</th><th style={th}>Company</th><th style={th}>Size</th><th style={th}>Band</th><th style={th}>Evidence / status</th></tr></thead>
          <tbody>{cards.filter(c=>c.state==="UPCOMING"||c.state==="LISTING").map((c,i)=>(
            <tr key={i}><td style={{...td,...num}}>{D(c.listing_date)}</td>
              <td style={{...td,fontWeight:600,color:C.text}}>{String(c.company_name||"")}</td>
              <td style={{...td,...num}}>{c.issue_size_cr!=null?`₹${Number(c.issue_size_cr).toLocaleString()}cr`:"—"}</td>
              <td style={td}><Chip b={c.score_band as string}/></td>
              <td style={{...td,fontSize:12,color:C.meta}}>{String(c.score_evidence||"—")}</td></tr>))}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Pre-listing scores use size/valuation only — the gap weight applies itself at the open.</div>
      </div>}

      {/* POST-LISTING AUDIT */}
      {view==="post" && <div style={card}>
        <b style={{fontSize:14}}>Score vs reality — the standing audit</b>
        <table style={{width:"100%",borderCollapse:"collapse",marginTop:8}}>
          <thead><tr><th style={th}>Listed</th><th style={th}>Company</th><th style={th}>Band</th>
            <th style={th}>Gap</th><th style={th}>Listing gap</th><th style={th}>10-session best</th></tr></thead>
          <tbody>{(d?.post||[]).map((r,i)=>(
            <tr key={i}><td style={{...td,...num}}>{D(r.listing_date)}</td>
              <td style={{...td,fontWeight:600,color:C.text}}>{String(r.company_name||"")}</td>
              <td style={td}><Chip b={r.score_band as string}/></td>
              <td style={td}>{String(r.gap_bucket||"—")}</td>
              <td style={{...td,...num}}>{r.listing_gap_pct!=null?`${Number(r.listing_gap_pct).toFixed(1)}%`:"—"}</td>
              <td style={{...td,...num,fontWeight:700,color:N(r.d10_best_pct)==null?C.dim:(N(r.d10_best_pct)!>0?C.green:C.red)}}>
                {r.d10_best_pct!=null?`${Number(r.d10_best_pct).toFixed(1)}%`:"pending"}</td></tr>))}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Misses feed the quarterly re-weight. 10-session outcomes precompute nightly.</div>
      </div>}

      {/* BRLM */}
      {view==="brlm" && <div style={card}>
        <b style={{fontSize:14}}>Book managers — empirical, from our own outcomes</b>
        <table style={{width:"100%",borderCollapse:"collapse",marginTop:8}}>
          <thead><tr><th style={th}>Lead manager</th><th style={th}>IPOs</th><th style={th}>Pop rate</th>
            <th style={th}>Med gap</th><th style={th}>10s win</th><th style={th}>10s median</th></tr></thead>
          <tbody>{(d?.brlm||[]).map((r,i)=>(
            <tr key={i}><td style={{...td,fontWeight:600,color:C.text}}>{String(r.lead||"")}</td>
              <td style={{...td,...num}}>{String(r.n)}</td>
              <td style={{...td,...num}}>{r.pop_rate!=null?`${r.pop_rate}%`:"—"}</td>
              <td style={{...td,...num}}>{r.med_gap!=null?`${Number(r.med_gap).toFixed(1)}%`:"—"}</td>
              <td style={{...td,...num,fontWeight:700}}>{r.d10_win!=null?`${r.d10_win}%`:"pending"}</td>
              <td style={{...td,...num}}>{r.d10_med!=null?`${Number(r.d10_med).toFixed(1)}%`:"pending"}</td></tr>))}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Lead = first-named manager · cells need n≥8 · "pending" fills after tonight's d10 precompute.</div>
      </div>}
    </div>
  );
}
