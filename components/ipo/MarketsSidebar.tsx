"use client";
import { useEffect, useState } from "react";

// Compact Domestic + Global markets rail for the right side of the IPO page.
// Self-contained: fetches /api/market/global + /api/market/snapshot (same as Today).
// Styled to match the ipo2 palette.

type GRow = { label: string; value: string; change: number | null };
const C = { surface:"#FBFCFD", border:"#DAE0E8", line:"#E7EBF1", text:"#1A2438",
  sub:"#3A4560", meta:"#68738C", green:"#0E7A4D", red:"#C4443A" };

const has = (v: unknown) => v !== null && v !== undefined && v !== "" && !(typeof v === "number" && isNaN(v));
const num = (v: unknown) => (has(v) ? Number(v) : NaN);
const first = (...vals: unknown[]) => vals.find(has);
const fmt = (v: unknown, d = 0) => (has(v) ? Number(v).toLocaleString("en-IN",{minimumFractionDigits:d,maximumFractionDigits:d}) : "—");
const cr = (v: unknown) => { if(!has(v)) return "—"; const n=Number(v); return `${n>=0?"+":""}${n.toLocaleString("en-IN",{maximumFractionDigits:0})}`; };
const sgn = (n: number | null) => (n==null?"—":`${n>=0?"+":""}${n.toFixed(2)}%`);

function Tile({ label, value, sub, tone }: { label:string; value:string; sub?:string; tone?:"up"|"down"|null }) {
  const col = tone==="up"?C.green:tone==="down"?C.red:C.text;
  return (
    <div style={{ background:"#F4F6FA", border:`1px solid ${C.line}`, borderRadius:10, padding:"8px 10px" }}>
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetch("/api/market/global",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
      fetch("/api/market/snapshot",{cache:"no-store"}).then(r=>r.json()).catch(()=>null),
    ]).then(([gg, ss]) => {
      if (!live) return;
      const g = (gg?.india) || gg || {};
      const s = (ss?.snapshot) || ss || {};
      setDom({
        nifty: fmt(first(g.nifty, s.nifty_price), 0),
        niftyChg: has(first(g.niftyChg, s.nifty_change_pct)) ? num(first(g.niftyChg, s.nifty_change_pct)) : null,
        bn: fmt(first(g.bankNifty, s.banknifty_price), 0),
        bnChg: has(first(g.bankNiftyChg, s.banknifty_change_pct)) ? num(first(g.bankNiftyChg, s.banknifty_change_pct)) : null,
        vix: fmt(first(g.vix, s.vix, s.india_vix), 2),
        fii: cr(first(g.fii, s.fii_flow, s.fii_cash_flow)),
        dii: cr(first(g.dii, s.dii_flow, s.dii_cash_flow)),
        pcr: fmt(first(g.pcr, s.pcr), 2),
      });
      // global rows — the API returns a global map; build labeled rows
      const gm = (gg?.global) || {};
      const mk = (k:string,label:string) => {
        const row = gm[k]; if(!row) return null;
        const val = first(row.value, row.price, row.last);
        const chg = first(row.change, row.changePct, row.change_pct);
        return { label, value: fmt(val, 2), change: has(chg)?num(chg):null } as GRow;
      };
      const rows = [
        mk("dowjones","🇺🇸 Dow"), mk("nasdaq","🇺🇸 Nasdaq"), mk("sp500","🇺🇸 S&P 500"),
        mk("ftse","🇬🇧 FTSE"), mk("dax","🇩🇪 DAX"), mk("nikkei","🇯🇵 Nikkei"),
        mk("hangseng","🇭🇰 Hang Seng"), mk("shanghai","🇨🇳 Shanghai"),
        mk("gold","🥇 Gold"), mk("crude","🛢️ Crude"), mk("btc","₿ Bitcoin"), mk("usdinr","💵 USD/INR"),
      ].filter(Boolean) as GRow[];
      // fallback: if the API shape differs, flatten whatever object we got
      if (!rows.length && gm && typeof gm === "object") {
        for (const [k,v] of Object.entries<any>(gm)) {
          const val = first(v?.value, v?.price, v?.last);
          const chg = first(v?.change, v?.changePct);
          if (has(val)) rows.push({ label:k, value:fmt(val,2), change:has(chg)?num(chg):null });
        }
      }
      setGlob(rows);
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
      </div>
      {/* Global */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:"12px 13px" }}>
        <div style={{ fontSize:11, fontWeight:800, letterSpacing:.5, textTransform:"uppercase", color:C.sub, marginBottom:9 }}>Global Markets</div>
        {loading ? <div style={{ fontSize:12, color:C.meta, padding:"8px 0" }}>Loading…</div> : (
          <div style={{ display:"flex", flexDirection:"column", gap:4, maxHeight:360, overflowY:"auto" }}>
            {glob.length ? glob.map(g => (
              <div key={g.label} style={{ display:"flex", alignItems:"center", gap:8, padding:"6px 8px", background:"#F4F6FA", border:`1px solid ${C.line}`, borderRadius:8 }}>
                <span style={{ fontSize:11.5, color:C.sub, flex:1, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{g.label}</span>
                <span style={{ fontSize:12, fontWeight:700, color:C.text, fontFamily:"ui-monospace,monospace", minWidth:66, textAlign:"right" }}>{g.value}</span>
                <span style={{ fontSize:11, fontWeight:700, fontFamily:"ui-monospace,monospace", minWidth:52, textAlign:"right", color:(g.change??0)>=0?C.green:C.red }}>{sgn(g.change)}</span>
              </div>
            )) : <div style={{ fontSize:12, color:C.meta }}>Markets data unavailable.</div>}
          </div>
        )}
      </div>
    </aside>
  );
}
