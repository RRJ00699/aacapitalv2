"use client"
// components/features/market-global-screen.tsx
// World-class global macro dashboard.
// Regime-first. Heat-mapped. AI-powered analysis via Global Macro Engine prompt.
// Competes with Koyfin / Bloomberg Markets.

import { useState, useEffect, useCallback } from "react"

// ── Types ────────────────────────────────────────────────────────────────────
interface Asset { label:string; region:string; flag:string; symbol:string; price:number; change:number; changePct:number }
interface IndiaData {
  nifty:number|null; niftyChg:number|null; bankNifty:number|null; bankNiftyChg:number|null;
  vix:number|null; pcr:number|null; fii:number|null; dii:number|null;
  regime:string|null; riskScore:number|null; oppScore:number|null;
  vs200dma:number|null; sectors:Record<string,number>; source:string; snapshotAge:number|null;
}

// ── Heat-map color engine ────────────────────────────────────────────────────
function heat(pct: number | null | undefined): { bg:string; text:string; border:string } {
  if (pct == null || isNaN(pct)) return { bg:"#F9FAFB", text:"#9CA3AF", border:"#E5E7EB" }
  if (pct >  2)   return { bg:"#15803d", text:"#fff",    border:"#15803d" }
  if (pct >  1)   return { bg:"#16a34a", text:"#fff",    border:"#16a34a" }
  if (pct >  0.3) return { bg:"#dcfce7", text:"#15803d", border:"#bbf7d0" }
  if (pct > -0.3) return { bg:"#f9fafb", text:"#374151", border:"#e5e7eb" }
  if (pct > -1)   return { bg:"#fef2f2", text:"#b91c1c", border:"#fecaca" }
  if (pct > -2)   return { bg:"#ef4444", text:"#fff",    border:"#ef4444" }
  return               { bg:"#991b1b", text:"#fff",    border:"#991b1b" }
}

// ── Regime config ────────────────────────────────────────────────────────────
function regimeCfg(r:string|null) {
  const map: Record<string,{bg:string;text:string;label:string;emoji:string}> = {
    HOT:              { bg:"#15803d", text:"#fff", label:"HOT 🔥",    emoji:"🔥" },
    NORMAL:           { bg:"#1d4ed8", text:"#fff", label:"NORMAL ✅",  emoji:"✅" },
    CAUTION:          { bg:"#b45309", text:"#fff", label:"CAUTION ⚠",  emoji:"⚠" },
    COLD:             { bg:"#b91c1c", text:"#fff", label:"COLD ❄",    emoji:"❄" },
    FROZEN:           { bg:"#4c1d95", text:"#fff", label:"FROZEN 🧊",  emoji:"🧊" },
    PANIC_OPPORTUNITY:{ bg:"#065f46", text:"#fff", label:"PANIC BUY ⚡",emoji:"⚡" },
  }
  return map[r || ""] || { bg:"#6b7280", text:"#fff", label:"—", emoji:"—" }
}

// ── Formatting helpers ───────────────────────────────────────────────────────
function fmtPrice(v:number|null, sym?:string): string {
  if (!v && v !== 0) return "—"
  if (sym === "USDINR=X") return `₹${v.toFixed(2)}`
  if (sym === "BTC-USD" || sym === "ETH-USD") return `$${v.toLocaleString("en-US",{maximumFractionDigits:0})}`
  if (v > 10000) return v.toLocaleString("en-IN",{maximumFractionDigits:0})
  if (v > 1000)  return v.toLocaleString("en-US",{maximumFractionDigits:0})
  return v.toFixed(2)
}

