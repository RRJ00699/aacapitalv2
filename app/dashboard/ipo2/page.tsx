"use client";
// app/dashboard/ipo2/page.tsx — the locked redesign, wired to /api/ipo-command.
// Self-contained: no imports from the 3 legacy shells. Polls every 20s while a
// live capture exists. Ships at /dashboard/ipo2 for side-by-side verification;
// cutover to /dashboard/ipo is a separate one-line commit after approval.
import { useEffect, useState, useCallback } from "react";
import { useThemeControls } from "@/lib/theme";
import AppShell from "@/components/app-shell/AppShell";
import MarketsSidebar from "@/components/ipo/MarketsSidebar";

const C = { bg:"var(--t-bg)", surface:"var(--t-surface)", surface2:"var(--t-surface2)", border:"var(--t-border)", line:"var(--t-line)", text:"var(--t-text)",
  sub:"var(--t-sub)", meta:"var(--t-meta)", dim:"var(--t-dim)",
  green:"var(--t-green)", greenBg:"var(--t-greenBg)", greenBd:"var(--t-greenBd)",
  blue:"var(--t-blue)", blueBg:"var(--t-blueBg)", blueBd:"var(--t-blueBd)",
  amber:"var(--t-amber)", amberBg:"var(--t-amberBg)", amberBd:"var(--t-amberBd)",
  red:"var(--t-red)", redBg:"var(--t-redBg)", redBd:"var(--t-redBd)", grayBg:"var(--t-grayBg)", gold:"var(--t-gold)" };
const MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace";

function ThemeToggle() {
  const { mode, isDark, setMode } = useThemeControls();
  // cycle: auto → light → dark → auto
  const next = mode === "auto" ? "light" : mode === "light" ? "dark" : "auto";
  const label = mode === "auto" ? "🌗 Auto" : mode === "light" ? "☀️ Day" : "🌙 Night";
  return (
    <button onClick={() => setMode(next)}
      title={`Theme: ${mode} (tap to change)`}
      style={{ border:`1px solid ${C.border}`, background:C.surface, color:C.text,
        borderRadius:10, padding:"6px 13px", fontSize:12.5, fontWeight:600, cursor:"pointer" }}>
      {label}
    </button>
  );
}

const BAND: Record<string,{c:string;bg:string;bd:string}> = {
  STRONG:{c:C.green,bg:C.greenBg,bd:C.greenBd}, FAVORABLE:{c:C.blue,bg:C.blueBg,bd:C.blueBd},
  NEUTRAL:{c:C.meta,bg:C.grayBg,bd:C.border}, AVOID:{c:C.red,bg:C.redBg,bd:C.redBd} };
const PLAYS = [
  { t:"1 · MEGA issue (>₹2000cr) opening positive — THE CORE TRADE", s:"92% win · +19% med · positive floor", c:C.green,
    d:"A large issue (over ₹2000 crore) that opens at or above its IPO price. Best when it opens +15% or more. Buy at listing open. Two iterations passed (2026-07-10 and 2026-07-13); even the unlucky day stays positive. Institutions must keep buying these for weeks — the price is supported." },
  { t:"2 · MORE THAN 30 ANCHORS — confirmed buy signal", s:"77% win vs 68% · tail halves", c:C.green,
    d:"Tested 2026-07-13. IPOs with 30+ anchor investors win 77% buying at open (vs 68% below 30), and the downside tail shrinks from −6.6% to −2.6%. 50+ anchors is even stronger (79%). A heavy anchor book means big institutions are committed." },
  { t:"3 · THE STACK — 30+ anchors + mega + positive open", s:"85% win · +13% med · ~zero floor", c:C.green,
    d:"Tested 2026-07-13. Layer the two edges: a mega issue, opening positive, with 30+ anchors = 85% win and a near-zero downside. The single cleanest setup. When all three line up, this is the trade." },
  { t:"4 · LOW PRICE BAND + FRESH ISSUE — strong", s:"82–90% win · small tail", c:C.blue,
    d:"Tested 2026-07-13. Cheaper bands (under ₹300) win far more at open (77–90%) than expensive ones (₹600+ sag to 58%). Fresh-issue IPOs (under 30% OFS) win 82% vs OFS-heavy. Cheap + fresh + 30 anchors reached 94% (small sample — promising)." },
  { t:"AVOID · small, pricey, or euphoric", s:"skip — this is the profit", c:C.red,
    d:"Under ₹500cr: 63% win, worst tail — skip. Band over ₹600 or OFS-heavy: weak. Opened +50% or more: the pop is priced in and ~1 in 3.5 fades to a loss. Skipping these IS the strategy." },
  { t:"GATE · RHP quality read (before listing)", s:"junk filter, not the entry", c:C.amber,
    d:"Before listing, the RHP forensic read flags clean / watch / reject. A reject is a hard pass regardless of how it opens. This is the quality filter that keeps junk out — separate from the buy-at-open signals above." } ];

type R = Record<string, unknown>;
const N = (v: unknown) => (v == null ? null : Number(v));
const D = (v: unknown) => String(v ?? "").slice(0, 10);

