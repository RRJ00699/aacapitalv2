"use client";
import React from "react";
/* eslint-disable @typescript-eslint/no-unused-vars */
// app/dashboard/ipo2/page.tsx — the locked redesign, wired to /api/ipo-command.
// Self-contained: no imports from the 3 legacy shells. Polls every 20s while a
// live capture exists. Ships at /dashboard/ipo2 for side-by-side verification;
// cutover to /dashboard/ipo is a separate one-line commit after approval.
import { useEffect, useState, useCallback, useRef } from "react";
import { useThemeControls } from "@/lib/theme";
import AppShell from "@/components/app-shell/AppShell";
import MarketsSidebar from "@/components/ipo/MarketsSidebar";
import IpoCard from "@/components/ipo/IpoCard";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/primitives";
import CompleteDetails from "@/components/ipo/CompleteDetails";

class CardBoundary extends React.Component<{children: React.ReactNode}, {err: boolean}> {
  constructor(p: {children: React.ReactNode}) { super(p); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  render() { return this.state.err
    ? <div style={{border:"1px solid #FEDF89",background:"#FFFAEB",borderRadius:12,padding:14,
        fontSize:12,color:"#B54708",marginBottom:12}}>This card failed to render — the rest of the page is unaffected.</div>
    : this.props.children; }
}

const C = { bg:"var(--t-bg)", surface:"var(--t-surface)", surface2:"var(--t-surface2)", border:"var(--t-border)", line:"var(--t-line)", text:"var(--t-text)",
  sub:"var(--t-sub)", meta:"var(--t-meta)", dim:"var(--t-dim)",
  green:"var(--t-green)", greenBg:"var(--t-greenBg)", greenBd:"var(--t-greenBd)",
  blue:"var(--t-blue)", blueBg:"var(--t-blueBg)", blueBd:"var(--t-blueBd)",
  amber:"var(--t-amber)", amberBg:"var(--t-amberBg)", amberBd:"var(--t-amberBd)",
  red:"var(--t-red)", redBg:"var(--t-redBg)", redBd:"var(--t-redBd)", grayBg:"var(--t-grayBg)", gold:"var(--t-gold)" };
const MONO = "var(--f-mono)";

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
    TRADE:[C.green,C.greenBg,C.greenBd], CAUTION:[C.amber,C.amberBg,C.amberBd],
    WATCH:[C.blue,C.blueBg,C.blueBd], AVOID:[C.red,C.redBg,C.redBd] };
  const [c,bg,bd] = m[v || ""] || m.CAUTION;
  const icon = v==="TRADE"?"✓ ":v==="AVOID"?"✕ ":v==="WATCH"?"◆ ":"! ";
  return <span style={{color:c,background:bg,border:`1px solid ${bd}`,borderRadius:8,
    padding:"4px 11px",fontSize:11,fontWeight:800,letterSpacing:.4,textTransform:"uppercase"}}>
    {icon}{v || "CAUTION"}</span>;
}
function QTag() {
  return <span style={{color:C.gold,background:C.amberBg,border:`1px solid ${C.amberBd}`,
    borderRadius:5,padding:"2px 8px",fontSize:9.5,fontWeight:800,letterSpacing:.4,textTransform:"uppercase"}}>★ Quality promoter</span>;
}
function Reasons({ trade, passes, caution, avoid }: { trade?:string|null; passes?:string|null; caution?:string|null; avoid?:string|null }) {
  const rows: [string,string,string,string][] = [];
  (trade||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["PASS",C.green,C.greenBg,t]));
  (passes||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["✓",C.green,C.greenBg,t]));
  (caution||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["CHECK",C.amber,C.amberBg,t]));
  (avoid||"").split(" ; ").filter(Boolean).forEach(t=>rows.push(["JUNK",C.red,C.redBg,t]));
  if(!rows.length) return null;
  return <div style={{marginTop:9}}>{rows.map(([lab,col,bg,txt],i)=>(
    <div key={i} style={{display:"flex",gap:8,alignItems:"flex-start",fontSize:13,margin:"4px 0",lineHeight:1.45}}>
      <span style={{flexShrink:0,fontSize:10,fontWeight:800,padding:"1px 6px",borderRadius:4,marginTop:2,color:col,background:bg}}>{lab}</span>
      <span style={{color:C.sub}}>{txt}</span></div>))}</div>;
}
function ScoreRing({ score, conf, verdict }: { score?: number|null; conf?: number|null; verdict?: string|null }) {
  if (score == null) {
    const vcol = verdict==="TRADE"?C.green:verdict==="WATCH"?C.blue:verdict==="CAUTION"?C.amber:verdict==="AVOID"?C.red:C.dim;
    return <div style={{width:56,textAlign:"center"}}>
      <div style={{width:52,height:52,borderRadius:"50%",border:`3px dashed ${verdict?vcol:C.border}`,display:"grid",placeItems:"center",fontSize:verdict?9:10,fontWeight:700,color:verdict?vcol:C.dim,margin:"0 auto",lineHeight:1,padding:2}}>{verdict||"n/a"}</div>
      <div style={{fontSize:8.5,color:C.dim,marginTop:2,textTransform:"uppercase",letterSpacing:.5}}>{verdict?"pre-listing":"data thin"}</div></div>;
  }
  const col = score>=65?C.green:score>=40?C.amber:C.red;
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
  const cColor = cLabel.includes("STRONG") ? C.amber : cLabel==="APPLY" ? C.green : cLabel==="AVOID" ? C.red : C.dim;
  // do we diverge? (we say caution/avoid while street says apply)
  const weCautious = verdict==="AVOID" || verdict==="CAUTION";
  const streetBullish = cLabel.includes("APPLY");
  const diverge = weCautious && streetBullish;
  return <div style={{marginTop:9,padding:"9px 12px",borderRadius:9,background:C.surface2,border:`1px solid ${C.border}`}}>
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
      {rc>0 && <span style={{color:C.red}}>⚑ {rc} red flag{rc>1?"s":""}</span>}
      {gc>0 && <span style={{color:C.green}}>✓ {gc} pass{gc>1?"es":""}</span>}
      <span style={{color:C.dim,fontWeight:600,fontSize:11}}>{open?"▲ hide":"▼ details"}</span>
    </div>
    {riskLine && verdict!=="AVOID" && <div style={{marginTop:6,fontSize:12,color:rc>=4?C.red:C.amber,background:rc>=4?C.redBg:C.amberBg,border:`1px solid ${rc>=4?C.redBd:C.amberBd}`,borderRadius:8,padding:"7px 11px",display:"flex",gap:7}}>
      <span style={{fontWeight:800}}>!</span><span>{riskLine}</span></div>}
    {open && <div style={{marginTop:7}}>
      {reds.map((t,i)=><div key={"r"+i} style={{display:"flex",gap:8,alignItems:"flex-start",fontSize:12.5,margin:"3px 0"}}>
        <span style={{color:C.red,flexShrink:0}}>⚑</span><span style={{color:C.sub}}>{t}</span></div>)}
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
  if (fv == null) {
    // honest: show WHY there's no fair value instead of a silent blank
    const note = c.fair_note ? String(c.fair_note) : null;
    if (!note) return null;
    return (
      <div style={{ marginTop:10, padding:"8px 12px", background:C.grayBg, border:`1px solid ${C.border}`, borderRadius:10 }}>
        <span style={{ fontSize:11, fontWeight:700, color:C.meta, textTransform:"uppercase", letterSpacing:.4 }}>Fair Value</span>
        <span style={{ fontSize:12, color:C.dim, marginLeft:8 }}>unavailable — {note}</span>
      </div>
    );
  }
  if (price <= 0) return null;
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
      {c.fair_note ? <div style={{ fontSize:10.5, color:C.dim, marginTop:6 }}>{String(c.fair_note)}</div> : null}
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
    clean:[C.green,C.greenBg,C.greenBd], watch:[C.amber,C.amberBg,C.amberBd],
    reject:[C.red,C.redBg,C.redBd] };
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
          color:col,border:`1px solid ${bd}`,borderRadius:5,padding:"2px 7px",background:C.surface}}>
          RHP Trust · {(gate||"watch").toUpperCase()}</span>
        {mos && <span style={{fontSize:11,color:col,fontWeight:600}}>margin of safety: {mos}</span>}
        {confidence && <span style={{fontSize:10.5,color:C.meta}}>· confidence {confidence}</span>}
        <span style={{marginLeft:"auto",fontSize:11,color:col}}>{open?"▲ hide":"▼ details"}</span>
      </div>
      {oneLine && <div style={{padding:"9px 13px",fontSize:12.5,color:C.sub,lineHeight:1.5,borderTop:`1px solid ${bd}`}}>{oneLine}</div>}
      {!clean && <div style={{padding:"0 13px 9px",display:"flex",gap:6,flexWrap:"wrap"}}>
        {flags.map((f,i)=><span key={i} style={{fontSize:11,color:col,background:bg,border:`1px solid ${bd}`,borderRadius:5,padding:"2px 7px"}}>{f}</span>)}
      </div>}
      {clean && oneLine && <div style={{padding:"0 13px 9px",fontSize:11.5,color:C.green}}>✓ No governance red flags in the RHP</div>}
      {open && fj && <div style={{padding:"11px 13px",borderTop:`1px solid ${bd}`,fontSize:12,color:C.sub,lineHeight:1.55}}>
        {fj.trust_summary && <p style={{marginBottom:9}}>{fj.trust_summary}</p>}
        {Array.isArray(fj.top_3_material_risks) && fj.top_3_material_risks.length>0 && <>
          <div style={{fontWeight:700,fontSize:11,textTransform:"uppercase",letterSpacing:.4,color:C.meta,margin:"8px 0 5px"}}>Top material risks</div>
          {fj.top_3_material_risks.map((r:string,i:number)=><div key={i} style={{display:"flex",gap:7,marginBottom:4}}><span style={{color:col}}>{i+1}.</span><span>{r}</span></div>)}
        </>}
        {fj.aacapital_decision?.dd_note && <>
          <div style={{fontWeight:700,fontSize:11,textTransform:"uppercase",letterSpacing:.4,color:C.meta,margin:"9px 0 4px"}}>Due-diligence to verify</div>
          <div style={{fontSize:11.5,color:C.sub}}>{fj.aacapital_decision.dd_note}</div></>}
        <div style={{marginTop:9,fontSize:10.5,color:C.dim}}>Source: Red Herring Prospectus · extracted by Claude Sonnet · research signal, not a buy call</div>
      </div>}
    </div>
  );
}