function fmtPct(v:number|null): string {
  if (v == null) return "—"
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`
}

function arrow(v:number|null): string {
  if (!v) return ""
  return v > 0 ? " ▲" : " ▼"
}

// ── Asset card ───────────────────────────────────────────────────────────────
function AssetCard({ asset }: { asset: Asset }) {
  const c = heat(asset.changePct)
  return (
    <div style={{
      background: c.bg, border: `1px solid ${c.border}`, borderRadius: 9,
      padding: "9px 11px", marginBottom: 6, cursor: "default",
      transition: "transform 0.1s", userSelect: "none",
    }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
        <div>
          <div style={{ fontSize: 10, color: c.text, opacity: 0.75, marginBottom: 1, display:"flex", alignItems:"center", gap: 4 }}>
            <span>{asset.flag}</span>
            <span style={{ fontWeight: 600, textTransform:"uppercase", letterSpacing:"0.04em" }}>{asset.label}</span>
          </div>
          <div style={{ fontSize: 16, fontWeight: 900, color: c.text, lineHeight: 1, fontFamily: "monospace" }}>
            {fmtPrice(asset.price, asset.symbol)}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: c.text }}>
            {fmtPct(asset.changePct)}{arrow(asset.changePct)}
          </div>
          <div style={{ fontSize: 10, color: c.text, opacity: 0.7, marginTop: 1, fontFamily: "monospace" }}>
            {asset.change >= 0 ? "+" : ""}{Number(asset.change).toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Region column ────────────────────────────────────────────────────────────
function RegionCol({ title, symbols, global }: { title:string; symbols:string[]; global:Record<string,Asset> }) {
  const COLORS: Record<string,string> = {
    "🇺🇸 UNITED STATES": "#1d4ed8", "🇯🇵 ASIA": "#dc2626",
    "🇬🇧 EUROPE": "#7c3aed", "🇮🇳 INDIA": "#d97706",
  }
  const accent = COLORS[title] || "#6b7280"
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{
        fontSize: 9, fontWeight: 800, color: accent, letterSpacing: "0.08em",
        textTransform: "uppercase", marginBottom: 8, paddingLeft: 2,
        borderBottom: `2px solid ${accent}`, paddingBottom: 4,
      }}>
        {title}
      </div>
      {symbols.map(sym => global[sym]
        ? <AssetCard key={sym} asset={global[sym]} />
        : <div key={sym} style={{ height: 52, background: "#F9FAFB", borderRadius: 9, marginBottom: 6 }} />
      )}
    </div>
  )
}

// ── India column (special) ───────────────────────────────────────────────────
function IndiaCol({ india }: { india: IndiaData }) {
  const n50c  = heat(india.niftyChg)
  const bnfc  = heat(india.bankNiftyChg)
  const rc    = regimeCfg(india.regime)
  const vixLvl = india.vix ? (india.vix > 22 ? "red" : india.vix > 16 ? "amber" : "green") : "gray"
  const vixColor = vixLvl === "red" ? "#dc2626" : vixLvl === "amber" ? "#d97706" : "#15803d"

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{
        fontSize: 9, fontWeight: 800, color: "#d97706", letterSpacing: "0.08em",
        textTransform: "uppercase", marginBottom: 8, paddingLeft: 2,
        borderBottom: "2px solid #d97706", paddingBottom: 4,
      }}>
        🇮🇳 INDIA {india.source === "zerodha_live" ? "● LIVE" : `(${india.snapshotAge}m ago)`}
      </div>

      {/* Nifty 50 */}
      <div style={{ background: n50c.bg, border:`1px solid ${n50c.border}`, borderRadius:9, padding:"9px 11px", marginBottom:6 }}>
        <div style={{ fontSize:10, fontWeight:600, color:n50c.text, opacity:0.75, marginBottom:1 }}>NIFTY 50</div>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline" }}>
          <div style={{ fontSize:18, fontWeight:900, color:n50c.text, fontFamily:"monospace" }}>
            {india.nifty?.toLocaleString("en-IN",{maximumFractionDigits:0}) || "—"}
          </div>
          <div style={{ fontSize:13, fontWeight:800, color:n50c.text }}>{fmtPct(india.niftyChg)}{arrow(india.niftyChg)}</div>
        </div>
      </div>

      {/* Bank Nifty */}
      <div style={{ background:bnfc.bg, border:`1px solid ${bnfc.border}`, borderRadius:9, padding:"9px 11px", marginBottom:6 }}>
        <div style={{ fontSize:10, fontWeight:600, color:bnfc.text, opacity:0.75, marginBottom:1 }}>BANK NIFTY</div>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline" }}>
          <div style={{ fontSize:15, fontWeight:900, color:bnfc.text, fontFamily:"monospace" }}>
            {india.bankNifty?.toLocaleString("en-IN",{maximumFractionDigits:0}) || "—"}
          </div>
          <div style={{ fontSize:13, fontWeight:800, color:bnfc.text }}>{fmtPct(india.bankNiftyChg)}{arrow(india.bankNiftyChg)}</div>
        </div>
      </div>

      {/* VIX + PCR */}
      <div style={{ display:"flex", gap:5, marginBottom:6 }}>
        <div style={{ flex:1, background:"#f9fafb", border:"1px solid #e5e7eb", borderRadius:9, padding:"8px 10px" }}>
          <div style={{ fontSize:9, color:"#9ca3af", marginBottom:2 }}>INDIA VIX</div>
          <div style={{ fontSize:16, fontWeight:900, color:vixColor }}>{Number(india.vix).toFixed(1) || "—"}</div>
        </div>
        <div style={{ flex:1, background:"#f9fafb", border:"1px solid #e5e7eb", borderRadius:9, padding:"8px 10px" }}>
          <div style={{ fontSize:9, color:"#9ca3af", marginBottom:2 }}>PCR</div>
          <div style={{ fontSize:16, fontWeight:900, color: (india.pcr||1) < 0.8 ? "#dc2626" : (india.pcr||1) > 1.2 ? "#15803d" : "#374151" }}>
            {Number(india.pcr).toFixed(2) || "—"}
          </div>
        </div>
      </div>

      {/* FII/DII */}
      <div style={{ background:"#f9fafb", border:"1px solid #e5e7eb", borderRadius:9, padding:"8px 10px", marginBottom:6 }}>
        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
          <span style={{ fontSize:10, color:"#6b7280" }}>FII</span>
          <span style={{ fontSize:11, fontWeight:700, color: (india.fii||0) >= 0 ? "#15803d" : "#dc2626", fontFamily:"monospace" }}>
            {india.fii != null ? `₹${india.fii >= 0 ? "+" : ""}${(india.fii/100).toFixed(0)}Cr` : "—"}
          </span>
        </div>
        <div style={{ display:"flex", justifyContent:"space-between" }}>
          <span style={{ fontSize:10, color:"#6b7280" }}>DII</span>
          <span style={{ fontSize:11, fontWeight:700, color: (india.dii||0) >= 0 ? "#15803d" : "#dc2626", fontFamily:"monospace" }}>
            {india.dii != null ? `₹${india.dii >= 0 ? "+" : ""}${(india.dii/100).toFixed(0)}Cr` : "—"}
          </span>
        </div>
      </div>

      {/* 200 DMA */}
      {india.vs200dma != null && (
        <div style={{ background:"#f9fafb", border:"1px solid #e5e7eb", borderRadius:9, padding:"7px 10px" }}>
          <div style={{ fontSize:9, color:"#9ca3af", marginBottom:1 }}>vs 200 DMA</div>
          <div style={{ fontSize:13, fontWeight:800, color: india.vs200dma >= 0 ? "#15803d" : "#dc2626" }}>
            {india.vs200dma >= 0 ? "+" : ""}{Number(india.vs200dma).toFixed(1)}%
          </div>
        </div>
      )}
    </div>
  )
}

// ── Bottom strip: Commodities, Crypto, FX ────────────────────────────────────
function BottomStrip({ global }: { global: Record<string,Asset> }) {
  const groups = [
    { title:"COMMODITIES", symbols:["GC=F","SI=F","CL=F","NG=F","HG=F"] },
    { title:"CRYPTO",      symbols:["BTC-USD","ETH-USD"] },
    { title:"FX",          symbols:["DX-Y.NYB","USDINR=X"] },
  ]
  return (
    <div style={{ display:"flex", gap:10, flexWrap:"wrap", marginTop:10 }}>
      {groups.map(g => (
        <div key={g.title} style={{ flex:"1 1 200px", background:"#fff", border:"1px solid #e5e7eb", borderRadius:10, padding:"10px 12px" }}>
          <div style={{ fontSize:9, fontWeight:800, color:"#9ca3af", letterSpacing:"0.08em", textTransform:"uppercase", marginBottom:8 }}>
            {g.title}
          </div>
          {g.symbols.map(sym => {
            const a = global[sym]
            if (!a) return null
            const c = heat(a.changePct)
            return (
              <div key={sym} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:5 }}>
                <div style={{ display:"flex", gap:5, alignItems:"center" }}>
                  <span style={{ fontSize:12 }}>{a.flag}</span>
                  <span style={{ fontSize:11, fontWeight:600, color:"#374151" }}>{a.label}</span>
                </div>
                <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                  <span style={{ fontSize:11, color:"#6b7280", fontFamily:"monospace" }}>{fmtPrice(a.price, sym)}</span>
                  <div style={{ background:c.bg, border:`1px solid ${c.border}`, borderRadius:5, padding:"1px 6px" }}>
                    <span style={{ fontSize:10, fontWeight:700, color:c.text }}>{fmtPct(a.changePct)}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// ── Sector bar ───────────────────────────────────────────────────────────────
function SectorBar({ sectors }: { sectors: Record<string,number> }) {
  const entries = Object.entries(sectors).sort((a,b) => b[1] - a[1])
  if (!entries.length) return null
  return (
    <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:10, padding:"10px 12px", marginTop:10 }}>
      <div style={{ fontSize:9, fontWeight:800, color:"#9ca3af", letterSpacing:"0.08em", marginBottom:8 }}>SECTOR PERFORMANCE</div>
      <div style={{ display:"flex", gap:5, flexWrap:"wrap" }}>
        {entries.map(([s, v]) => {
          const c = heat(v)
          return (
            <div key={s} style={{ background:c.bg, border:`1px solid ${c.border}`, borderRadius:6, padding:"3px 8px" }}>
              <span style={{ fontSize:10, fontWeight:600, color:c.text }}>{s} {fmtPct(v)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Global Macro Engine prompt builder ───────────────────────────────────────
function buildMacroPrompt(global: Record<string,Asset>, india: IndiaData, composite: any): string {
  const fmt = (sym: string) => {
    const a = global[sym]
    return a ? `${a.label}: ${fmtPrice(a.price, sym)} (${fmtPct(a.changePct)})` : `${sym}: N/A`
  }
  return `You are AACapital's Global Macro Engine.

Analyze the following live market data and determine the current market regime.

GLOBAL INDICES:
US:
${fmt("^GSPC")}
${fmt("^NDX")}
${fmt("^DJI")}
${fmt("^RUT")}

ASIA:
${fmt("^N225")}
${fmt("^HSI")}
${fmt("000001.SS")}
${fmt("^KS11")}

EUROPE:
${fmt("^FTSE")}
${fmt("^GDAXI")}
${fmt("^FCHI")}

INDIA:
Nifty 50: ${india.nifty?.toLocaleString("en-IN") || "N/A"} (${fmtPct(india.niftyChg)})
Bank Nifty: ${india.bankNifty?.toLocaleString("en-IN") || "N/A"} (${fmtPct(india.bankNiftyChg)})
India VIX: ${india.vix || "N/A"}
PCR: ${india.pcr || "N/A"}
vs 200 DMA: ${india.vs200dma != null ? india.vs200dma + "%" : "N/A"}
FII Flow: ${india.fii != null ? "₹" + india.fii + " Cr" : "N/A"}
DII Flow: ${india.dii != null ? "₹" + india.dii + " Cr" : "N/A"}

CURRENCIES:
${fmt("DX-Y.NYB")}
${fmt("USDINR=X")}

COMMODITIES:
${fmt("GC=F")}
${fmt("SI=F")}
${fmt("CL=F")}
${fmt("NG=F")}
${fmt("HG=F")}

CRYPTO:
${fmt("BTC-USD")}
${fmt("ETH-USD")}

COMPOSITE SIGNAL: ${composite?.capitalFlow || "Mixed"}

Output:
1. Global Risk-On or Risk-Off score (0-100)
2. Liquidity Environment
3. Inflation Environment
4. Commodity Trend
5. Dollar Strength Trend
6. Strongest Regions
7. Weakest Regions
8. Capital Flow Direction
9. Sectors likely to outperform next 3-12 months
10. Sectors likely to underperform

End with:
Market Regime: HOT / NORMAL / CAUTION / COLD / FROZEN

Recommended Exposure:
Cash %
Equities %
IPO %`
}

// ── Main Component ────────────────────────────────────────────────────────────
export function GlobalMacroScreen() {
  const [data,     setData]     = useState<any>(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState("")
  const [aiText,   setAiText]   = useState("")
  const [aiLoading,setAiLoading]= useState(false)
  const [showAI,   setShowAI]   = useState(false)
  const [lastFetch,setLastFetch]= useState<Date|null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true); setError("")
    try {
      const res = await fetch("/api/market/global")
      const d   = await res.json()
      if (!d.ok) throw new Error(d.error)
      setData(d)
      setLastFetch(new Date())
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const runAI = async () => {
    if (!data) return
    setShowAI(true); setAiLoading(true); setAiText("")
    try {
      const prompt = buildMacroPrompt(data.global, data.india, data.composite)
      const res = await fetch("/api/ai/memo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          context: "global_macro_analysis",
          maxTokens: 1200,
        }),
      })
      const d = await res.json()
      setAiText(d.memo || d.analysis || d.content || "Analysis complete.")
    } catch { setAiText("Failed to run analysis. Please try again.") }
    setAiLoading(false)
  }

  const global  = data?.global  || {}
  const india   = data?.india   || {}
  const composite = data?.composite || {}
  const rc      = regimeCfg(india.regime)

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "12px 16px", fontFamily: "'DM Sans', system-ui, sans-serif" }}>

      {/* ── Regime Header Bar ───────────────────────────────────────────── */}
      <div style={{
        background: "#0f172a", borderRadius: 12, padding: "12px 18px", marginBottom: 10,
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10,
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <div>
            <div style={{ fontSize:9, color:"#475569", textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:2 }}>
              GLOBAL MACRO PULSE {loading ? "⟳" : "●"}
            </div>
            <div style={{ fontSize:11, color:"#64748b" }}>
              {lastFetch ? `Updated ${lastFetch.toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}` : "Loading…"}
              {india.source === "zerodha_live" && " · Zerodha live"}
            </div>
          </div>

          {india.regime && (
            <div style={{ background: rc.bg, borderRadius: 8, padding: "6px 14px" }}>
              <span style={{ fontSize:14, fontWeight:900, color:"#fff", letterSpacing:"0.04em" }}>{rc.label}</span>
            </div>
          )}

          {composite.capitalFlow && (
            <div style={{ background:"rgba(255,255,255,0.06)", borderRadius:7, padding:"5px 12px" }}>
              <span style={{ fontSize:11, color:"#94a3b8" }}>{composite.capitalFlow}</span>
            </div>
          )}
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          {india.riskScore != null && (
            <div style={{ textAlign:"center" }}>
              <div style={{ fontSize:9, color:"#475569", marginBottom:1 }}>RISK</div>
              <div style={{ fontSize:20, fontWeight:900, color: india.riskScore > 60 ? "#ef4444" : india.riskScore > 35 ? "#f59e0b" : "#22c55e" }}>
                {india.riskScore}
              </div>
            </div>
          )}
          <button onClick={runAI} disabled={aiLoading || loading} style={{
            padding:"7px 14px", background: aiLoading ? "#1e293b" : "#2563eb",
            border:"none", borderRadius:8, color:"#fff", fontSize:12, fontWeight:700,
            cursor: aiLoading ? "default" : "pointer",
          }}>
            {aiLoading ? "Analyzing…" : "🤖 AI Analysis"}
          </button>
          <button onClick={fetchData} disabled={loading} style={{
            padding:"7px 12px", background:"#1e293b", border:"1px solid #334155",
            borderRadius:8, color:"#94a3b8", fontSize:12, cursor:"pointer",
          }}>↻</button>
        </div>
      </div>

      {error && (
        <div style={{ background:"#fef2f2", border:"1px solid #fecaca", borderRadius:9, padding:"10px 14px", marginBottom:10, fontSize:12, color:"#b91c1c" }}>
          ⚠ {error}
        </div>
      )}

      {/* ── 4-Column Grid ───────────────────────────────────────────────── */}
      <div style={{ display:"flex", gap:10, marginBottom:0 }}>
        <RegionCol title="🇺🇸 UNITED STATES" symbols={["^GSPC","^NDX","^DJI","^RUT"]} global={global} />
        <RegionCol title="🇯🇵 ASIA"           symbols={["^N225","^HSI","000001.SS","^KS11"]} global={global} />
        <RegionCol title="🇬🇧 EUROPE"         symbols={["^FTSE","^GDAXI","^FCHI"]} global={global} />
        <IndiaCol india={india as IndiaData} />
      </div>

      {/* ── Bottom strip: Commodities | Crypto | FX ─────────────────────── */}
      <BottomStrip global={global} />

      {/* ── Sector Performance ──────────────────────────────────────────── */}
      {Object.keys(india.sectors || {}).length > 0 && (
        <SectorBar sectors={india.sectors} />
      )}

      {/* ── AI Analysis Panel ───────────────────────────────────────────── */}
      {showAI && (
        <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:16, marginTop:10 }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
            <div style={{ fontSize:13, fontWeight:700, color:"#111827" }}>🤖 Global Macro Engine Analysis</div>
            <button onClick={() => setShowAI(false)} style={{ background:"none", border:"none", color:"#9ca3af", cursor:"pointer", fontSize:18 }}>×</button>
          </div>
          {aiLoading ? (
            <div style={{ display:"flex", alignItems:"center", gap:10, color:"#6b7280", fontSize:13 }}>
              <div style={{ width:14, height:14, border:"2px solid #e5e7eb", borderTopColor:"#2563eb", borderRadius:"50%", animation:"spin .7s linear infinite" }} />
              Analyzing 20 global assets…
            </div>
          ) : (
            <div style={{ fontSize:12, color:"#374151", lineHeight:1.8, whiteSpace:"pre-wrap" }}>{aiText}</div>
          )}
        </div>
      )}

      {/* ── Refresh hint ─────────────────────────────────────────────────── */}
      <div style={{ marginTop:10, fontSize:10, color:"#9ca3af", textAlign:"center" }}>
        Global indices via Yahoo Finance · India data via Zerodha (live) · Click ↻ to refresh
      </div>
    </div>
  )
}