function Chip({ b }: { b?: string | null }) {
  const s = BAND[b || ""] || BAND.NEUTRAL;
  const TIP: Record<string,string> = { STRONG:"9 of 10 like this made money (15-yr history)",
    FAVORABLE:"7.6 of 10 like this made money", NEUTRAL:"about average — 7 of 10 made money",
    AVOID:"a coin flip historically — we skip these" };
  return <span title={TIP[b || ""] || "not enough data to grade yet"}
    style={{color:s.c,background:s.bg,border:`1px solid ${s.bd}`,borderRadius:8,
    padding:"2px 9px",fontSize:11,fontWeight:700,cursor:"help"}}>{b || "UNSCORED"}</span>;
}
function State({ s }: { s?: string | null }) {
  const m: Record<string,[string,string,string]> = {
    LISTING:[C.red,C.redBg,C.redBd], OPEN:[C.green,C.greenBg,C.greenBd],
    UPCOMING:[C.blue,C.blueBg,C.blueBd], INWINDOW:[C.meta,C.grayBg,C.border] };
  const [c,bg,bd] = m[s || ""] || m.INWINDOW;
  return <span style={{color:c,background:bg,border:`1px solid ${bd}`,borderRadius:8,
    padding:"2px 9px",fontSize:11,fontWeight:700}}>{s || ""}</span>;
}
function Verdict({ v }: { v?: string | null }) {
  const m: Record<string,[string,string,string]> = {
    TRADE:[C.green,C.greenBg,C.greenBd], CAUTION:["#c2830c","#fdf6e6","#f0dfae"],
    WATCH:[C.blue,C.blueBg,C.blueBd], AVOID:[C.red,C.redBg,C.redBd] };
  const [c,bg,bd] = m[v || ""] || m.CAUTION;
  const icon = v==="TRADE"?"✓ ":v==="AVOID"?"✕ ":v==="WATCH"?"👁 ":"⚠ ";
  return <span style={{color:c,background:bg,border:`1px solid ${bd}`,borderRadius:8,
    padding:"4px 11px",fontSize:11,fontWeight:800,letterSpacing:.4,textTransform:"uppercase"}}>
    {icon}{v || "CAUTION"}</span>;
}
function QTag() {
  return <span style={{color:C.gold||"#c99a2e",background:"#fdf7e6",border:"1px solid #f0dfae",
    borderRadius:5,padding:"2px 8px",fontSize:9.5,fontWeight:800,letterSpacing:.4,textTransform:"uppercase"}}>★ Quality promoter</span>;
}
function Reasons({ trade, passes, caution, avoid }: { trade?:string|null; passes?:string|null; caution?:string|null; avoid?:string|null }) {
  const rows: [string,string,string,string][] = [];
  (trade||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["PASS",C.green,C.greenBg,t]));
  (passes||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["✓",C.green,C.greenBg,t]));
  (caution||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["CHECK","#c2830c","#fdf6e6",t]));
  (avoid||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["JUNK",C.red,C.redBg,t]));
  if(!rows.length) return null;
  return <div style={{marginTop:9}}>{rows.map(([lab,col,bg,txt],i)=>(
    <div key={i} style={{display:"flex",gap:8,alignItems:"flex-start",fontSize:13,margin:"4px 0",lineHeight:1.45}}>
      <span style={{flexShrink:0,fontSize:10,fontWeight:800,padding:"1px 6px",borderRadius:4,marginTop:2,color:col,background:bg}}>{lab}</span>
      <span style={{color:C.sub}}>{txt}</span></div>))}</div>;
}
function ScoreRing({ score, conf, verdict }: { score?: number|null; conf?: number|null; verdict?: string|null }) {
  if (score == null) {
    const vcol = verdict==="TRADE"?C.green:verdict==="WATCH"?C.blue:verdict==="CAUTION"?"#c2830c":verdict==="AVOID"?C.red:C.dim;
    return <div style={{width:56,textAlign:"center"}}>
      <div style={{width:52,height:52,borderRadius:"50%",border:`3px dashed ${verdict?vcol:C.border}`,display:"grid",placeItems:"center",fontSize:verdict?9:10,fontWeight:700,color:verdict?vcol:C.dim,margin:"0 auto",lineHeight:1,padding:2}}>{verdict||"n/a"}</div>
      <div style={{fontSize:8.5,color:C.dim,marginTop:2,textTransform:"uppercase",letterSpacing:.5}}>{verdict?"pre-listing":"data thin"}</div></div>;
  }
  const col = score>=65?C.green:score>=40?"#c2830c":C.red;
  const r=22, c=2*Math.PI*r, off=c*(1-score/100);
  return <div style={{width:56,textAlign:"center"}}>
    <div style={{position:"relative",width:52,height:52,margin:"0 auto"}}>
      <svg width="52" height="52" style={{transform:"rotate(-90deg)"}}>
        <circle cx="26" cy="26" r={r} fill="none" stroke={C.grayBg} strokeWidth="4"/>
        <circle cx="26" cy="26" r={r} fill="none" stroke={col} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={off}/></svg>
      <span style={{position:"absolute",inset:0,display:"grid",placeItems:"center",fontSize:16,fontWeight:800,color:col}}>{score}</span>
    </div>
    <div style={{fontSize:8.5,color:C.dim,marginTop:1,textTransform:"uppercase",letterSpacing:.4}}>{conf!=null?`${conf}% conf`:"score"}</div></div>;
}
function StreetConsensus({ consensus, brokers, verdict }: { consensus?:string|null; brokers?:number|null; verdict?:string|null }) {
  if (!consensus) return null;
  // historical honesty: STRONG APPLY underperformed APPLY at open (crowd conviction isn't edge)
  const cLabel = String(consensus);
  const bn = brokers ?? 0;
  const cColor = cLabel.includes("STRONG") ? "#8a6d0b" : cLabel==="APPLY" ? C.green : cLabel==="AVOID" ? C.red : C.dim;
  // do we diverge? (we say caution/avoid while street says apply)
  const weCautious = verdict==="AVOID" || verdict==="CAUTION";
  const streetBullish = cLabel.includes("APPLY");
  const diverge = weCautious && streetBullish;
  return <div style={{marginTop:9,padding:"9px 12px",borderRadius:9,background:"#faf9f6",border:`1px solid ${C.border}`}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,flexWrap:"wrap"}}>
      <div style={{fontSize:12.5}}>
        <span style={{color:C.dim,fontWeight:600}}>Street:</span>{" "}
        <span style={{color:cColor,fontWeight:800}}>{cLabel}</span>
        {bn>0 && <span style={{color:C.dim}}> · {bn} broker{bn>1?"s":""}</span>}
      </div>
      <div style={{fontSize:12.5}}>
        <span style={{color:C.dim,fontWeight:600}}>AACapital:</span>{" "}
        <span style={{color:verdict==="TRADE"?C.green:verdict==="AVOID"?C.red:C.gold,fontWeight:800}}>{verdict||"—"}</span>
      </div>
    </div>
    {diverge && <div style={{marginTop:6,fontSize:11.5,color:C.sub,borderTop:`1px solid ${C.border}`,paddingTop:6}}>
      Street's call is about applying at the IPO price — and those calls have listed well (STRONG APPLY averaged strong listing gains). But you're buying at open, where that gain is largely priced in. Our read weighs the gap and our flags for the open-buy entry, which is a different decision.
    </div>}
  </div>;
}
function Flags({ red, green, redCount, greenCount, verdict }: { red?:string|null; green?:string|null; redCount?:number|null; greenCount?:number|null; verdict?:string|null }) {
  const [open,setOpen] = useState(false);
  const rc = redCount ?? 0, gc = greenCount ?? 0;
  if (rc===0 && gc===0) return null;
  const reds = (red||"").split(" ; ").filter(Boolean);
  const greens = (green||"").split(" ; ").filter(Boolean);
  // risk framing — NOT a prediction; a position-sizing signal (principle-consistent)
  const riskLine = rc>=4 ? "Higher-risk trade — the market prices these flags into the open, so size smaller and honor your stop."
    : rc>=2 ? "Some risk flags — verify them and size accordingly if you trade the open."
    : rc===1 ? "One flag to note — not disqualifying, but worth a look before trading."
    : null;
  return <div style={{marginTop:9}}>
    <div onClick={()=>setOpen(!open)} style={{display:"inline-flex",gap:10,alignItems:"center",cursor:"pointer",userSelect:"none",fontSize:12.5,fontWeight:700}}>
      {rc>0 && <span style={{color:C.red}}>🚩 {rc} red flag{rc>1?"s":""}</span>}
      {gc>0 && <span style={{color:C.green}}>✓ {gc} pass{gc>1?"es":""}</span>}
      <span style={{color:C.dim,fontWeight:600,fontSize:11}}>{open?"▲ hide":"▼ details"}</span>
    </div>
    {riskLine && verdict!=="AVOID" && <div style={{marginTop:6,fontSize:12,color:rc>=4?C.red:"#c2830c",background:rc>=4?C.redBg:"#fdf6e6",border:`1px solid ${rc>=4?C.redBd:"#f0dfae"}`,borderRadius:8,padding:"7px 11px",display:"flex",gap:7}}>
      <span>⚠️</span><span>{riskLine}</span></div>}
    {open && <div style={{marginTop:7}}>
      {reds.map((t,i)=><div key={"r"+i} style={{display:"flex",gap:8,alignItems:"flex-start",fontSize:12.5,margin:"3px 0"}}>
        <span style={{color:C.red,flexShrink:0}}>🚩</span><span style={{color:C.sub}}>{t}</span></div>)}
      {greens.map((t,i)=><div key={"g"+i} style={{display:"flex",gap:8,alignItems:"flex-start",fontSize:12.5,margin:"3px 0"}}>
        <span style={{color:C.green,flexShrink:0}}>✓</span><span style={{color:C.sub}}>{t}</span></div>)}
    </div>}
  </div>;
}