function GmpLine({ c }: { c: Record<string, unknown> }) {
  const db = c.gmp_day_before == null ? null : Number(c.gmp_day_before);
  const hi = c.gmp_high == null ? null : Number(c.gmp_high);
  const lo = c.gmp_low == null ? null : Number(c.gmp_low);
  const band = c.gmp_band ? String(c.gmp_band) : null;
  const hint = c.gmp_hint ? String(c.gmp_hint) : null;
  if (db == null && hi == null && lo == null) return null;
  const col = band === "STRONG" || band === "GOOD" ? C.green : band === "NEGATIVE" ? C.red : C.amber;
  const bg  = band === "STRONG" || band === "GOOD" ? C.greenBg : band === "NEGATIVE" ? C.redBg : C.amberBg;
  const bd  = band === "STRONG" || band === "GOOD" ? C.greenBd : band === "NEGATIVE" ? C.redBd : C.amberBd;
  return (
    <div style={{ marginTop:9, padding:"8px 12px", background:bg, border:`1px solid ${bd}`, borderRadius:10,
      display:"flex", alignItems:"baseline", gap:10, flexWrap:"wrap" }}>
      <span style={{ fontSize:11, fontWeight:700, color:C.meta, textTransform:"uppercase", letterSpacing:.4 }}>GMP</span>
      {db != null && <span style={{ ...num, fontSize:16, fontWeight:800, color:col }}>{db > 0 ? "+" : ""}{db}% day-before</span>}
      {band && <span style={{ fontSize:10.5, fontWeight:800, color:col, letterSpacing:.4 }}>{band}</span>}
      {(lo != null || hi != null) && <span style={{ ...num, fontSize:11.5, color:C.meta }}>range {lo ?? "—"}% … {hi ?? "—"}%</span>}
      {hint && <span style={{ fontSize:11, color:C.meta }}>{hint}</span>}
    </div>
  );
}

function await2(txt: string) {
  return (
    <div style={{ fontSize: 12 }}>
      <b style={{ color: C.dim, fontWeight: 600 }}>awaiting</b>
      <span style={{ color: C.dim }}> · {txt}</span>
    </div>
  );
}

function VolumeConfirm({ sym }: { sym: string }) {
  // Wired to /api/ipo/cum-volume (#171). Polls only when the 10:29–11:00 IST
  // window is near/past; before that the tile keeps the honest awaiting text.
  const [v, setV] = useState<R | null>(null);
  useEffect(() => {
    if (!sym) return;
    const load = () => {
      const n = new Date(); const m = n.getUTCHours() * 60 + n.getUTCMinutes();
      if (m < 295) return;            // before ~10:25 IST — nothing to confirm yet
      fetch(`/api/ipo/cum-volume?symbol=${encodeURIComponent(sym)}`)
        .then(r => r.json()).then(x => { if (x && x.ok) setV(x); }).catch(() => {});
    };
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [sym]);
  // BUG E: a dead upstream (tick capture) must not masquerade as patience.
  if (!v) return await2("cumulative volume · confirms from 10:29 IST");
  if (v.upstream_stale === true || v.capture_down === true)
    return (<div style={{ fontSize: 12, color: "#B42318" }}>
      <b>upstream capture down</b><span style={{ color: C.dim }}> · last tick {String(v.last_tick ?? "unknown")} · not awaiting, broken</span></div>);
  if (v.status !== "confirmed" || v.cum_volume == null)
    return await2(String(v.note ?? "in window — accumulating ticks"));
  const cum = Number(v.cum_volume);
  const disp = cum >= 1e7 ? `${(cum / 1e7).toFixed(2)} Cr` : cum >= 1e5 ? `${(cum / 1e5).toFixed(1)} L` : cum.toLocaleString();
  return (
    <div style={{ fontSize: 12.5 }}>
      <b style={{ ...num, fontSize: 15 }}>{disp}</b> shares
      <span style={{ color: C.green, fontWeight: 700, marginLeft: 6 }}>✓ confirmed</span>
      <div style={{ fontSize: 10, color: C.meta, marginTop: 2 }}>10:29–11:00 window · {String(v.tick_count)} ticks</div>
    </div>
  );
}

function HoldStrip({ sym }: { sym: string }) {
  const [j, setJ] = useState<R | null>(null);
  const load = useCallback(() => {
    fetch(`/api/ipo/journey?sym=${sym}`).then(r => r.json())
      .then(x => { if (x && x.ok) setJ(x); })
      .catch(() => { /* strip is best-effort; the journey page is the fallback */ });
  }, [sym]);
  useEffect(() => {
    load();
    // Poll only during IST market hours (Mon–Fri 9:15–15:30 IST = 3:45–10:00 UTC),
    // same Neon-cost gate as /dashboard/journey.
    const inMkt = () => { const n = new Date(); const d = n.getUTCDay();
      if (d === 0 || d === 6) return false;
      const m = n.getUTCHours() * 60 + n.getUTCMinutes(); return m >= 225 && m <= 600; };
    const t = setInterval(() => { if (inMkt()) load(); }, 60000);
    return () => clearInterval(t);
  }, [load]);
  if (!j) return null;
  if (j.hasData === false) return (
    <div style={{ border: `1px dashed ${C.border}`, borderRadius: 10, padding: "14px 13px" }}>
      <div style={{ fontSize: 10.5, color: C.meta, textTransform: "uppercase", letterSpacing: .5, fontWeight: 700 }}>Exit engine</div>
      <div style={{ fontSize: 12, color: C.meta, marginTop: 6, lineHeight: 1.5 }}>
        {j.note ? String(j.note) : "Awaiting first candles — arms after the first close syncs (17:00 IST run)."}</div>
      <div style={{ ...num, fontSize: 10, color: C.dim, marginTop: 6 }}>lock8/trail12 · arm +8% · floor +3% · trail −12%</div>
    </div>
  );
  const exit = j.decision === "EXIT";
  const armed = j.armed === true;
  const col = exit ? C.red : armed ? C.green : C.amber;
  const bg  = exit ? C.redBg : armed ? C.greenBg : C.amberBg;
  const bd  = exit ? C.redBd : armed ? C.greenBd : C.amberBd;
  const gain = j.gainNow == null ? null : Number(j.gainNow);
  const lvl = (lab: string, v: unknown) => (
    <span style={{ fontSize: 11, color: C.meta }}>{lab} <b style={{ ...num, color: C.text }}>₹{String(v ?? "—")}</b></span>
  );
  return (
    <div style={{ marginTop: 10, border: `1px solid ${bd}`, borderRadius: 10, background: bg, padding: "9px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: .5, fontFamily: "var(--f-display)",
          color: exit ? "#fff" : col, border: `1px solid ${exit ? C.red : bd}`,
          background: exit ? C.red : C.surface, borderRadius: 6, padding: "3px 10px",
          transition: "all .25s var(--ease)" }}>
          {exit ? "EXIT NOW" : "HOLD"}</span>
        {j.live != null && <span style={{ ...num, fontSize: 19, fontWeight: 800, color: C.text }}>
          ₹{String(j.live)}</span>}
        {gain != null && <span style={{ ...num, fontSize: 17, fontWeight: 800, color: gain >= 0 ? C.green : C.red,
          transition: "color .3s var(--ease)" }}>
          {gain >= 0 ? "+" : ""}{gain}%</span>}
        <span style={{ fontSize: 11, fontWeight: 700, color: armed ? C.green : C.meta }}>
          {armed ? "floor armed" : "arms at +8%"}</span>
        <span style={{ marginLeft: "auto", fontSize: 10, color: C.dim }}>
          lock8/trail12 · {j.liveSource === "close" ? "close" : <><span className="livedot" style={{width:5,height:5,marginRight:3,verticalAlign:"middle"}}/>live</>} · day {String(j.daysHeld ?? "—")}</span>
      </div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 6 }}>
        {lvl("entry", j.entry)}{lvl("floor", j.floorLevel)}{lvl("trail", j.trailLevel)}{lvl("peak", j.peak)}
        {j.offPeak != null && <span style={{ ...num, fontSize: 11, color: C.meta }}>{Number(j.offPeak).toFixed(1)}% off peak</span>}
      </div>
      {j.reason ? <div style={{ fontSize: 11.5, color: C.sub, marginTop: 6, lineHeight: 1.45 }}>{String(j.reason)}</div> : null}
      {(() => {
        // Listing-day: the exit engine's chart, auto-expanded — no tap to see the story.
        const ser = (j.series as Array<{date: string; close: number; high: number; low: number}> | undefined) || [];
        if (ser.length < 2) return null;
        const entry = Number(j.entry), peak = Number(j.peak), lo = Number(j.low);
        const fl = Number(j.floorLevel), tr = Number(j.trailLevel);
        const prices = ser.flatMap(p => [p.high, p.low]).concat([entry, peak, lo, fl, tr].filter(v => !isNaN(v)));
        const mn = Math.min(...prices), mx = Math.max(...prices), rng = mx - mn || 1;
        const W = 340, H = 96, pad = 6;
        const X = (i: number) => pad + (i / Math.max(1, ser.length - 1)) * (W - 2 * pad);
        const Y = (v: number) => H - pad - ((v - mn) / rng) * (H - 2 * pad);
        const line = ser.map((p, i) => `${i === 0 ? "M" : "L"}${X(i).toFixed(1)},${Y(p.close).toFixed(1)}`).join(" ");
        return (
          <div style={{ marginTop: 9 }}>
            <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
              {!isNaN(fl) && <line x1={pad} y1={Y(fl)} x2={W - pad} y2={Y(fl)} stroke={C.gold} strokeWidth="1" strokeDasharray="3,3" opacity="0.65" />}
              {!isNaN(tr) && <line x1={pad} y1={Y(tr)} x2={W - pad} y2={Y(tr)} stroke={C.red} strokeWidth="1" strokeDasharray="3,3" opacity="0.5" />}
              <path d={line} fill="none" stroke={exit ? C.red : C.green} strokeWidth="2"
                style={{ transition: "stroke .3s var(--ease)" }} />
              {!isNaN(entry) && <circle cx={X(0)} cy={Y(entry)} r="3.5" fill={C.green} />}
              <circle cx={X(ser.length - 1)} cy={Y(ser[ser.length - 1].close)} r="4.5"
                fill={C.surface} stroke={exit ? C.red : C.green} strokeWidth="2" />
            </svg>
            <div style={{ ...num, display: "flex", justifyContent: "space-between", fontSize: 9.5, color: C.meta, marginTop: 2 }}>
              <span>entry ₹{String(j.entry ?? "—")}</span>
              <span style={{ color: C.gold }}>· · floor</span>
              <span style={{ color: C.red }}>· · trail</span>
              <span>peak ₹{String(j.peak ?? "—")}</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

type LiveRule = { name: string; passed: boolean | null; win: number | null; detail?: string };
function RuleCard({ title, when, rules }: { title: string; when: string; rules: LiveRule[] | null }) {
  const ghost: LiveRule[] = Array.from({ length: 4 }, () => ({ name: "", passed: null, win: null }));
  const rows = rules ?? ghost;
  return (
    <div style={{ flex: "1 1 240px", minWidth: 230, border: rules ? `1px solid ${C.border}` : `1px dashed ${C.border}`,
      borderRadius: 11, padding: "10px 12px", background: rules ? C.bg : "transparent" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 9.5, color: C.meta, letterSpacing: .4, textTransform: "uppercase", fontWeight: 700 }}>{title}</span>
        <span style={{ fontSize: 9.5, color: C.dim }}>{when}</span>
      </div>
      <div style={{ marginTop: 7 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0",
            borderTop: i ? `1px solid ${C.line}` : "none" }}>
            {r.passed == null
              ? <span className={rules ? undefined : "shimmer"} style={{ width: 12, textAlign: "center", color: C.dim, fontWeight: 800, fontSize: 11 }}>·</span>
              : <span style={{ width: 12, textAlign: "center", fontWeight: 800, fontSize: 11.5, color: r.passed ? C.green : C.red }}>{r.passed ? "✓" : "✕"}</span>}
            {r.name
              ? <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 11.5, color: C.sub, lineHeight: 1.3, display: "block" }}>{r.name}</span>
                  {r.detail ? <span style={{ fontSize: 9.5, color: C.dim, display: "block", lineHeight: 1.3 }}>{r.detail}</span> : null}
                </span>
              : <span className="shimmer" style={{ flex: 1, height: 8, background: C.grayBg, borderRadius: 4 }} />}
            <span style={{ ...num, fontSize: 10.5, fontWeight: 600, color: r.win != null ? C.meta : C.dim }}>
              {r.win != null ? `${r.win}%` : "—"}</span>
          </div>))}
      </div>
    </div>
  );
}

