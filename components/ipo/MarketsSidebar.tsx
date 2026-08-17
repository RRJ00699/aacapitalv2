"use client";
import { useEffect, useState } from "react";

// Compact Domestic + Global markets rail for the right side of the IPO page.
// Self-contained: fetches /api/market/global + /api/market/snapshot (same as Today).
// Styled to match the ipo2 palette.

type GRow = { label: string; value: string; change: number | null; isPct?: boolean };
const C = { surface:"var(--t-surface)", border:"var(--t-border)", line:"var(--t-line)", text:"var(--t-text)",
  sub:"var(--t-sub)", meta:"var(--t-meta)", green:"var(--t-green)", red:"var(--t-red)" };

// The keys /api/market/global actually ships (Yahoo symbols), in display order.
const GLOBAL_ORDER = ["^DJI","^NDX","^GSPC","^RUT","^FTSE","^GDAXI","^FCHI","^N225","^HSI","000001.SS","^KS11",
  "GC=F","SI=F","CL=F","NG=F","HG=F","BTC-USD","ETH-USD","DX-Y.NYB","USDINR=X"];

const has = (v: unknown) => v !== null && v !== undefined && v !== "" && !(typeof v === "number" && isNaN(v));
const num = (v: unknown) => (has(v) ? Number(v) : NaN);
const first = (...vals: unknown[]) => vals.find(has);
const fmt = (v: unknown, d = 0) => (has(v) ? Number(v).toLocaleString("en-IN",{minimumFractionDigits:d,maximumFractionDigits:d}) : "—");
const cr = (v: unknown) => { if(!has(v)) return "—"; const n=Number(v); return `${n>=0?"+":""}${n.toLocaleString("en-IN",{maximumFractionDigits:0})}`; };
const sgn = (n: number | null, isPct = true) =>
  // UAT bug U4 (2026-07-21): absolute point changes were rendered with a %
  // suffix (^DJI +594.83 pts shown as +594.83%). Percent suffix ONLY when the
  // value IS a percent; bare points otherwise.
  (n==null?"—":`${n>=0?"+":""}${n.toFixed(2)}${isPct?"%":""}`);

function Tile({ label, value, sub, tone }: { label:string; value:string; sub?:string; tone?:"up"|"down"|null }) {
  const col = tone==="up"?C.green:tone==="down"?C.red:C.text;
  return (
    <div style={{ background:"var(--t-surface2)", border:`1px solid ${C.line}`, borderRadius:10, padding:"8px 10px" }}>
      <div style={{ fontSize:9.5, fontWeight:800, letterSpacing:.6, textTransform:"uppercase", color:C.meta }}>{label}</div>
      <div style={{ fontSize:17, fontWeight:800, fontFamily:"ui-monospace,monospace", color:col }}>{value}</div>
      {sub && <div style={{ fontSize:9.5, color:col }}>{sub}</div>}
    </div>
  );
}