function FairValueCard({ c }: { c: Record<string, unknown> }) {
  const fv = c.fair_value == null ? null : Number(c.fair_value);
  const mos = c.fair_mos == null ? null : Number(c.fair_mos);
  const verdict = c.fair_verdict as string | null;
  const price = Number(c.issue_price) || 0;
  if (fv == null || price <= 0) return null;
  const col = verdict === "undervalued" ? C.green : verdict === "rich" ? C.red : C.amber;
  const bg  = verdict === "undervalued" ? C.greenBg : verdict === "rich" ? C.redBg : C.amberBg;
  const bd  = verdict === "undervalued" ? C.greenBd : verdict === "rich" ? C.redBd : C.amberBd;
  return (
    <div style={{ marginTop:10, padding:"12px 14px", background:bg, border:`1px solid ${bd}`, borderRadius:11 }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <span style={{ fontSize:12, fontWeight:700, color:C.sub, textTransform:"uppercase", letterSpacing:.4 }}>Fair Value</span>
        <span style={{ fontSize:11.5, fontWeight:700, color:col, textTransform:"uppercase", letterSpacing:.5 }}>{verdict}</span>
      </div>
      <div style={{ display:"flex", alignItems:"baseline", gap:10, marginTop:7 }}>
        <span style={{ fontSize:12.5, color:C.meta }}>Issue ₹{price.toFixed(0)}</span>
        <span style={{ fontSize:15, color:C.dim }}>→</span>
        <span style={{ fontSize:20, fontWeight:800, color:col }}>₹{fv.toLocaleString()}</span>
        {mos != null && <span style={{ fontSize:13, fontWeight:700, color:col }}>{mos>=0?"+":""}{mos}% MoS</span>}
      </div>
      {c.fair_note && <div style={{ fontSize:10.5, color:C.dim, marginTop:6 }}>{String(c.fair_note)}</div>}
    </div>
  );
}

function WeakOpenFlag({ c }: { c: Record<string, unknown> }) {
  // Negative-listing pattern (backtested): OFS-heavy + rich P/E → often opens weak → dip-then-pop
  const ofsPct = c.ofs_pct == null ? null : Number(c.ofs_pct);
  const pe = c.ipo_pe == null ? null : Number(c.ipo_pe);
  const peerPE = c.peer_median_pe == null ? null : Number(c.peer_median_pe);
  const listed = c.listing_gap_pct != null; // only flag pre-listing
  if (listed || ofsPct == null || ofsPct < 50) return null;
  const rich = pe != null && peerPE != null && peerPE > 0 && pe > peerPE * 1.1;
  if (!rich) return null;
  return (
    <div style={{ marginTop:8, padding:"9px 12px", background:C.amberBg, border:`1px solid ${C.amberBd}`, borderRadius:10, fontSize:12, color:C.amber }}>
      ⚠ <b>May open weak</b> — OFS-heavy ({ofsPct.toFixed(0)}%) + rich vs peers. Often dips then pops (buy-the-bounce setup, not a panic).
    </div>
  );
}

function TrustReport({ gate, oneLine, mos, full, confidence, company }:
  { gate?:string|null; oneLine?:string|null; mos?:string|null; full?:any; confidence?:string|null; company?:string }) {
  const [open,setOpen] = useState(false);
  if (!gate && !oneLine) return null;
  const gc: Record<string,[string,string,string]> = {
    clean:["#0e7a4d","#e7f7ef","#bfe6d2"], watch:["#b7791f","#fdf6e6","#efdcae"],
    reject:["#c0392b","#fdeceb","#f5cdc8"] };
  const [col,bg,bd] = gc[(gate||"watch").toLowerCase()] || gc.watch;
  const fj = (typeof full==="string") ? (()=>{try{return JSON.parse(full)}catch{return null}})() : full;
  const db = fj?.db_fields || {};
  // build a compact flag row from db_fields (only the concerning ones)
  const flags: string[] = [];
  if (db.auditor_qualified===true) flags.push("⚠ auditor qualified");
  if (db.sebi_action===true) flags.push("⚠ SEBI action");
  if (db.criminal_litigation===true) flags.push("⚠ criminal case");
  if (db.customer_concentration_high===true) flags.push("● customer concentration");
  if (db.ofs_heavy===true) flags.push("● OFS-heavy exit");
  if (db.promoter_pledge_flag===true) flags.push("⚠ promoter pledge");
  if (db.numbers_integrity_flag==="watch") flags.push("● numbers: watch");
  if (db.cash_conversion_flag==="weak") flags.push("⚠ weak cash conversion");
  if (db.debt_trend==="rising") flags.push("● debt rising");
  if (db.working_capital_flag==="watch") flags.push("● working capital");
  if (db.contingent_liabilities_material===true) flags.push("● contingent liab.");
  const clean = flags.length===0;
  return (
    <div style={{marginTop:11,border:`1px solid ${bd}`,borderRadius:11,overflow:"hidden"}}>
      <div style={{display:"flex",alignItems:"center",gap:9,padding:"9px 13px",background:bg,cursor:"pointer"}}
           onClick={()=>setOpen(!open)}>
        <span style={{fontSize:10,fontWeight:800,letterSpacing:.5,textTransform:"uppercase",
          color:col,border:`1px solid ${bd}`,borderRadius:5,padding:"2px 7px",background:"#fff"}}>
          🔍 RHP Trust · {(gate||"watch").toUpperCase()}</span>
        {mos && <span style={{fontSize:11,color:col,fontWeight:600}}>margin of safety: {mos}</span>}
        {confidence && <span style={{fontSize:10.5,color:"#888"}}>· confidence {confidence}</span>}
        <span style={{marginLeft:"auto",fontSize:11,color:col}}>{open?"▲ hide":"▼ details"}</span>
      </div>
      {oneLine && <div style={{padding:"9px 13px",fontSize:12.5,color:"#3a4152",lineHeight:1.5,borderTop:`1px solid ${bd}`}}>{oneLine}</div>}
      {!clean && <div style={{padding:"0 13px 9px",display:"flex",gap:6,flexWrap:"wrap"}}>
        {flags.map((f,i)=><span key={i} style={{fontSize:11,color:col,background:bg,border:`1px solid ${bd}`,borderRadius:5,padding:"2px 7px"}}>{f}</span>)}
      </div>}
      {clean && oneLine && <div style={{padding:"0 13px 9px",fontSize:11.5,color:"#0e7a4d"}}>✓ No governance red flags in the RHP</div>}
      {open && fj && <div style={{padding:"11px 13px",borderTop:`1px solid ${bd}`,fontSize:12,color:"#3a4152",lineHeight:1.55}}>
        {fj.trust_summary && <p style={{marginBottom:9}}>{fj.trust_summary}</p>}
        {Array.isArray(fj.top_3_material_risks) && fj.top_3_material_risks.length>0 && <>
          <div style={{fontWeight:700,fontSize:11,textTransform:"uppercase",letterSpacing:.4,color:"#666",margin:"8px 0 5px"}}>Top material risks</div>
          {fj.top_3_material_risks.map((r:string,i:number)=><div key={i} style={{display:"flex",gap:7,marginBottom:4}}><span style={{color:col}}>{i+1}.</span><span>{r}</span></div>)}
        </>}
        {fj.aacapital_decision?.dd_note && <>
          <div style={{fontWeight:700,fontSize:11,textTransform:"uppercase",letterSpacing:.4,color:"#666",margin:"9px 0 4px"}}>Due-diligence to verify</div>
          <div style={{fontSize:11.5,color:"#555"}}>{fj.aacapital_decision.dd_note}</div></>}
        <div style={{marginTop:9,fontSize:10.5,color:"#999"}}>Source: Red Herring Prospectus · extracted by Claude Sonnet · research signal, not a buy call</div>
      </div>}
    </div>
  );
}

const card: React.CSSProperties = { background:"linear-gradient(180deg,#FBFCFD,#F4F6FA)", border:`1px solid ${C.border}`,
  borderRadius:16, padding:"16px 18px", marginBottom:14,
  boxShadow:"0 1px 0 rgba(255,255,255,.9) inset, 0 12px 32px -10px rgba(28,36,58,.28), 0 3px 10px -3px rgba(28,36,58,.16)" };
const th: React.CSSProperties = { textAlign:"left", fontSize:10.5, color:C.meta,
  textTransform:"uppercase", letterSpacing:.5, padding:"7px 8px", borderBottom:`1px solid ${C.border}` };
const td: React.CSSProperties = { fontSize:13, color:C.sub, padding:"7px 8px",
  borderBottom:`1px solid ${C.border}` };
const num: React.CSSProperties = { fontFamily:MONO, fontVariantNumeric:"tabular-nums" };

function Spark({ ticks, floor, ceil }: { ticks: R[]; floor: number|null; ceil: number|null }) {
  const px = ticks.map(t => N(t.ltp)).filter((x): x is number => x != null);
  const vw = ticks.map(t => N(t.vwap)).filter((x): x is number => x != null);
  if (px.length < 2) return <div style={{fontSize:12,color:C.dim,padding:"18px 0"}}>Collecting ticks…</div>;
  const q = (a:number[], p:number) => { const s=[...a].sort((x,y)=>x-y);
    return s[Math.min(s.length-1, Math.max(0, Math.round(p*(s.length-1))))]; };
  const cand = [q(px,0.02), q(px,0.98), ...(vw.length?[q(vw,0.02),q(vw,0.98)]:[]),
    ...(floor!=null?[floor]:[]), ...(ceil!=null?[ceil]:[])];
  let lo = Math.min(...cand), hi = Math.max(...cand);
  const pad = (hi-lo || 1) * 0.06; lo -= pad; hi += pad; const sp = hi - lo || 1;
  const W = 640, H = 150,
    y = (v:number) => 12 + (1 - (Math.min(hi, Math.max(lo, v)) - lo)/sp) * (H-24);
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

function Calculator() {
  const [cap, setCap] = useState("10000");
  const [prices, setPrices] = useState("110, 115, 120");
  const [buyPx, setBuyPx] = useState("");
  const [sellPx, setSellPx] = useState("");
  const [shares, setShares] = useState("");
  const [ladderPx, setLadderPx] = useState("100");
  const [ladderStep, setLadderStep] = useState("2");
  const [ladderSh, setLadderSh] = useState("");
  const lp = Number(ladderPx)||0, step = Number(ladderStep)||0, lsh = Number(ladderSh)||0;
  const capN = Number(cap)||0;
  const priceList = prices.split(",").map(s=>Number(s.trim())).filter(x=>x>0);
  const inp: React.CSSProperties = {padding:"10px 12px",borderRadius:9,border:`1px solid ${C.border}`,
    fontSize:15,width:"100%",fontFamily:MONO,color:C.text,background:"#fff"};
  const lbl: React.CSSProperties = {fontSize:12,fontWeight:700,color:C.meta,marginBottom:5,display:"block"};
  const bp=Number(buyPx)||0, sp=Number(sellPx)||0, sh=Number(shares)||0;
  const pct = bp>0&&sp>0 ? ((sp-bp)/bp)*100 : null;
  const pnl = pct!=null&&sh>0 ? (sp-bp)*sh : null;
  return <>
    <div style={{...card,borderTop:`3px solid ${C.blue}`}}>
      <b style={{fontSize:16}}>🧮 Share sizer — how many shares for your capital</b>
      <div style={{fontSize:12.5,color:C.meta,marginTop:2,marginBottom:14}}>
        On listing day (9:45–10:15) the price moves as discovery happens. Enter your capital and the prices NSE is showing — see how many shares you can buy at each.</div>
      <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:16}}>
        <div style={{flex:1,minWidth:160}}><label style={lbl}>Your capital (₹)</label>
          <input style={inp} value={cap} onChange={e=>setCap(e.target.value)} inputMode="numeric"/></div>
        <div style={{flex:2,minWidth:220}}><label style={lbl}>Likely listing prices (comma-separated)</label>
          <input style={inp} value={prices} onChange={e=>setPrices(e.target.value)}/></div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:10}}>
        {priceList.map((p,i)=>{
          const n=Math.floor(capN/p), left=capN-n*p;
          return <div key={i} style={{border:`1px solid ${C.border}`,borderRadius:11,padding:"14px 16px",background:C.bg}}>
            <div style={{fontSize:12,color:C.meta,fontWeight:700}}>at ₹{p}</div>
            <div style={{...num,fontSize:28,fontWeight:800,color:C.blue,margin:"4px 0"}}>{n}</div>
            <div style={{fontSize:12,color:C.meta}}>shares · ₹{left.toLocaleString()} left</div>
          </div>;})}
      </div>
    </div>

    <div style={{...card,borderTop:`3px solid ${C.green}`}}>
      <b style={{fontSize:16}}>📈 Return calculator — your gain or loss</b>
      <div style={{fontSize:12.5,color:C.meta,marginTop:2,marginBottom:14}}>Enter your buy price and the current/sell price. Optionally add shares for the ₹ amount.</div>
      <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:16}}>
        <div style={{flex:1,minWidth:130}}><label style={lbl}>Buy price (₹)</label>
          <input style={inp} value={buyPx} onChange={e=>setBuyPx(e.target.value)} inputMode="decimal" placeholder="111"/></div>
        <div style={{flex:1,minWidth:130}}><label style={lbl}>Current / sell (₹)</label>
          <input style={inp} value={sellPx} onChange={e=>setSellPx(e.target.value)} inputMode="decimal" placeholder="125"/></div>
        <div style={{flex:1,minWidth:130}}><label style={lbl}>Shares (optional)</label>
          <input style={inp} value={shares} onChange={e=>setShares(e.target.value)} inputMode="numeric" placeholder="90"/></div>
      </div>
      {pct!=null && <div style={{display:"flex",gap:20,alignItems:"baseline",padding:"16px 18px",borderRadius:11,
        background:pct>=0?C.greenBg:C.redBg,border:`1px solid ${pct>=0?C.greenBd:C.redBd}`}}>
        <div><div style={{fontSize:12,color:C.meta,fontWeight:700}}>Gross return</div>
          <div style={{...num,fontSize:32,fontWeight:800,color:pct>=0?C.green:C.red}}>{pct>=0?"+":""}{pct.toFixed(2)}%</div></div>
        {pnl!=null && <div><div style={{fontSize:12,color:C.meta,fontWeight:700}}>On {sh} shares</div>
          <div style={{...num,fontSize:32,fontWeight:800,color:pct>=0?C.green:C.red}}>{pnl>=0?"+":"−"}₹{Math.abs(pnl).toLocaleString(undefined,{maximumFractionDigits:0})}</div></div>}
      </div>}
    </div>

    <div style={{...card,borderTop:`3px solid ${C.blue}`}}>
      <b style={{fontSize:16}}>🪜 Target ladder — price at each % gain</b>
      <div style={{fontSize:12.5,color:C.meta,marginTop:2,marginBottom:14}}>
        Enter your buy price and a step %. See the price at each gain level — set your targets fast.</div>
      <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:16}}>
        <div style={{flex:1,minWidth:130}}><label style={lbl}>Buy price (₹)</label>
          <input style={inp} value={ladderPx} onChange={e=>setLadderPx(e.target.value)} inputMode="decimal" placeholder="100"/></div>
        <div style={{flex:1,minWidth:130}}><label style={lbl}>Step %</label>
          <input style={inp} value={ladderStep} onChange={e=>setLadderStep(e.target.value)} inputMode="decimal" placeholder="2"/></div>
        <div style={{flex:1,minWidth:130}}><label style={lbl}>Shares (optional)</label>
          <input style={inp} value={ladderSh} onChange={e=>setLadderSh(e.target.value)} inputMode="numeric" placeholder="90"/></div>
      </div>
      {lp>0&&step>0 && <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(130px,1fr))",gap:10}}>
        {Array.from({length:12},(_,i)=>{
          const g=step*(i+1);
          const price=lp*(1+g/100);
          const gain=lsh>0?(price-lp)*lsh:null;
          return <div key={i} style={{border:`1px solid ${C.greenBd}`,borderRadius:11,padding:"12px 14px",background:C.greenBg}}>
            <div style={{fontSize:12,color:C.green,fontWeight:800}}>+{g.toFixed(g%1?1:0)}%</div>
            <div style={{...num,fontSize:22,fontWeight:800,color:C.text,margin:"3px 0"}}>₹{price.toFixed(2)}</div>
            {gain!=null && <div style={{fontSize:11.5,color:C.meta}}>+₹{gain.toLocaleString(undefined,{maximumFractionDigits:0})}</div>}
          </div>;})}
      </div>}
    </div>
  </>;
}