type MosData = { pct: number; cushion_rupees: number; fair_anchor: number;
  anchor_source: string; gmp_ref: number | null; note?: string | null; open_ref?: number | null };
function MosTile({ d: m, live }: { d: MosData | null; live?: number | null }) {
  const good = m != null && m.pct >= 5, bad = m != null && m.pct < 0;
  const col = m == null ? C.dim : good ? C.green : bad ? C.red : C.amber;
  return (
    <div style={{ flex: "1 1 240px", minWidth: 230, border: m ? `1px solid ${C.border}` : `1px dashed ${C.border}`,
      borderRadius: 11, padding: "10px 12px", background: m ? C.bg : "transparent" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 9.5, color: C.meta, letterSpacing: .4, textTransform: "uppercase", fontWeight: 700 }}>Margin of safety</span>
        <span style={{ fontSize: 9.5, color: C.dim }}>{m ? m.anchor_source : "anchor source"}</span>
      </div>
      {m == null || m.pct == null ? (
        <>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: C.dim, marginTop: 6 }}>
            {m?.fair_anchor != null ? <>Fair <span style={{ ...num, color: C.sub }}>₹{m.fair_anchor}</span> · awaiting open</> : "awaiting"}</div>
          <div style={{ fontSize: 10, color: C.dim, marginTop: 1, lineHeight: 1.4 }}>margin computes when the open prints</div>
        </>
      ) : (
        <>
          <div style={{ marginTop: 6, fontSize: 12, color: C.sub, lineHeight: 1.45 }}>
            Fair <b style={{ ...num }}>₹{m.fair_anchor}</b>{m.open_ref != null ? <> vs open <b style={{ ...num }}>₹{m.open_ref}</b></> : null} →{" "}
            <b style={{ ...num, color: col }}>{m.pct > 0 ? "+" : ""}{m.pct}%</b>{" "}
            <span style={{ ...num, color: col }}>({m.cushion_rupees > 0 ? "+" : ""}₹{m.cushion_rupees} cushion)</span>
            {live != null && m.fair_anchor != null && (() => {
              const lp = Number(live), fa = Number(m.fair_anchor);
              const nowPct = Math.round((lp / fa - 1) * 1000) / 10;
              return <span> · now <span style={{ ...num }}>₹{lp}</span>{" "}
                <b style={{ color: nowPct >= 0 ? C.green : C.red }}>{nowPct >= 0 ? "+" : ""}{nowPct}%</b></span>;
            })()}{" "}
            <span style={{ color: col, fontWeight: 800 }}>●</span>
          </div>
          {m.gmp_ref != null ? <div style={{ ...num, fontSize: 10, color: C.meta, marginTop: 4 }}>GMP cross-check: {m.gmp_ref > 0 ? "+" : ""}{m.gmp_ref}%</div> : null}
          {m.anchor_source === "market-implied-GMP" && m.note ? <div style={{ fontSize: 10, color: C.amber, marginTop: 4, lineHeight: 1.4 }}>{m.note}</div> : null}
        </>
      )}
    </div>
  );
}

function useLivePreopen(enabled: boolean) {
  const [listings, setListings] = useState<R[] | null>(null);
  const load = useCallback(() => {
    fetch("/api/ipo/live-preopen").then(r => r.json())
      .then(j => { if (j && j.ok && Array.isArray(j.listings)) setListings(j.listings); })
      .catch(() => { /* endpoint absent/failing → tiles stay awaiting */ });
  }, []);
  useEffect(() => {
    if (!enabled) return;
    load();
    // eval window: refresh through pre-open + decision window (8:55–10:20 IST = 3:25–4:50 UTC)
    const inWin = () => { const n = new Date(); const d = n.getUTCDay();
      if (d === 0 || d === 6) return false;
      const m = n.getUTCHours() * 60 + n.getUTCMinutes(); return m >= 205 && m <= 290; };
    const t = setInterval(() => { if (inWin()) load(); }, 60000);
    return () => clearInterval(t);
  }, [enabled, load]);
  return listings;
}