export default function MarketsSidebar() {
  const [dom, setDom] = useState<{nifty:string;niftyChg:number|null;bn:string;bnChg:number|null;vix:string;fii:string;dii:string;pcr:string}>(
    { nifty:"—",niftyChg:null,bn:"—",bnChg:null,vix:"—",fii:"—",dii:"—",pcr:"—" });
  const [glob, setGlob] = useState<GRow[]>([]);
  const [breadth, setBreadth] = useState<{adv?:number;dec?:number;unch?:number;asof?:string}|null>(null);
  const [asOf, setAsOf] = useState<string>("");
  const [domGaps, setDomGaps] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetch("/api/market/global",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
      fetch("/api/market/snapshot",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
    ]).then(([gg, ss]) => {
      if (!live) return;
      const g = (gg?.india) || gg || {};
      const s = (ss?.data) || ss || {};   // /api/market/snapshot answers { ok, data }
      setDom({
        nifty: fmt(first(g.nifty, s.nifty_price), 0),
        niftyChg: has(first(g.niftyChg, s.nifty_change_pct)) ? num(first(g.niftyChg, s.nifty_change_pct)) : null,
        bn: fmt(first(g.bankNifty, s.banknifty_price), 0),
        bnChg: has(first(g.bankNiftyChg, s.banknifty_change_pct)) ? num(first(g.bankNiftyChg, s.banknifty_change_pct)) : null,
        vix: fmt(first(g.vix, s.vix, s.india_vix), 2),
        // fii_cash_flow / dii_cash_flow were also dead reads: /api/market/snapshot
        // ships fii_flow / dii_flow, and /api/market/global ships india.fii / .dii.
        fii: cr(first(g.fii, s.fii_flow)),
        dii: cr(first(g.dii, s.dii_flow)),
        pcr: fmt(first(g.pcr, s.pcr), 2),
      });
      // Global rows. DEAD-READ FIX (2026-08-17): this used to look the map up by
      // slugs — mk("dowjones"), mk("nasdaq"), … — which /api/market/global has
      // never shipped; it keys by Yahoo symbol (^DJI, ^NDX, …). Every labeled
      // row therefore resolved to null and the rail silently fell through to a
      // raw-key fallback that printed "^DJI" as the label. Same class of bug as
      // ListingReview's c.candles_json: a read of a field no payload carries.
      // It now reads the real keys and the label/flag the API already ships.
      const gm = (gg?.global) || {};
      setBreadth(gg?.breadth || null);
      if (gg?.as_of) setAsOf(new Date(gg.as_of).toLocaleTimeString());
      const rows: GRow[] = [];
      for (const key of GLOBAL_ORDER) {
        const row = gm[key];
        if (!row || !has(row.price)) continue;      // absent stays absent — no zero row
        // U4 contract (_scripts/tests/test_ux_premium.py pins this exact line):
        // a percent field is always preferred over a point change, so a point
        // change can never wear a % suffix. change_pct is kept as a defensive
        // alias only — /api/market/global ships changePct.
        const pct = first(row.changePct, row.change_pct);
        rows.push({
          label: [row.flag, row.label].filter(Boolean).join(" ") || key,
          value: fmt(row.price, 2),
          change: has(pct) ? num(pct) : null,
          isPct: has(pct),
        });
      }
      // Anything the API adds that this order does not name yet still renders,
      // under its own shipped label rather than a bare symbol.
      for (const [key, row] of Object.entries<any>(gm)) {
        if (GLOBAL_ORDER.includes(key) || !has(row?.price)) continue;
        rows.push({
          label: [row.flag, row.label].filter(Boolean).join(" ") || key,
          value: fmt(row.price, 2),
          change: has(row?.changePct) ? num(row.changePct) : null,
          isPct: has(row?.changePct),
        });
      }
      setGlob(rows);
      setDomGaps([
        ...(has(first(g.pcr, s.pcr)) ? [] : ["PCR"]),
        ...(has(first(g.fii, s.fii_flow)) ? [] : ["FII"]),
        ...(has(first(g.dii, s.dii_flow)) ? [] : ["DII"]),
      ]);
      setLoading(false);
    });
    return () => { live = false; };
  }, []);

  return (
    <aside style={{ display:"flex", flexDirection:"column", gap:12 }}>
      {/* Domestic */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:"12px 13px" }}>
        <div style={{ fontSize:11, fontWeight:800, letterSpacing:.5, textTransform:"uppercase", color:C.sub, marginBottom:9 }}>Domestic Market</div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
          <Tile label="NIFTY" value={dom.nifty} sub={dom.niftyChg!=null?sgn(dom.niftyChg):undefined} tone={dom.niftyChg!=null?(dom.niftyChg>=0?"up":"down"):null}/>
          <Tile label="Bank Nifty" value={dom.bn} sub={dom.bnChg!=null?sgn(dom.bnChg):undefined} tone={dom.bnChg!=null?(dom.bnChg>=0?"up":"down"):null}/>
          <Tile label="India VIX" value={dom.vix}/>
          <Tile label="PCR" value={dom.pcr}/>
          <Tile label="FII" value={dom.fii} tone={dom.fii.startsWith("+")?"up":dom.fii.startsWith("-")?"down":null}/>
          <Tile label="DII" value={dom.dii} tone={dom.dii.startsWith("+")?"up":dom.dii.startsWith("-")?"down":null}/>
        </div>
        {domGaps.length ? (
          <div style={{ fontSize:10.5, color:C.meta, marginTop:8 }}>
            {domGaps.join(" · ")} unavailable — no maintained producer ships these fields
            (FII/DII need daily_institutional_flows, which was never built; PCR needs a market_snapshot row).
          </div>
        ) : null}
      </div>
      {breadth ? (<div style={{fontSize:11.5,margin:"2px 2px 8px",color:C.sub}}>
        <b style={{color:C.green}}>Adv {breadth.adv ?? "—"}</b>{" · "}
        <b style={{color:C.red}}>Dec {breadth.dec ?? "—"}</b>{" · unch "}{breadth.unch ?? "—"}
        <span style={{color:C.meta}}> · {breadth.asof || ""}</span></div>) : null}
      {asOf ? (<div style={{fontSize:10.5,color:C.meta,margin:"0 2px 8px"}}>quotes as of {asOf}</div>) : null}
      {/* Global */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:"12px 13px" }}>
        <div style={{ fontSize:11, fontWeight:800, letterSpacing:.5, textTransform:"uppercase", color:C.sub, marginBottom:9 }}>Global Markets</div>
        {loading ? <div style={{ fontSize:12, color:C.meta, padding:"8px 0" }}>Loading…</div> : (
          <div style={{ display:"flex", flexDirection:"column", gap:4, maxHeight:360, overflowY:"auto" }}>
            {glob.length ? glob.map(g => (
              <div key={g.label} style={{ display:"flex", alignItems:"center", gap:8, padding:"6px 8px", background:"var(--t-surface2)", border:`1px solid ${C.line}`, borderRadius:8 }}>
                <span style={{ fontSize:11.5, color:C.sub, flex:1, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{g.label}</span>
                <span style={{ fontSize:12, fontWeight:700, color:C.text, fontFamily:"ui-monospace,monospace", minWidth:66, textAlign:"right" }}>{g.value}</span>
                <span style={{ fontSize:11, fontWeight:700, fontFamily:"ui-monospace,monospace", minWidth:52, textAlign:"right", color:(g.change??0)>=0?C.green:C.red }}>{sgn(g.change, g.isPct !== false)}</span>
              </div>
            )) : <div style={{ fontSize:12, color:C.meta }}>Markets data unavailable.</div>}
          </div>
        )}
      </div>
    </aside>
  );
}