function IpoCommand() {
  const [d, setD] = useState<{cards:R[];live:R[];levels:R[];blocks:R[];post:R[];brlm:R[];dl:R[];track?:R[];leaderboard?:R[]}|null>(null);
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
  const pills: [string,string][] = [["command","⚡ Command Center"],["calc","🧮 Calculator"],["pb","🎯 Quick Profit Playbook"],
    ["open","📋 Open Now"],["upcoming","📅 Upcoming"],["post","📈 Post-Listing"],["brlm","🏆 BRLM"]];

  return (
    <div style={{padding:"16px 20px",background:"transparent",minHeight:"100vh",maxWidth:1500,margin:"auto",
      font:'14px/1.45 -apple-system,"Segoe UI",Inter,Roboto,sans-serif',color:C.text,
      alignItems:"start"}} className="ipo-shell">
      <style>{`
        .ipo-shell{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px}
        @media (max-width:900px){.ipo-shell{grid-template-columns:1fr}.ipo-shell aside{order:-1}}
      `}</style>
      <div style={{minWidth:0}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",flexWrap:"wrap",gap:10}}>
        <div><h1 style={{fontSize:20,fontWeight:800,margin:0}}>⚡ IPO Command Center</h1>
          <div style={{fontSize:12,color:C.meta}}>Nightly pipeline · Chittorgarh + SBI + NSE + Kite ·
            {d ? ` refreshed ${new Date().toLocaleTimeString()}` : " loading…"}</div></div>
        <ThemeToggle/>
      </div>

      {/* engine strip — plain-English grades, rigor one line below */}
      <div style={{...card,marginTop:12}}>
        <div style={{display:"flex",gap:22,alignItems:"center",flexWrap:"wrap"}}>
          <div style={{maxWidth:300}}>
            <div style={{fontWeight:800,fontSize:14}}>Every IPO gets a grade before it lists</div>
            <div style={{fontSize:12,color:C.meta}}>based on how 370 IPOs behaved over the last 15 years</div>
          </div>
          {[["STRONG grade","9 of 10 worked","typical gain +9.4%",C.green],
            ["FAVORABLE","7.6 of 10 worked","typical +8.7%",C.blue],
            ["average IPO","7.2 of 10 worked","typical +5.9%",C.text],
            ["AVOID grade","a coin flip","typical +0.8% — skip these",C.red]].map((s,i)=>(
            <div key={i} title="worked = made money buying at the listing open and selling at the best close within 10 trading days">
              <div style={{fontSize:10.5,color:C.meta,textTransform:"uppercase",letterSpacing:.4}}>{s[0]}</div>
              <div style={{fontSize:17,fontWeight:800,color:s[3] as string}}>{s[1]}</div>
              <div style={{fontSize:12,color:C.meta}}>{s[2]}</div></div>))}
        </div>
        <div style={{fontSize:11.5,color:C.dim,marginTop:8}}>
          “Worked” = best close within 10 sessions beat the open (a CEILING, not an executable exit — see Playbook for real exit rules: MID sell-D1-close = 65%/+3.3).
          Grades: STRONG 89.5% (n=38) · FAVORABLE 76.0% (n=96) · baseline 72% (n=370) · AVOID 51.2% (n=84) · validated 2026-07-05.
        </div>
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
                {meta.sbi_rating ? (
                  <div style={{fontSize:12,marginTop:4,padding:"4px 8px",background:C.blueBg,border:`1px solid ${C.blueBd}`,borderRadius:6,color:C.text}}>
                    <b>SBI:</b> <span style={{fontWeight:700,color:String(meta.sbi_rating).toLowerCase().includes("subscribe")?C.green:C.meta}}>{String(meta.sbi_rating)}</span>
                    {meta.sbi_peer ? <span style={{color:C.meta}}> · peer {String(meta.sbi_peer)}{meta.sbi_peer_ps?` ${meta.sbi_peer_ps}x`:""}</span> : null}
                    {meta.sbi_highlight ? <div style={{color:C.meta,marginTop:2,fontSize:11.5,lineHeight:1.35}}>{String(meta.sbi_highlight).slice(0,180)}</div> : null}
                  </div>
                ) : (
                  <div style={{fontSize:11,marginTop:4,color:C.meta,fontStyle:"italic"}}>SBI note: not in system</div>
                )}
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
                  {(()=>{const L=(d?.dl||[]).find(x=>x.sym===sym);
                    return <Spark ticks={ticks} floor={N(L?.floor) ?? N(lv.floor_price)} ceil={N(L?.ceiling) ?? N(lv.ceiling_price)}/>;})()}
                  <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8,marginTop:8}}>
                    {[["OBIR",N(last.obir)==null?"—":N(last.obir)!.toFixed(2),N(last.obir)!=null&&N(last.obir)!>=1?C.green:C.red],
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
                      <span style={{...num,fontSize:10.5,color:C.dim,minWidth:42}}>{new Date(String(b.at)).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false,hour:"2-digit",minute:"2-digit"})}</span>
                      <span><b>{Number(b.qty).toLocaleString()} @ ₹{String(b.price)}</b> — {String(b.mult)}× median</span></div>))}
                  <div style={{fontSize:12,color:C.meta,marginTop:8}}>
                    {String(lv.risk_note||"")} {lv.circuit_locked?" · ⚠ circuit locked":""}</div>
                </div>
              </div>
            </div>);
        })}
        {cards.filter(c=>c.state!=="INWINDOW"||liveSyms.includes(String(c.sym))===false).map((c,i)=>{
          if (liveSyms.includes(String(c.sym))) return null;
          let subs: [string,number][] = [];
          try { const o=JSON.parse(String(c.sub_scores||"{}")); subs=Object.entries(o) as [string,number][]; } catch {}
          return (
          <div key={i} style={c.verdict==="TRADE"?{...card,borderLeft:`4px solid ${C.green}`,background:"#fbfffc"}:card}>
            <div style={{display:"flex",gap:14,alignItems:"flex-start"}}>
              <ScoreRing score={(c.vscore ?? c.ipo_score) as number} conf={c.vconf as number} verdict={c.verdict as string}/>
              <div style={{flex:1,minWidth:0}}>
                <div style={{display:"flex",gap:9,alignItems:"center",flexWrap:"wrap",marginBottom:3}}>
                  {c.verdict!=null&&<Verdict v={c.verdict as string}/>}
                  {c.quality_promoter===true&&<QTag/>}
                  <State s={c.state as string}/>
                  {c.regime!=null&&<span style={{fontSize:11.5,fontWeight:700,color:c.regime==="bull"?C.green:C.red}}>{c.regime==="bull"?"▲ bull":"▼ bear"}</span>}
                </div>
                <b style={{fontSize:17}}>{String(c.company_name||"")}</b>
                {subs.length>0&&<div style={{marginTop:4,fontSize:11.5,color:C.meta,display:"flex",gap:12,flexWrap:"wrap"}}>
                  {subs.map(([k,v])=><span key={k}>{k} <b style={{color:v>=65?C.green:v>=40?"#c2830c":C.red}}>{v}</b></span>)}
                </div>}
              </div>
              <span style={{...num,fontSize:12,color:C.meta,textAlign:"right",flexShrink:0}}>
                {c.issue_price!=null?`₹${c.issue_price}`:""}<br/>{c.issue_size_cr!=null?`₹${Number(c.issue_size_cr).toLocaleString()}Cr`:""}
                {c.listing_date?<><br/>lists {D(c.listing_date)}</>:""}</span>
            </div>
            {c.ai_summary!=null&&<div style={{display:"flex",gap:8,marginTop:11,fontSize:13,color:C.sub,lineHeight:1.5,
              background:C.bg,border:`1px solid ${C.border}`,borderRadius:9,padding:"9px 12px"}}>
              <span>🤖</span><span>{String(c.ai_summary)}</span></div>}
            {c.final_qib!=null&&<div style={{display:"flex",gap:12,alignItems:"center",marginTop:9,flexWrap:"wrap"}}>
              <span style={{fontSize:12,color:C.meta,minWidth:30}}>QIB</span>
              <div style={{height:7,borderRadius:4,background:C.grayBg,flex:1,minWidth:120,position:"relative",overflow:"hidden"}}>
                <div style={{position:"absolute",inset:0,width:`${Math.min(100,Number(c.final_qib))}%`,background:C.green,borderRadius:4}}/></div>
              <span style={{...num,fontWeight:700,color:C.green}}>{Number(c.final_qib).toFixed(1)}×</span>
              {c.final_total!=null&&<span style={{...num,fontSize:12,color:C.meta}}>Total {Number(c.final_total).toFixed(1)}×</span>}</div>}
            <Reasons trade={c.why_trade as string} passes={c.why_passes as string} caution={c.why_caution as string} avoid={c.why_avoid as string}/>
            <StreetConsensus consensus={c.street_consensus as string} brokers={c.street_brokers as number} verdict={c.verdict as string}/>
            <Flags red={c.red_flags as string} green={c.green_checks as string} redCount={c.red_count as number} greenCount={c.green_count as number} verdict={c.verdict as string}/>
            <TrustReport gate={c.rhp_gate as string} oneLine={c.rhp_one_line as string} mos={c.rhp_mos as string} full={c.rhp_full} confidence={c.rhp_confidence as string} company={String(c.company_name||"")}/>
            <FairValueCard c={c}/>
            <WeakOpenFlag c={c}/>
            {c.verdict==="TRADE"&&<div style={{marginTop:10,paddingTop:9,borderTop:`1px dashed ${C.border}`,fontSize:12,color:C.meta,display:"flex",gap:15,flexWrap:"wrap"}}>
              <span>▸ <b style={{color:C.text}}>Entry</b> buy at open</span>
              <span>▸ <b style={{color:C.text}}>Exit</b> trailing −5%</span>
              <span>▸ <b style={{color:C.text}}>Order</b> ICICI GTT-OCO</span></div>}
            {c.verdict==="WATCH"&&<div style={{marginTop:10,paddingTop:9,borderTop:`1px dashed ${C.border}`,fontSize:12,color:C.blue}}>
              👁 On listing day: check the gap against the Playbook — quality passes, the gap decides the trade.</div>}
          </div>);})}
      </>}

      {/* PLAYBOOK */}
      {view==="calc" && <Calculator/>}

      {view==="pb" && <>
        {d?.leaderboard && d.leaderboard.length>0 && (()=>{
          const street = d.leaderboard!.filter(r=>String(r.source).startsWith("Street"));
          const ours = d.leaderboard!.filter(r=>String(r.source).startsWith("AACapital"));
          const Panel = ({title, rows, measure}:{title:string;rows:R[];measure:string})=>(
            <div style={{...card, marginBottom:12}}>
              <div style={{fontWeight:800,fontSize:14,marginBottom:2}}>{title}</div>
              <div style={{fontSize:11.5,color:C.dim,marginBottom:10}}>scored on {measure}</div>
              {rows.map((r,i)=>{
                const avg = r.avg_outcome!=null?Number(r.avg_outcome):null;
                const hit = r.hit_rate!=null?Number(r.hit_rate):null;
                const n = Number(r.n||0);
                const label = String(r.source).replace(/^(Street|AACapital): /,"");
                return <div key={i} style={{display:"flex",alignItems:"center",gap:10,padding:"7px 0",borderTop:i?`1px solid ${C.border}`:"none"}}>
                  <div style={{flex:"0 0 130px",fontWeight:700,fontSize:13}}>{label}</div>
                  <div style={{flex:1,fontSize:13}}>
                    <span style={{color:avg!=null&&avg>0?C.green:C.red,fontWeight:800}}>{avg!=null?`${avg>0?"+":""}${avg}%`:"—"}</span>
                    <span style={{color:C.dim}}> avg · {hit!=null?`${hit}%`:"—"} positive</span>
                  </div>
                  <div style={{flex:"0 0 auto",fontSize:11.5,color:C.dim}}>n={n}{n<10?" ⚠":""}</div>
                </div>;
              })}
            </div>
          );
          return <div style={{marginBottom:14}}>
            <b style={{fontSize:16}}>📊 Track record — two different games</b>
            <p style={{fontSize:12.5,color:C.sub,margin:"4px 0 12px"}}>
              The street rates whether to <b>apply</b> at the IPO price (judged on listing gain). We rate whether to <b>buy at open</b> (judged on the 20-day return from open). Different entries, different measures — not a head-to-head.
            </p>
            {street.length>0 && <Panel title="Street consensus — the 'apply' call" rows={street} measure="listing gain (issue→listing)"/>}
            {ours.length>0 && <Panel title="AACapital verdict — the 'buy-open' call" rows={ours} measure="20-day return from listing open"/>}
            <p style={{fontSize:11,color:C.dim,marginTop:-2}}>Small samples (n&lt;10 ⚠) are directional only. Buy-open edges are modest by design — the pop is largely priced in at open.</p>
          </div>;
        })()}
        <div style={{...card, background:"#FFFBEB", border:"1.5px solid #FDE68A"}}>
          <b style={{fontSize:16}}>🏠 The House Rules — the whole strategy in 3 lines</b>
          <div style={{fontSize:11.5,color:C.meta,marginTop:2,marginBottom:10}}>
            Written so anyone in the family can follow it. Tested 2026-07-13 on 585 clean IPOs (2016+).
          </div>
          {[
            ["1","BUY giants that open positive — with 30+ anchors best",
             "Issue over ₹2,000 crore, opening at or above IPO price (best +15%+). Add 30 or more anchor investors and the win rate climbs to 85% with almost no downside. Buy at listing open."],
            ["2","SKIP small, pricey, euphoric, and rejects",
             "Under ₹500cr, band over ₹600, opened +50%+, or an RHP-reject: skip. The pop is priced in or the risk is real. Skipping IS the strategy."],
            ["3","Cheaper + fresh beats expensive + OFS",
             "Low price bands (under ₹300) and fresh-issue IPOs (not sell-heavy) win far more at open. Two iterations passed (2026-07-10, 2026-07-13)."],
          ].map(([n,t,d2])=>(
            <div key={n} style={{display:"flex",gap:12,padding:"10px 0",borderTop:n!=="1"?`1px solid ${C.border}`:"none"}}>
              <div style={{minWidth:34,height:34,borderRadius:"50%",background:"#B8860B",color:"#fff",
                display:"flex",alignItems:"center",justifyContent:"center",fontWeight:800,fontSize:16}}>{n}</div>
              <div><div style={{fontWeight:800,fontSize:13.5}}>{t}</div>
                <div style={{fontSize:12.5,color:C.sub,marginTop:2}}>{d2}</div></div>
            </div>))}
          <div style={{marginTop:10,padding:"9px 12px",background:"#F0FDF4",border:"1px solid #BBF7D0",
            borderRadius:9,fontSize:12.5,color:"#166534"}}>
            <b>The honest math (two iterations: 2026-07-10 &amp; 2026-07-13):</b> the core giant-opens-positive trade wins
            ~92 in 100; adding 30+ anchors on a mega issue reaches <b>85% with a near-zero downside floor</b>.
            Everything outside the rules — small, pricey, euphoric, or reject — is watch-only.
          </div>
        </div>

        <div style={card}>
          <b style={{fontSize:15}}>The two strategies — validated</b>
          <div style={{fontSize:11.5,color:C.meta,marginTop:2,marginBottom:12}}>
            Two layers: a <b>quality gate</b> (before listing) and a <b>tradeable signal</b> (buy-at-open).
            Tradeable signal tested <b>2026-07-13</b> on 585 clean IPOs (2016+); quality gate = RHP forensic read of 448 prospectuses.
          </div>
          {[
            ["Q","Quality gate (before listing)","#2E5A9E","#EAF0F9","#C2D4EC",
             "RHP forensic read of the prospectus → clean / watch / reject. A reject is a hard pass. This is the junk filter, not the entry — it tells you what NOT to touch.",
             "448 prospectuses read"],
            ["T","Tradeable signal (buy at open)","#16A34A","#F0FDF4","#BBF7D0",
             "Giant issue (>₹2000cr) opening positive, best at +15%+. The measured open-buy edge. Small issues (<500cr) and euphoric >50% pops are excluded.",
             "92% win · +20% median · n=25"],
          ].map(([tag,name,col,bg,bd,desc,stat])=>(
            <div key={tag} style={{display:"flex",gap:12,padding:"11px 0",borderTop:tag!=="S1"?`1px solid ${C.border}`:"none"}}>
              <div style={{minWidth:38,height:38,borderRadius:9,background:bg,border:`1px solid ${bd}`,color:col,
                display:"flex",alignItems:"center",justifyContent:"center",fontWeight:800,fontSize:13}}>{tag}</div>
              <div style={{flex:1}}>
                <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:6}}>
                  <span style={{fontWeight:800,fontSize:14}}>{name}</span>
                  <span style={{...num,fontSize:12.5,fontWeight:700,color:col}}>{stat}</span></div>
                <div style={{fontSize:12.5,color:C.sub,marginTop:3}}>{desc}</div></div>
            </div>))}
          <div style={{marginTop:10,padding:"9px 12px",background:C.grayBg,borderRadius:9,fontSize:12,color:C.meta}}>
            <b>Golden rule (tested):</b> euphoric opens &gt;50% and issues under ₹500cr = skip.
            The edge is the giant opening positive — not the pop. GMP is context only; QIB level and ROE showed no edge in the test.
          </div>
        </div>

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
              <div style={{display:"flex",gap:9,alignItems:"center",flexWrap:"wrap"}}>
                {c.verdict!=null&&<Verdict v={c.verdict as string}/>}
                <b>{String(c.company_name||"")}</b>
                {c.quality_promoter===true&&<QTag/>}
                <span style={{fontSize:12,color:C.meta}}>closes {D(c.close_date)}</span></div>
              <span style={{...num,fontSize:12,color:C.meta}}>₹{String(c.issue_price??"—")} · ₹{Number(c.issue_size_cr||0).toLocaleString()}Cr</span></div>
            {[["QIB",c.final_qib],["NII",c.final_nii],["Retail",c.final_retail]].map(([k,v],j)=>(
              v==null?null:
              <div key={j} style={{display:"flex",gap:12,alignItems:"center",marginTop:7}}>
                <span style={{fontSize:12,color:C.meta,minWidth:40}}>{k as string}</span>
                <div style={{height:7,borderRadius:4,background:C.grayBg,flex:1,position:"relative",overflow:"hidden"}}>
                  <div style={{position:"absolute",inset:0,width:`${Math.min(100,Number(v))}%`,background:C.green,borderRadius:4}}/></div>
                <span style={{...num,fontWeight:700}}>{Number(v).toFixed(1)}×</span></div>))}
            <Reasons trade={c.why_trade as string} caution={c.why_caution as string} avoid={c.why_avoid as string}/>
            <div style={{fontSize:12,color:C.dim,marginTop:8}}>Figures = last nightly sync · live intraday capture is the next data build. QIBs bid late — a low day-1 is normal.</div>
          </div>))}
        {cards.filter(c=>c.state==="OPEN").length===0&&<div style={card}><span style={{fontSize:13,color:C.meta}}>No IPO is open for bidding right now.</span></div>}
      </>}

      {/* UPCOMING */}
      {view==="upcoming" && <div style={{...card,overflowX:"auto"}}>
        <table style={{minWidth:560,width:"100%",borderCollapse:"collapse"}}>
          <thead><tr><th style={th}>Lists</th><th style={th}>Company</th><th style={th}>Size</th><th style={th}>Verdict</th><th style={th}>Why</th></tr></thead>
          <tbody>{cards.filter(c=>c.state==="UPCOMING"||c.state==="LISTING").map((c,i)=>(
            <tr key={i}><td style={{...td,...num}}>{D(c.listing_date)}</td>
              <td style={{...td,fontWeight:600,color:C.text}}>{String(c.company_name||"")}{c.quality_promoter===true?" ★":""}</td>
              <td style={{...td,...num}}>{c.issue_size_cr!=null?`₹${Number(c.issue_size_cr).toLocaleString()}cr`:"—"}</td>
              <td style={td}>{c.verdict!=null?<Verdict v={c.verdict as string}/>:<Chip b={c.score_band as string}/>}</td>
              <td style={{...td,fontSize:12,color:C.meta}}>{String(c.why_trade||c.why_caution||c.why_avoid||c.score_evidence||"—").split(" ; ")[0]}</td></tr>))}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Pre-listing scores use size/valuation only — the gap weight applies itself at the open.</div>
      </div>}

      {/* POST-LISTING AUDIT */}
      {view==="post" && <div style={{...card,overflowX:"auto"}}>
        <b style={{fontSize:14}}>Score vs reality — the standing audit</b>
        <table style={{minWidth:560,width:"100%",borderCollapse:"collapse",marginTop:8}}>
          <thead><tr><th style={th}>Listed</th><th style={th}>Company</th><th style={th}>Verdict</th>
            <th style={th}>Gap</th><th style={th}>Listing gap</th><th style={th}>10-session best</th></tr></thead>
          <tbody>{(d?.post||[]).map((r,i)=>(
            <tr key={i}><td style={{...td,...num}}>{D(r.listing_date)}</td>
              <td style={{...td,fontWeight:600,color:C.text}}>{String(r.company_name||"")}</td>
              <td style={td}>{r.verdict!=null?<Verdict v={r.verdict as string}/>:<Chip b={r.score_band as string}/>}</td>
              <td style={td}>{String(r.gap_bucket||"—")}</td>
              <td style={{...td,...num}}>{r.listing_gap_pct!=null?`${Number(r.listing_gap_pct).toFixed(1)}%`:"—"}</td>
              <td style={{...td,...num,fontWeight:700,color:N(r.d10_best_pct)==null?C.dim:(N(r.d10_best_pct)!>0?C.green:C.red)}}>
                {r.d10_best_pct!=null?`${Number(r.d10_best_pct).toFixed(1)}%`:"pending"}</td></tr>))}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Misses feed the quarterly re-weight. 10-session outcomes precompute nightly.</div>
      </div>}

      {/* BRLM */}
      {view==="brlm" && <div style={{...card,overflowX:"auto"}}>
        <b style={{fontSize:14}}>Book managers — empirical, from our own outcomes</b>
        <table style={{minWidth:560,width:"100%",borderCollapse:"collapse",marginTop:8}}>
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
      <MarketsSidebar />
    </div>
  );
}

export default function IpoRoute() {
  return (
    <AppShell current="ipo">
      <IpoCommand />
    </AppShell>
  );
}