function LiveDecisionPanel({ L }: { L: R | null }) {
  // Countdown to the 10:14 IST decision deadline (2-min grace off 10:16 — Rakesh 2026-07-16).
  // Pure client time — no API. The layered tiles below are DESIGNED AWAITING states shaped
  // to the confirmed backend contract (rules_static/rules_live/pre-open book/score/volume);
  // they bind when the endpoint ships. Zero invented bindings today.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const ist = new Date(now + 5.5 * 3600000);
  const mins = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  const dl = L && typeof L.deadline_ist === "string" ? String(L.deadline_ist).split(":") : null;
  const deadline = dl && dl.length === 2 ? Number(dl[0]) * 60 + Number(dl[1]) : 10 * 60 + 14; // 10:14 IST
  const secsLeft = (deadline - mins) * 60 - ist.getUTCSeconds();
  // OFFICIAL NSE special pre-open (IST), corrected post-LASER 2026-07-16:
  // 9:00–9:45 order entry (we tick 43:00 to a 9:43 buffer) · 9:45–9:55
  // discovery · 9:55–10:00 buffer · 10:00 trading. Decision by 09:58.
  const entryEnd = 9 * 60 + 43;               // order-entry buffer (9:45 − 2min)
  const secsEntry = (entryEnd - mins) * 60 - ist.getUTCSeconds();
  const phase = mins < 9 * 60 ? "pre"
    : mins < entryEnd ? "entry"
    : mins < 9 * 60 + 45 ? "entryClosed"
    : mins < 9 * 60 + 55 ? "discovery"
    : secsLeft > 0 ? "final" : "past";
  const pre = phase === "pre", past = phase === "past";
  const listedPast = (() => {
    const ld = L?.listing_date ? new Date(String(L.listing_date)) : null;
    if (!ld || isNaN(+ld)) return false;
    // 2026-07-21 (owner screenshot): 'DECISION WINDOW (ARCHIVED) · listed'
    // before the open. listing_date arrives midnight-UTC; parsing it with
    // browser-LOCAL getters shifts it to Jul-20 in US-Central, so IST-today
    // (Jul-21) > local-listing (Jul-20) => 'archived' on every listing
    // morning viewed from the US. Compare UTC parts to UTC parts.
    const t0 = Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate());
    const l0 = Date.UTC(ld.getUTCFullYear(), ld.getUTCMonth(), ld.getUTCDate());
    return t0 > l0;
  })();
  const showSecs = phase === "entry" ? Math.max(0, secsEntry) : Math.max(0, secsLeft);
  const mm = Math.floor(showSecs / 60), ss = showSecs % 60;
  const hot = phase === "final" || (phase === "entry" && secsEntry < 5 * 60);
  const await2 = (note: string) => (
    <div style={{ fontSize: 11.5, fontWeight: 600, color: C.dim, marginTop: 4 }}>awaiting<span style={{ fontWeight: 400 }}> · {note}</span></div>);
  return (
    <div className="aac-sticky-decision" style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "14px 15px", marginBottom: 14 }}>
      {/* HERO: the deadline — sticky (feat/ux-premium): the primary answer
          stays visible while rules/evidence scroll underneath. */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: C.meta, letterSpacing: .6, textTransform: "uppercase", fontWeight: 700 }}>
          {listedPast ? "Decision window (archived)" : phase === "entry" ? "Order entry closes 9:43" : phase === "discovery" ? "Price discovery 9:45–9:55" : `Decision deadline ${String(L?.deadline_ist ?? "09:58")} IST`}</span>
        <span style={{ ...num, fontSize: 30, fontWeight: 800, lineHeight: 1,
          color: past ? C.dim : hot ? C.red : C.text, transition: "color .3s var(--ease)" }}>
          {listedPast ? "listed" : pre ? "opens 9:00" : past ? "closed" : phase === "entryClosed" ? "entry closed"
            : `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`}
        </span>
        {!pre && !past && <span style={{ fontSize: 11, color: C.meta }}>
          {phase === "entry" ? "order entry 9:00–9:45 · discovery 9:45–9:55 · trading 10:00"
           : phase === "discovery" ? "book frozen — open price forming · decide by 09:58"
           : phase === "entryClosed" ? "entry closed 9:45 · discovery starts"
           : "final window — trading opens 10:00"}</span>}
        {past && <span style={{ fontSize: 11, color: C.meta }}>decision closed — trading from 10:00 · reopens next listing morning</span>}
        <span style={{ marginLeft: "auto", textAlign: "right" }}>
          {L?.live_price != null && (
            <span style={{ ...num, display: "inline-flex", alignItems: "center", gap: 6,
              fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 3 }}>
              <span className="livedot" style={{ width: 6, height: 6 }} />₹{String(L.live_price)}</span>
          )}
          <span style={{ display: "block", fontSize: 9, color: C.meta, letterSpacing: .5, textTransform: "uppercase", fontWeight: 700 }}>Confidence</span>
          <span style={{ ...num, fontSize: 24, fontWeight: 800, lineHeight: 1, transition: "color .3s var(--ease)",
            color: L?.confidence == null ? C.dim : Number(L.confidence) >= 65 ? C.green : Number(L.confidence) >= 40 ? C.amber : C.red }}>
            {L?.confidence != null ? String(L.confidence) : "—"}</span>
          <span style={{ ...num, display: "block", fontSize: 9, color: C.meta }}>
            {L?.rules_passed != null ? `${L.rules_passed}/${L.rules_total} rules pass` : "win-rate-weighted · awaiting"}</span>
        </span>
      </div>
      {/* PR-D readiness gate: INCOMPLETE research is a first-class state —
          a go-signal with unread research is treated as WATCH, and we say
          exactly which inputs are missing (server-attested, never guessed). */}
      {L && (L as R).news != null && (()=>{const n=(L as R).news as R;return (
        <div style={{margin:"6px 0 8px",fontSize:11.5,color:C.sub}}>
          <span style={{fontWeight:800,color:C.meta,fontSize:9.5,letterSpacing:.4,textTransform:"uppercase"}}>Street · {String(n.publisher)}</span>{" "}
          <a href={String(n.url)} target="_blank" rel="noopener noreferrer" style={{color:C.blue,fontWeight:600}}>{String(n.headline)}</a>
        </div>);})()}
      {L && L.research_ready === false && (
        <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 9, background: C.amberBg,
          border: `1px solid ${C.amberBd}`, display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: .5, color: C.amber, textTransform: "uppercase" }}>Research incomplete</span>
          <span style={{ fontSize: 11.5, color: C.sub }}>
            {Array.isArray(L.research_missing) && L.research_missing.length
              ? `missing: ${(L.research_missing as string[]).join(" · ")}`
              : "required research inputs unavailable"} — treat any go-signal as WATCH, not BUY</span>
        </div>
      )}
      {/* two-layer rule cards: static @9:30, live firming to 10:08 — bind rules_static/rules_live */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <RuleCard title="Static rules" when="scored 9:30" rules={(L?.rules_static as LiveRule[] | undefined) ?? null} />
        <RuleCard title="Live rules" when="firms to 10:08" rules={(L?.rules_live as LiveRule[] | undefined) ?? null} />
        <MosTile live={L?.live_price != null ? Number(L.live_price) : null} d={L?.mos ? { ...(L.mos as MosData), open_ref: (L.book as {discoveryPrice?: number | null} | null)?.discoveryPrice ?? null } : null} />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        {(() => {
          const bk = L?.book as {discoveryPrice: number | null; buyQty: number; sellQty: number; leanPct: number | null} | null;
          if (!bk) return (
            <div style={{ flex: "1 1 150px", minWidth: 140, border: `1px dashed ${C.border}`, borderRadius: 10, padding: "9px 11px" }}>
              <div style={{ fontSize: 9.5, color: C.meta, letterSpacing: .4, textTransform: "uppercase", fontWeight: 600 }}>Pre-open book</div>
              {await2("depth flows during pre-open/market hours")}
            </div>);
          const lean = bk.leanPct;
          const lc = lean == null ? C.dim : lean > 0 ? C.green : lean < 0 ? C.red : C.meta;
          return (
            <div style={{ flex: "1 1 150px", minWidth: 140, border: `1px solid ${C.border}`, background: C.bg, borderRadius: 10, padding: "9px 11px" }}>
              <div style={{ fontSize: 9.5, color: C.meta, letterSpacing: .4, textTransform: "uppercase", fontWeight: 600 }}>Pre-open book</div>
              <div style={{ ...num, fontSize: 14, fontWeight: 800, marginTop: 4 }}>
                {bk.discoveryPrice != null ? `₹${bk.discoveryPrice}` : "—"}
                {lean != null && <span style={{ color: lc, marginLeft: 7, fontSize: 12 }}>{lean > 0 ? "+" : ""}{lean}% lean</span>}
              </div>
              <div style={{ ...num, fontSize: 9.5, color: C.meta, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                buy {Number(bk.buyQty).toLocaleString()} · sell {Number(bk.sellQty).toLocaleString()}</div>
              {(() => {
                const b2 = Number(bk.buyQty), s2 = Number(bk.sellQty);
                if (!(b2 > 0) || !(s2 > 0)) return null;
                const heavy = s2 >= b2;
                const ratio = (heavy ? s2 / b2 : b2 / s2).toFixed(1).replace(/\.0$/, "");
                return <div style={{ fontSize: 10, fontWeight: 600, marginTop: 3,
                  color: heavy ? C.red : C.green }}>
                  {heavy ? `${ratio}× more sellers than buyers` : `${ratio}× more buyers than sellers`}</div>;
              })()}
            </div>);
        })()}
        <div style={{ flex: "1 1 150px", minWidth: 140, border: `1px dashed ${C.border}`, borderRadius: 10, padding: "9px 11px" }}>
          <div style={{ fontSize: 9.5, color: C.meta, letterSpacing: .4, textTransform: "uppercase", fontWeight: 600 }}>Volume confirm · 10:29–11:00</div>
          <VolumeConfirm sym={String(L?.sym ?? "")} />
        </div>
      </div>
      {(() => {
        const flags = (L?.avoid_flags as string[] | undefined) ?? [];
        const gate = String(L?.rhp_gate ?? "").toLowerCase();
        const reject = L?.rhp_reject === true;
        if (!flags.length && !gate && !reject) return null;
        return (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
            {reject && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#fff", background: C.red,
              border: `1px solid ${C.red}`, borderRadius: 999, padding: "3px 10px" }}>✕ RHP REJECT</span>}
            {!reject && gate && <span style={{ fontSize: 10.5, fontWeight: 700,
              color: gate === "watch" ? C.amber : C.sub, background: gate === "watch" ? C.amberBg : C.grayBg,
              border: `1px solid ${gate === "watch" ? C.amberBd : C.border}`, borderRadius: 999, padding: "3px 10px" }}>
              RHP gate · {gate}</span>}
            {flags.map((f, i) => <span key={i} style={{ fontSize: 10.5, fontWeight: 600, color: C.red,
              background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 999, padding: "3px 10px" }}>⚑ {String(f)}</span>)}
          </div>
        );
      })()}
      {L?.last_eval_ist ? <div style={{ ...num, fontSize: 9, color: C.dim, marginTop: 8, textAlign: "right" }}>last eval {String(L.last_eval_ist)} IST</div> : null}
    </div>
  );
}

const card: React.CSSProperties = { background:C.surface, border:`1px solid ${C.border}`,
  borderRadius:16, padding:"16px 18px", marginBottom:14,
  boxShadow:"0 1px 0 rgba(255,255,255,.9) inset, 0 12px 32px -10px rgba(28,36,58,.28), 0 3px 10px -3px rgba(28,36,58,.16)" };
const th: React.CSSProperties = { fontFamily:"var(--f-mono)", textAlign:"left", fontSize:10.5, color:C.meta,
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
        <rect x="0" y={y(ceil)} width={W} height={Math.max(0,y(floor)-y(ceil))} fill={C.blueBg}/>}
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
    fontSize:15,width:"100%",fontFamily:MONO,color:C.text,background:C.surface};
  const lbl: React.CSSProperties = {fontSize:12,fontWeight:700,color:C.meta,marginBottom:5,display:"block"};
  const bp=Number(buyPx)||0, sp=Number(sellPx)||0, sh=Number(shares)||0;
  const pct = bp>0&&sp>0 ? ((sp-bp)/bp)*100 : null;
  const pnl = pct!=null&&sh>0 ? (sp-bp)*sh : null;
  return <>
    <div style={{...card,borderTop:`3px solid ${C.blue}`}}>
      <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:16}}>Share sizer — how many shares for your capital</b>
      <div style={{fontSize:12.5,color:C.meta,marginTop:2,marginBottom:14}}>
        On listing day (9:45–10:14 decision window) the price moves as discovery happens. Enter your capital and the prices NSE is showing — see how many shares you can buy at each.</div>
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
      <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:16}}>Return calculator — your gain or loss</b>
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
      <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:16}}>Target ladder — price at each % gain</b>
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
  const [d, setD] = useState<{cards:R[];live:R[];levels:R[];blocks:R[];post:R[];brlm:R[];dl:R[];track?:R[]}|null>(null);
  const [err, setErr] = useState<string|null>(null);
  const [view, setView] = useState("command");
  const [vFilter, setVFilter] = useState("ALL");
  const [liveSel, setLiveSel] = useState<string | null>(null);
  const preopen = useLivePreopen(view === "live");
  // ── Phase-1 fix #1: live tick overlay ─────────────────────────────────────
  // The ipo-command payload is KV-cached for 12h, so its `live` ticks are stale
  // on listing morning. Poll /api/ipo/tick-feed?live=1 (KV-only fast path, ZERO
  // Neon) every 5s for 7-day-window symbols, and overlay the freshest tick.
  // IST market hours regardless of the viewer's timezone (user is CST):
  // 09:00 IST = 03:30 UTC (210 min) · 15:30 IST = 10:00 UTC (600 min), Mon–Fri.
  const [liveOverlay, setLiveOverlay] = useState<Record<string, R>>({});
  useEffect(() => {
    if (view !== "live" || !d) return;
    const inISTMarketHours = () => {
      const n = new Date(); const dow = n.getUTCDay();
      if (dow === 0 || dow === 6) return false;
      const m = n.getUTCHours() * 60 + n.getUTCMinutes();
      return m >= 210 && m <= 600;
    };
    const syms = Array.from(new Set((d.cards || [])
      .filter(c => {
        if (!c.sym || !c.listing_date) return false;
        const days = (Date.now() - new Date(String(c.listing_date)).getTime()) / 86400000;
        return days >= 0 && days <= 7;
      })
      .map(c => String(c.sym))));
    if (!syms.length) return;
    let stop = false;
    const poll = () => {
      if (stop || !inISTMarketHours()) return;
      for (const sym of syms) {
        fetch(`/api/ipo/tick-feed?symbol=${encodeURIComponent(sym)}&live=1`)
          .then(r => r.json())
          .then(j => { if (!stop && j && j.latest) setLiveOverlay(p => ({ ...p, [sym]: j.latest as R })); })
          .catch(() => { /* KV miss/offline — panel falls back to cached d.live */ });
      }
    };
    poll();
    const t = setInterval(poll, 5000);
    return () => { stop = true; clearInterval(t); };
  }, [view, d]);
  // Live <-> Command cross-links (same page; tabs are state, so link = switch + scroll)
  const jumpToCommand = (sym: string) => {
    setVFilter("ALL"); setView("command");
    // BUG F: double-rAF so the scroll target exists after the section renders
    // (single setTimeout raced the mount → needed a hard refresh before).
    requestAnimationFrame(() => requestAnimationFrame(() =>
      document.getElementById(`ipocard-${sym}`)?.scrollIntoView({ behavior: "smooth", block: "start" })));
  };
  const jumpToLive = (sym: string) => {
    setLiveSel(sym); setView("live");
    setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 40);
  };
  // BUG F: the global search dispatches aac:focus-ipo but NOTHING listened —
  // clicking a result did nothing. Wire it: switch to Command + scroll to card.
  useEffect(() => {
    // replay a search selection made on another page (see AppShell handoff)
    try {
      const pend = sessionStorage.getItem("aac:pending-focus");
      if (pend && d) {
        sessionStorage.removeItem("aac:pending-focus");
        const { company, target } = JSON.parse(pend);
        window.dispatchEvent(new CustomEvent("aac:focus-ipo", { detail: { company, target } }));
      }
    } catch { /* best-effort */ }
    const onSetView = (e: Event) => {
      const v = String((e as CustomEvent).detail?.view || "");
      if (v === "live" || v === "command" || v === "post") { setView(v); window.scrollTo({ top: 0, behavior: "smooth" }); }
    };
    window.addEventListener("aac:set-view", onSetView);
    try {
      const pv = sessionStorage.getItem("aac:pending-view");
      if (pv) { sessionStorage.removeItem("aac:pending-view"); onSetView(new CustomEvent("x", { detail: { view: pv } })); }
    } catch { /* best-effort */ }
    const onFocus = (e: Event) => {
      const company = String((e as CustomEvent).detail?.company || "");
      const target = String((e as CustomEvent).detail?.target || "");
      if (!company || !d) return;
      // Phase 9 stage-aware routing: LISTING -> Live screen; LISTED -> post/
      // journey; UPCOMING/OPEN -> Command card (subscription lives on it).
      if (target === "live") {
        const lm = (d.cards || []).find((r: R) =>
          String(r.company_name || "").toLowerCase().includes(company.toLowerCase()) ||
          canonSym(String(r.sym || "")) === canonSym(company));
        if (lm?.sym) { jumpToLive(String(lm.sym)); return; }
      }
      // Listed IPO -> land on the POST-LISTING table, on the exact row.
      const match = (r: R) =>
        String(r.company_name || "").toLowerCase().includes(company.toLowerCase()) ||
        canonSym(String(r.sym || "")) === canonSym(company);
      const postHit = (d.post || []).find(match);
      if (postHit) {
        setView("post");
        requestAnimationFrame(() => requestAnimationFrame(() =>
          document.getElementById(`postrow-${canonSym(String(postHit.sym || postHit.company_name || ""))}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" })));
        return;
      }
      // Not listed yet (upcoming/open) -> Command card, as before.
      const hit = (d.cards || []).find(match);
      if (!hit) return;
      setVFilter("ALL"); setView("command");
      requestAnimationFrame(() => requestAnimationFrame(() =>
        document.getElementById(`ipocard-${hit.sym}`)?.scrollIntoView({ behavior: "smooth", block: "start" })));
    };
    window.addEventListener("aac:focus-ipo", onFocus);
    return () => { window.removeEventListener("aac:focus-ipo", onFocus); window.removeEventListener("aac:set-view", onSetView); };
  }, [d]);
  const autoLive = useRef(false);
  useEffect(() => {
    if (autoLive.current || !d) return;
    const n = new Date(); const day = n.getUTCDay();
    const m = n.getUTCHours() * 60 + n.getUTCMinutes();
    const mkt = day !== 0 && day !== 6 && m >= 225 && m <= 600;
    if (mkt && (d.live||[]).length > 0) setView("live");
    autoLive.current = true;
  }, [d]);
  const loadData = useCallback(() => {
    fetch("/api/ipo-command").then(r=>r.json())
      .then(j => j.error ? setErr(j.error) : (setErr(null), setD(j)))
      .catch(e => setErr(String(e)));
  }, []);
  useEffect(() => { loadData(); }, [loadData]);
  // Note: IPO command data refreshes nightly (16:00 IST pipeline), so we do NOT
  // poll on an interval — that kept Neon compute awake 24/7 and drove the bill up.
  // The user can pull-to-refresh or reopen the app to re-fetch.

  const cards = d?.cards || [];
  const degraded = (d as {degraded?: string} | null)?.degraded;
  // BUG A fix: canonicalize before de-duping so symbol variants (LASER / LASER-EQ)
  // collapse to ONE chip + ONE card. Root cause of the recurring double-Laser.
  const canonSym = (x: string) => x.toUpperCase().replace(/[-_.]?(EQ|BE|BZ|NS)$/i, "").replace(/[^A-Z0-9]/g, "");
  const liveSyms = Array.from(new Map((d?.live||[]).map(t=>[canonSym(String(t.symbol)), String(t.symbol)])).values());
  const liveCanon = Array.from(new Set((d?.live||[]).map(t=>canonSym(String(t.symbol)))));
  // Live screen window: any IPO listed within the last 7 days (payload fields only)
  const windowCards = (() => {
    const raw = cards.filter(c => {
      if (!c.listing_date || !c.sym) return false;
      const days = (Date.now() - new Date(String(c.listing_date)).getTime()) / 86400000;
      return days >= 0 && days <= 7;
    });
    // Defensive dedupe: a junk DB twin (two Laser rows, 2026-07-18) rendered
    // duplicate pills AND duplicate decision panels. One entry per canonical
    // symbol — keep the most complete row (most non-null fields). The twin
    // itself gets hunted at the data layer; the UI must survive it meanwhile.
    const best = new Map<string, { c: (typeof raw)[number]; score: number }>();
    for (const c of raw) {
      const k = canonSym(String(c.sym));
      const score = Object.values(c).filter(v => v != null).length;
      const prev = best.get(k);
      if (!prev || score > prev.score) best.set(k, { c, score });
    }
    return Array.from(best.values()).map(e => e.c);
  })();
  const next = cards.find(c=>c.state==="UPCOMING");
  const pills: [string,string][] = [["live","Live"],["command","Command"],["details","Complete Details"],["calc","Calculator"],["pb","Playbook"],
    ["open","Open Now"],["upcoming","Upcoming"],["post","Post-Listing"],["brlm","BRLM"]];
  // Deep links (2026-07-22): /dashboard/ipo2?view=details&ipo=SYM — exact
  // symbol key (strong key; never fuzzy). Selection state for details view.
  const [detailSym,setDetailSym]=useState<string>("");
  useEffect(()=>{
    try{
      const sp=new URLSearchParams(window.location.search);
      const v=sp.get("view"); const ipo=sp.get("ipo");
      if(ipo) setDetailSym(ipo.toUpperCase());
      if(v==="details") setView("details");
    }catch{/* best-effort */}
  },[]);

  return (
    <div style={{padding:"16px 20px",background:"transparent",minHeight:"100vh",maxWidth:1500,margin:"auto",
      font:'14px/1.45 -apple-system,"Segoe UI",Inter,Roboto,sans-serif',color:C.text,
      alignItems:"start"}} className="ipo-shell">
      {degraded && <div style={{margin:"10px 0"}}>
        <ErrorState title="Data engine degraded — showing what we can."
          detail={String(degraded)} onRetry={()=>window.location.reload()}/></div>}
      <style>{`
        .ipo-shell{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px}
        @media (max-width:900px){.ipo-shell{grid-template-columns:1fr}.ipo-shell aside{order:-1}}
      `}</style>
      <div key={view} className="aac-view" style={{minWidth:0}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",flexWrap:"wrap",gap:10}}>
        <div><h1 style={{fontFamily:"var(--f-display)",fontSize:20,fontWeight:800,margin:0,letterSpacing:-0.3}}>IPO Command Center</h1>
          <div style={{fontSize:12,color:C.meta}}>Nightly pipeline · Chittorgarh + SBI + NSE + Kite ·
            {d ? ` refreshed ${new Date().toLocaleTimeString()}` : " loading…"}</div></div>
        <ThemeToggle/>
      </div>
      {!d && <div style={{marginTop:12}}><Skeleton h={120} n={4}/></div>}
      {view==="details" && d && (()=>{
        const all=(d.cards||[]) as R[];
        const sel=all.find(c=>String(c.sym||"").toUpperCase()===detailSym) ?? all[0];
        return (
          <div style={{marginTop:12}}>
            <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:10}}>
              {all.map((c,i)=>(
                <button key={i} onClick={()=>setDetailSym(String(c.sym||"").toUpperCase())}
                  aria-pressed={sel===c}
                  style={{fontSize:10.5,fontWeight:700,padding:"5px 11px",borderRadius:999,cursor:"pointer",
                    border:`1px solid ${sel===c?C.amberBd:C.border}`,background:sel===c?C.amberBg:C.surface,color:sel===c?C.gold:C.meta}}>
                  {String(c.sym||c.company_name||"")}</button>))}
            </div>
            <CompleteDetails c={sel as R}/>
          </div>
        );})()}

      {/* engine strip — plain-English grades, rigor one line below */}
      <div style={{...card,marginTop:12}}>
        <div style={{display:"flex",gap:22,alignItems:"center",flexWrap:"wrap"}}>
          <div style={{maxWidth:300}}>
            <div style={{fontWeight:800,fontSize:14}}>Every IPO gets a grade before it lists</div>
            <div style={{fontSize:12,color:C.meta}}>based on how 370 IPOs behaved over the last 15 years</div>
          </div>
          {[["STRONG grade","8.1 of 10 worked","n=43",C.green],
            ["FAVORABLE","7.9 of 10 worked","n=92",C.blue],
            ["NEUTRAL","7.3 of 10 worked","n=145",C.text],
            ["AVOID grade","6 of 10 — skip","n=93",C.red]].map((s,i)=>(
            <div key={i} title="worked = made money buying at the listing open and selling at the best close within 10 trading days">
              <div style={{fontSize:10.5,color:C.meta,textTransform:"uppercase",letterSpacing:.4}}>{s[0]}</div>
              <div style={{fontSize:17,fontWeight:800,color:s[3] as string}}>{s[1]}</div>
              <div style={{fontSize:12,color:C.meta}}>{s[2]}</div></div>))}
        </div>
        <div style={{fontSize:11.5,color:C.dim,marginTop:8}}>
          “Worked” = best close within 10 sessions beat the open (a CEILING, not an executable exit — see Playbook for real exit rules).
          Bands verified monotonic on clean data (spec §2A): AVOID 60% → NEUTRAL 73% → FAVORABLE 79% → STRONG 81% · baseline 72%/+5.9 (n=370).
        </div>
      </div>

      <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"12px 0"}}>
        {pills.map(([k,l])=>(
          <span key={k} role="button" tabIndex={0} aria-pressed={view===k} aria-label={`Switch to ${l}`}
            onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setView(k);}}}
            onClick={()=>setView(k)} style={{cursor:"pointer",userSelect:"none",
            border:`1px solid ${view===k?C.amberBd:C.border}`,background:view===k?C.amberBg:C.surface,
            color:view===k?C.gold:C.meta,borderRadius:20,padding:"7px 14px",fontSize:12.5,fontWeight:view===k?700:500,
            transition:"all .2s var(--ease)"}}>{k==="live" && liveSyms.length>0 ? <><span className="livedot" style={{width:5,height:5,marginRight:5,verticalAlign:"middle"}}/>{l}</> : l}</span>))}
      </div>
      {err && <div style={{margin:"6px 0"}}><ErrorState title="API error" detail={String(err)} onRetry={()=>window.location.reload()}/></div>}

      {/* LIVE — the trading surface: live panel + exit engine side-by-side */}
      {view==="live" && <>
        <div style={{fontSize:12,color:C.meta,margin:"0 2px 8px"}}>
          {liveSyms.length ? <><span className="livedot" style={{marginRight:5,verticalAlign:"middle"}}/>{liveSyms.length} live capture</> : "feed idle"} ·
          {windowCards.length} in the 7-day window · launcher 09:10 IST
        </div>
        {windowCards.length>1 && (
          <div style={{display:"flex",gap:6,flexWrap:"wrap",margin:"0 0 10px"}}>
            {windowCards.map(w => { const ws = String(w.sym);
              const sel = (liveSel ?? String(windowCards[0].sym)) === ws;
              return (
              <span key={ws} onClick={()=>setLiveSel(ws)} style={{cursor:"pointer",userSelect:"none",
                fontFamily:"var(--f-display)",fontSize:12,fontWeight:sel?700:500,padding:"6px 13px",borderRadius:10,
                border:`1px solid ${sel?C.amberBd:C.border}`,background:sel?C.amberBg:C.surface,
                color:sel?C.gold:C.meta,transition:"all .2s var(--ease)"}}>
                {liveCanon.includes(canonSym(ws)) && <span className="livedot" style={{width:5,height:5,marginRight:5,verticalAlign:"middle"}}/>}
                {String(w.company_name||ws).split(" ").slice(0,2).join(" ")}
              </span>);})}
          </div>
        )}
        {windowCards.length===0 && <div style={card}>
          <div style={{border:`1px dashed ${C.border}`,borderRadius:12,padding:"16px 14px"}}>
            <div style={{fontSize:11,color:C.meta,textTransform:"uppercase",letterSpacing:.5,fontWeight:600}}>No IPO in the live window</div>
            <div style={{fontSize:12.5,color:C.meta,marginTop:6,lineHeight:1.5}}>
              This screen holds every IPO for 7 days after listing. Next listing: {next ? `${next.company_name} · ${D(next.listing_date)}` : "—"}.</div>
          </div>
        </div>}
        {windowCards.filter(w => String(w.sym) === (liveSel ?? String(windowCards[0]?.sym))).map((wc) => {
          const sym = String(wc.sym);
          const isLive = liveCanon.includes(canonSym(sym)) || liveOverlay[sym] != null;
          return (
          <div key={sym}>
          <div style={{display:"flex",justifyContent:"flex-end",margin:"0 2px 6px"}}>
            <span onClick={()=>jumpToCommand(sym)} style={{cursor:"pointer",fontSize:11.5,fontWeight:600,
              color:C.gold,display:"inline-flex",alignItems:"center",gap:4}}>
              Full analysis on Command →</span>
          </div>
          <LiveDecisionPanel L={(preopen || []).find(l => String(l.sym) === sym) ?? null}/>
          <div className="live-split">
            <div className="lp">
              {isLive ? (
                <>{(() => {
          const ticks = (d!.live).filter(t=>t.symbol===sym);
          const last = (liveOverlay[sym] ?? ticks[ticks.length-1] ?? {}) as R; // KV overlay wins over cached snapshot
          const lv = (d!.levels).find(l=>l.symbol===sym) || {};
          const meta = cards.find(c=>c.sym===sym) || {};
          const blk = (d!.blocks).filter(b=>b.symbol===sym);
          const ltp = N(last.ltp), vwap = N(last.vwap), open = N(lv.listing_open);
          return (
            <div key={sym} style={{...card,borderColor:C.greenBd,borderWidth:2}}>
              <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
                <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
                  <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:16}}>{sym} · {String(meta.company_name||"")}</b>
                  <span style={{display:"inline-flex",alignItems:"center",gap:5,color:C.green,fontWeight:700,fontSize:11,letterSpacing:.5}}><span className="livedot"/>LIVE</span>
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
                <div style={{flex:2,minWidth:300}}>
                  <div style={{display:"flex",gap:16,alignItems:"baseline",flexWrap:"wrap"}}>
                    <span style={{...num,fontSize:28,fontWeight:800}}>{ltp!=null?`₹${ltp}`:"—"}</span>
                    {ltp!=null&&open!=null&&open>0&&<span style={{...num,fontWeight:700,
                      color:ltp>=open?C.green:C.red}}>{((ltp-open)/open*100).toFixed(1)}% vs open ₹{open}</span>}
                    {vwap!=null&&<span style={{...num,fontSize:12,color:C.meta}}>VWAP ₹{vwap} · {ltp!=null&&ltp>=vwap?"above":"below"}</span>}
                  </div>
                  {(()=>{const L=(d?.dl||[]).find(x=>x.sym===sym);
                    return <Spark ticks={ticks} floor={N(L?.floor) ?? N(lv.floor_price)} ceil={N(L?.ceiling) ?? N(lv.ceiling_price)}/>;})()}
                  <div className="aac-cols-4" style={{marginTop:8}}>
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
                  return null; })()}</>
              ) : (
                <div style={card}>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",gap:10,flexWrap:"wrap"}}>
                    <b style={{fontFamily:"var(--f-display)",fontSize:16,letterSpacing:-0.2}}>{String(wc.company_name||sym)}</b>
                    <span style={{...num,fontSize:11,color:C.meta}}>listed {D(wc.listing_date)}</span>
                  </div>
                  <div style={{border:`1px dashed ${C.border}`,borderRadius:11,padding:"12px 13px",marginTop:10}}>
                    <div style={{fontSize:10.5,color:C.meta,textTransform:"uppercase",letterSpacing:.5,fontWeight:600}}>Feed idle</div>
                    <div style={{fontSize:12,color:C.meta,marginTop:5,lineHeight:1.5}}>Market closed or capture not running — the exit engine on the right tracks daily closes meanwhile.</div>
                  </div>
                </div>
              )}

            </div>
            <div className="rp">
              <HoldStrip sym={sym}/>
            </div>
          </div>
          </div>);
        })}
      </>}

      {/* COMMAND */}
      {view==="command" && <>
        <div style={{fontSize:12,color:C.meta,margin:"0 2px 8px"}}>
          {liveSyms.length ? <><span className="livedot" style={{marginRight:5,verticalAlign:"middle"}}/>{liveSyms.length} live capture</> : "no live capture"} ·
          next listing {next ? `${next.company_name} ${D(next.listing_date)}` : "—"} ·
          launcher 09:10 · self-check 09:25 &amp; 13:00
        </div>
        <div style={{display:"flex",gap:6,flexWrap:"wrap",margin:"2px 0 10px"}}>
          {["ALL","TRADE","WATCH","CAUTION","AVOID"].map(k=>(
            <span key={k} role="button" tabIndex={0} aria-pressed={vFilter===k}
              onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setVFilter(k);}}}
              onClick={()=>setVFilter(k)} style={{cursor:"pointer",userSelect:"none",fontSize:11.5,fontWeight:700,
              padding:"4px 12px",borderRadius:999,letterSpacing:.3,
              border:`1px solid ${vFilter===k?C.blueBd:C.border}`,
              background:vFilter===k?C.blueBg:C.surface,color:vFilter===k?C.blue:C.meta}}>
              {k==="ALL"?"All":k}</span>))}
        </div>
        {cards.filter(c=>c.state!=="INWINDOW"||liveCanon.includes(canonSym(String(c.sym)))===false).map((c,i)=>{
          if (liveCanon.includes(canonSym(String(c.sym)))) return null;
          if (vFilter!=="ALL" && String(c.verdict||"")!==vFilter) return null;
          const inWin = windowCards.some(w => String(w.sym) === String(c.sym));
          return <div key={i} id={`ipocard-${String(c.sym)}`}>
            <CardBoundary><IpoCard c={c} onJourney={(sym)=>{ window.location.href=`/dashboard/journey?sym=${sym}`; }}
              onLive={inWin ? () => jumpToLive(String(c.sym)) : undefined}/></CardBoundary>
          </div>;
        })}
        {vFilter!=="ALL" && cards.filter(c=>String(c.verdict||"")===vFilter && !liveCanon.includes(canonSym(String(c.sym)))).length===0 &&
          <EmptyState title={`No ${vFilter} verdicts in the current window.`}
            hint="Verdicts update after each pipeline run.">
            <button onClick={()=>setVFilter("ALL")} style={{fontSize:11,fontWeight:700,padding:"6px 12px",
              borderRadius:999,border:`1px solid ${C.border}`,background:C.surface,color:C.sub,cursor:"pointer"}}>Show all</button>
          </EmptyState>}
      </>}

      {/* PLAYBOOK */}
      {view==="calc" && <Calculator/>}

      {view==="pb" && <>
        <div style={{...card, background:C.amberBg, border:`1.5px solid ${C.amberBd}`}}>
          <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:16}}>The House Rules — the whole strategy in 3 lines</b>
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
              <div style={{minWidth:34,height:34,borderRadius:"50%",background:C.gold,color:C.bg,
                display:"flex",alignItems:"center",justifyContent:"center",fontWeight:800,fontSize:16}}>{n}</div>
              <div><div style={{fontWeight:800,fontSize:13.5}}>{t}</div>
                <div style={{fontSize:12.5,color:C.sub,marginTop:2}}>{d2}</div></div>
            </div>))}
          <div style={{marginTop:10,padding:"9px 12px",background:C.greenBg,border:`1px solid ${C.greenBd}`,
            borderRadius:9,fontSize:12.5,color:C.green}}>
            <b>The honest math (two iterations: 2026-07-10 &amp; 2026-07-13):</b> the core giant-opens-positive trade wins
            ~92 in 100; adding 30+ anchors on a mega issue reaches <b>85% with a near-zero downside floor</b>.
            Everything outside the rules — small, pricey, euphoric, or reject — is watch-only.
          </div>
        </div>

        <div style={card}>
          <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:15}}>The two strategies — validated</b>
          <div style={{fontSize:11.5,color:C.meta,marginTop:2,marginBottom:12}}>
            Two layers: a <b>quality gate</b> (before listing) and a <b>tradeable signal</b> (buy-at-open).
            Tradeable signal tested <b>2026-07-13</b> on 585 clean IPOs (2016+); quality gate = RHP forensic read of 448 prospectuses.
          </div>
          {[
            ["Q","Quality gate (before listing)",C.blue,C.blueBg,C.blueBd,
             "RHP forensic read of the prospectus → clean / watch / reject. A reject is a hard pass. This is the junk filter, not the entry — it tells you what NOT to touch.",
             "448 prospectuses read"],
            ["T","Tradeable signal (buy at open)",C.green,C.greenBg,C.greenBd,
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

        <div style={card}><b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:14}}>The playbook — what to do, by setup.</b>
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
            <GmpLine c={c}/>
            <FairValueCard c={c}/>
            <WeakOpenFlag c={c}/>
            <Reasons trade={c.why_trade as string} caution={c.why_caution as string} avoid={c.why_avoid as string}/>
            <StreetConsensus consensus={c.street_consensus as string} brokers={N(c.street_brokers)} verdict={c.verdict as string}/>
            <TrustReport gate={c.rhp_gate as string} oneLine={c.rhp_one_line as string} mos={c.rhp_mos as string}
              full={c.rhp_full} confidence={c.rhp_confidence as string} company={String(c.company_name||"")}/>
            <div style={{fontSize:12,color:C.dim,marginTop:8}}>Figures = last nightly sync · live intraday capture is the next data build. QIBs bid late — a low day-1 is normal.</div>
          </div>))}
        {cards.filter(c=>c.state==="OPEN").length===0&&<div style={card}><span style={{fontSize:13,color:C.meta}}>No IPO is open for bidding right now.</span></div>}
      </>}

      {/* UPCOMING */}
      {view==="upcoming" && <div style={{...card,overflowX:"auto"}}>
        <table style={{minWidth:560,width:"100%",borderCollapse:"collapse"}}>
          <thead><tr><th style={th}>Lists</th><th style={th}>Company</th><th style={th}>Size</th><th style={th}>GMP d-1</th><th style={th}>Anchors</th><th style={th}>Verdict</th><th style={th}>Why</th></tr></thead>
          <tbody>{cards.filter(c=>{
            if (c.state!=="UPCOMING" && c.state!=="LISTING") return false;
            // UAT bug 2026-07-21: SBIFUNDS stayed on Upcoming AFTER listing —
            // state flips only at the next pipeline run. Drop rows whose
            // listing date (UTC parts) is before IST-today.
            if (c.listing_date) {
              const ld = new Date(String(c.listing_date));
              const ist = new Date(Date.now() + 5.5*3600_000);
              if (Date.UTC(ld.getUTCFullYear(), ld.getUTCMonth(), ld.getUTCDate())
                  < Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate())) return false;
            }
            return true;
          }).map((c,i)=>{
            const istT=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
            const od=c.open_date?String(c.open_date).slice(0,10):null;
            const cd=c.close_date?String(c.close_date).slice(0,10):null;
            const status=c.state==="LISTING"?"LISTS TODAY":od&&istT<od?`opens ${od.slice(5)}`:cd&&istT<=cd?`● OPEN · closes ${cd.slice(5)}`:`allotment · lists ${String(c.listing_date??"").slice(5,10)}`;
            return (
            <tr key={i}><td style={{...td,...num}}>{D(c.listing_date)}<div style={{fontSize:9.5,color:status.startsWith("●")?C.green:C.meta,fontWeight:status.startsWith("●")?700:400}}>{status}</div></td>
              <td style={{...td,fontWeight:600,color:C.text}}>{String(c.company_name||"")}{c.quality_promoter===true?" ★":""}</td>
              <td style={{...td,...num}}>{c.issue_size_cr!=null?`₹${Number(c.issue_size_cr).toLocaleString()}cr`:"—"}</td>
              <td style={{...td,...num,fontWeight:700,color:c.gmp_day_before==null?C.dim:Number(c.gmp_day_before)>20?C.green:Number(c.gmp_day_before)>=0?C.text:C.red}}>
                {c.gmp_day_before!=null?`${Number(c.gmp_day_before)>0?"+":""}${c.gmp_day_before}%`:"—"}</td>
              <td style={{...td,...num,color:c.anchor_count!=null&&Number(c.anchor_count)>30?C.green:C.sub,fontWeight:c.anchor_count!=null&&Number(c.anchor_count)>30?700:400}}>
                {c.anchor_count!=null?String(c.anchor_count):"—"}</td>
              <td style={td}>{c.verdict!=null?<Verdict v={c.verdict as string}/>:<Chip b={c.score_band as string}/>}</td>
              <td style={{...td,fontSize:12,color:C.meta}}>{String(c.why_trade||c.why_caution||c.why_avoid||c.score_evidence||"—").split(" ; ")[0]}</td></tr>);})}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Pre-listing scores use size/valuation only — the gap weight applies itself at the open.</div>
      </div>}

      {/* POST-LISTING AUDIT */}
      {view==="post" && <div style={{...card,overflowX:"auto"}}>
        <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:14}}>Score vs reality — the standing audit</b>
        {(()=>{ const graded=(d?.post||[]).map(r=>{ const v=r.verdict as string|null, o=N(r.d10_best_pct);
            if(v==null||o==null) return null; if(v==="TRADE") return o>0; if(v==="AVOID") return o<=0; return null; })
            .filter((x):x is boolean=>x!=null);
          const hits=graded.filter(Boolean).length;
          if(!graded.length) return null;
          return <div style={{display:"inline-flex",gap:8,alignItems:"baseline",marginLeft:12,fontSize:12.5}}>
            <span style={{...num,fontWeight:800,color:hits/graded.length>=0.5?C.green:C.red}}>
              {hits}/{graded.length} calls hit ({Math.round(100*hits/graded.length)}%)</span>
            <span style={{color:C.dim,fontSize:11}}>TRADE→popped · AVOID→flopped · last {(d?.post||[]).length} listings</span>
          </div>; })()}
        <table style={{minWidth:560,width:"100%",borderCollapse:"collapse",marginTop:8}}>
          <thead><tr><th style={th}>Listed</th><th style={th}>Company</th><th style={th}>Verdict</th>
            <th style={th}>Gap</th><th style={th}>Listing gap</th><th style={th}>10-session best</th><th style={th}>Call</th><th style={th}>Journey</th></tr></thead>
          <tbody>{(d?.post||[]).map((r,i)=>(
            <tr key={i} id={`postrow-${canonSym(String(r.sym || r.company_name || i))}`}><td style={{...td,...num}}>{D(r.listing_date)}</td>
              <td style={{...td,fontWeight:600,color:C.text}}>{String(r.company_name||"")}</td>
              <td style={td}>{r.verdict!=null?<Verdict v={r.verdict as string}/>:<Chip b={r.score_band as string}/>}</td>
              <td style={td}>{String(r.gap_bucket||"—")}</td>
              <td style={{...td,...num}}>{r.listing_gap_pct!=null?`${Number(r.listing_gap_pct).toFixed(1)}%`:"—"}</td>
              <td style={{...td,...num,fontWeight:700,color:N(r.d10_best_pct)==null?C.dim:(N(r.d10_best_pct)!>0?C.green:C.red)}}>
                {r.d10_best_pct!=null?`${Number(r.d10_best_pct).toFixed(1)}%`:<span style={{color:C.dim,fontSize:11}}>awaiting d10</span>}</td>
              <td style={td}>{(()=>{ const v=r.verdict as string|null, o=N(r.d10_best_pct);
                if(v==null||o==null) return <span style={{color:C.dim}}>—</span>;
                const bullish=v==="TRADE", hit=bullish?o>0:(v==="AVOID"?o<=0:null);
                if(hit==null) return <span style={{color:C.dim,fontSize:11}}>n/a</span>;
                return <span style={{...num,fontWeight:800,color:hit?C.green:C.red}}>{hit?"✓ hit":"✗ miss"}</span>; })()}</td>
              <td style={td}>{r.sym?<a href={`/dashboard/journey?sym=${r.sym}`} style={{color:C.blue,fontWeight:600,textDecoration:"none"}}>hold →</a>:"—"}</td></tr>))}</tbody>
        </table>
        <div style={{fontSize:12,color:C.dim,marginTop:8}}>Misses feed the quarterly re-weight. 10-session outcomes precompute nightly.</div>
      </div>}

      {/* BRLM */}
      {view==="brlm" && <div style={{...card,overflowX:"auto"}}>
        <b style={{fontFamily:"var(--f-display)",letterSpacing:-0.2,fontSize:14}}>Book managers — empirical, from our own outcomes</b>
        <table style={{minWidth:560,width:"100%",borderCollapse:"collapse",marginTop:8}}>
          <thead><tr><th style={th}>Lead manager</th><th style={th}>IPOs</th><th style={th}>Pop rate</th>
            <th style={th}>Med gap</th><th style={th}>10s win</th><th style={th}>10s median</th></tr></thead>
          <tbody>{(d?.brlm||[]).map((r,i)=>(
            <tr key={i}><td style={{...td,fontWeight:600,color:C.text}}>{String(r.lead||"")}</td>
              <td style={{...td,...num}}>{String(r.n)}</td>
              <td style={{...td,...num}}>{r.pop_rate!=null?`${r.pop_rate}%`:"—"}</td>
              <td style={{...td,...num,fontWeight:700,color:r.med_gap==null?C.sub:Number(r.med_gap)>0?C.green:Number(r.med_gap)<0?C.red:C.sub}}>{r.med_gap!=null?`${Number(r.med_gap).toFixed(1)}%`:"—"}</td>
              <td style={{...td,...num,fontWeight:700}}>{r.d10_win!=null?`${r.d10_win}%`:<span style={{color:C.dim,fontSize:11}}>awaiting d10</span>}</td>
              <td style={{...td,...num,color:r.d10_med==null?C.sub:Number(r.d10_med)>0?C.green:Number(r.d10_med)<0?C.red:C.sub}}>{r.d10_med!=null?`${Number(r.d10_med).toFixed(1)}%`:<span style={{color:C.dim,fontSize:11}}>awaiting d10</span>}</td></tr>))}</tbody>
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
