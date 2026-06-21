"use client"

import React, { useCallback, useEffect, useMemo, useState } from "react"
import { Activity, Award, BarChart2, ChevronRight, Flame, Globe, RefreshCw } from "lucide-react"

type Regime = "HOT" | "NORMAL" | "CAUTION" | "COLD" | "FROZEN"
type Action = "BUY" | "WATCH" | "HOLD" | "APPLY" | "SKIP" | "ACCUMULATE" | "AVOID" | "TRIM"

interface Opportunity { symbol: string; name?: string; score: number; action: Action; reasons?: string[] }
interface IpoRow { name: string; score?: number; recommendation?: string }
interface SectorRow { name: string; performance?: number; score?: number; signal?: string }
interface GlobalRow { label: string; value?: string; change?: number | null }

const nf  = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 })
const n2  = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 })
const num = (v: unknown, fb = 0) => { const x = Number(v); return Number.isFinite(x) ? x : fb }
const has = (v: unknown) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v))
const fmt = (v: unknown, d = 2) => has(v) ? (d === 0 ? nf.format(num(v)) : n2.format(num(v))) : "—"
const sgn = (v?: number | null, s = "%") => has(v) ? `${num(v) >= 0 ? "+" : ""}${n2.format(num(v))}${s}` : "—"
const cr  = (v: unknown) => has(v) ? `${num(v) >= 0 ? "+" : ""}${nf.format(num(v))} Cr` : "—"
const first = (...vals: unknown[]) => vals.find(has)

const REGIME: Record<Regime, { title: string; advice: string; tone: string; deploy: string; pct: number; border: string; text: string; glow: string; bar: string }> = {
  HOT:     { title:"HOT",     advice:"Risk ON. Aggressively deploy capital into top-ranked sectors.", tone:"Aggressive deployment", deploy:"75–95%", pct:92, border:"border-emerald-200", text:"text-emerald-600", glow:"from-emerald-50",  bar:"bg-emerald-500" },
  NORMAL:  { title:"NORMAL",  advice:"Deploy selectively. Focus only on high-conviction names.",     tone:"Selective deployment",  deploy:"50–70%", pct:72, border:"border-slate-200",   text:"text-teal-600",   glow:"from-teal-50",    bar:"bg-teal-500"    },
  CAUTION: { title:"CAUTION", advice:"Protect capital. Avoid fresh leveraged positions.",             tone:"Defensive selection",   deploy:"25–45%", pct:42, border:"border-amber-200",  text:"text-amber-600",  glow:"from-amber-50",   bar:"bg-amber-500"   },
  COLD:    { title:"COLD",    advice:"Preserve capital. Wait for breadth and liquidity to improve.", tone:"Low deployment",         deploy:"10–30%", pct:24, border:"border-blue-200",   text:"text-blue-600",   glow:"from-blue-50",    bar:"bg-blue-500"    },
  FROZEN:  { title:"FROZEN",  advice:"Risk OFF. Hold cash and avoid new positions.",                 tone:"Cash protocol",          deploy:"0–15%",  pct:8,  border:"border-rose-200",   text:"text-rose-600",   glow:"from-rose-50",    bar:"bg-rose-500"    },
}

function Spark({ positive = true }: { positive?: boolean }) {
  const bars = positive ? [24,38,31,54,48,68,82] : [80,62,70,50,42,35,28]
  return <div className="flex h-7 w-16 items-end gap-0.5">{bars.map((h,i) => <span key={i} style={{height:`${h}%`}} className={positive ? "w-full rounded-t bg-emerald-400" : "w-full rounded-t bg-rose-400"} />)}</div>
}

function Skeleton({ className="h-20" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl border border-slate-100 bg-slate-50 ${className}`} />
}

function Card({ title, meta, icon, children }: { title:string; meta?:string; icon?:React.ReactNode; children:React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2.5">
        <h2 className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.1em] text-slate-800">{icon}{title}</h2>
        {meta && <span className="font-mono text-[10px] text-slate-400">{meta}</span>}
      </div>
      {children}
    </section>
  )
}

function ActionPill({ action }: { action: Action }) {
  const a = String(action).toUpperCase()
  const cls =
    a === "BUY"  || a === "APPLY" || a === "ACCUMULATE" ? "border-emerald-300 bg-emerald-50  text-emerald-700" :
    a === "SKIP" || a === "AVOID" || a === "TRIM"        ? "border-rose-300   bg-rose-50    text-rose-700"    :
                                                           "border-amber-300  bg-amber-50   text-amber-700"
  return <span className={`inline-block min-w-[56px] rounded-full border px-3 py-0.5 text-center font-mono text-[10px] font-bold tracking-wider ${cls}`}>{a}</span>
}

export function TodayScreen({ onStockSelect }: { simple?: boolean; onStockSelect?: (s: string) => void; commandCenter?: React.ReactNode }) {
  const [loading,   setLoading]   = useState(true)
  const [refreshing,setRefreshing]= useState(false)
  const [regime,    setRegime]    = useState<Regime>("NORMAL")
  const [nifty,     setNifty]     = useState<{val:string;chg:number|null}>({val:"—",chg:null})
  const [bankNifty, setBankNifty] = useState<{val:string;chg:number|null}>({val:"—",chg:null})
  const [vix,       setVix]       = useState<{val:string;note:string}>({val:"—",note:""})
  const [fii,       setFii]       = useState("—")
  const [dii,       setDii]       = useState("—")
  const [pcr,       setPcr]       = useState<{val:string;note:string}>({val:"—",note:""})
  const [globalRows,setGlobalRows]= useState<GlobalRow[]>([])
  const [opps,      setOpps]      = useState<Opportunity[]>([])
  const [ipos,      setIpos]      = useState<IpoRow[]>([])
  const [sectors,   setSectors]   = useState<SectorRow[]>([])
  const [topSectors,setTopSectors]= useState<string[]>([])
  const [updatedAt, setUpdatedAt] = useState("")
  const [brokerOk,  setBrokerOk]  = useState<boolean|null>(null)

  const load = useCallback(async (quiet=false) => {
    quiet ? setRefreshing(true) : setLoading(true)
    try {
      const [globalR, snapR, techR, sectorR, ipoR, brokerR] = await Promise.all([
        fetch("/api/market/global",                               {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/market/snapshot",                             {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/technical/screener?timeframe=daily&limit=15",  {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/sector-rotation?view=hot",                    {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/ipo/intelligence?limit=5",                    {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
        fetch("/api/broker/status",                               {cache:"no-store"}).then(r=>r.json()).catch(()=>null),
      ])

      // ── India data — merge Kite live (via global route) + Neon snapshot ──
      const g = globalR?.india ?? {}
      const s = snapR?.data   ?? {}

      const niftyVal   = first(g.nifty,     s.nifty_price)
      const bnVal      = first(g.bankNifty, s.banknifty_price)
      const vixVal     = first(g.vix,       s.vix, s.india_vix)
      const fiiVal     = first(g.fii,       s.fii_flow, s.fii_cash_flow)
      const diiVal     = first(g.dii,       s.dii_flow, s.dii_cash_flow)
      const pcrVal     = first(g.pcr,       s.pcr)
      const niftyChg   = first(g.niftyChg,    s.nifty_change_pct)   as number|null
      const bnChg      = first(g.bankNiftyChg, s.banknifty_change_pct) as number|null
      // Snapshot route reads market_regimes.active_regime first — use it as authority
      const regimeStr  = String(first(s.regime, s.market_regime, g.regime) ?? "NORMAL").toUpperCase() as Regime

      if (REGIME[regimeStr]) setRegime(regimeStr)
      setNifty    ({ val: fmt(niftyVal, 0), chg: has(niftyChg) ? num(niftyChg) : null })
      setBankNifty({ val: fmt(bnVal, 0),    chg: has(bnChg)    ? num(bnChg)    : null })
      setVix      ({ val: fmt(vixVal, 2),   note: !has(vixVal) ? "" : num(vixVal)<14 ? "LOW VOL" : num(vixVal)>18 ? "HIGH VOL" : "NORMAL" })
      setFii(cr(fiiVal))
      setDii(cr(diiVal))
      setPcr({ val: fmt(pcrVal, 2), note: !has(pcrVal) ? "" : num(pcrVal)>=1.1 ? "BULLISH" : num(pcrVal)<=0.8 ? "CAUTION" : "NEUTRAL" })

      // ── Global markets — all 20 assets from API, grouped by region ──
      const gl = globalR?.global ?? {}
      const mkGrow = (sym: string, label: string, flag: string): GlobalRow => ({
        label: `${flag} ${label}`,
        value:  gl[sym]?.price != null ? n2.format(num(gl[sym].price)) : "—",
        change: typeof gl[sym]?.changePct === "number" ? gl[sym].changePct : null,
      })
      setGlobalRows([
        // India
        { label: "🇮🇳 NIFTY",     value: fmt(niftyVal,0), change: has(niftyChg) ? num(niftyChg) : null },
        { label: "🇮🇳 BANK NIFTY", value: fmt(bnVal,0),    change: has(bnChg)    ? num(bnChg)    : null },
        // US
        mkGrow("^GSPC",    "S&P 500",    "🇺🇸"),
        mkGrow("^NDX",     "Nasdaq 100", "🇺🇸"),
        mkGrow("^DJI",     "Dow Jones",  "🇺🇸"),
        mkGrow("^RUT",     "Russell 2K", "🇺🇸"),
        // Asia
        mkGrow("^N225",    "Nikkei",     "🇯🇵"),
        mkGrow("^HSI",     "Hang Seng",  "🇭🇰"),
        mkGrow("000001.SS","Shanghai",   "🇨🇳"),
        mkGrow("^KS11",    "KOSPI",      "🇰🇷"),
        // Europe
        mkGrow("^FTSE",    "FTSE 100",   "🇬🇧"),
        mkGrow("^GDAXI",   "DAX",        "🇩🇪"),
        mkGrow("^FCHI",    "CAC 40",     "🇫🇷"),
        // FX
        mkGrow("DX-Y.NYB", "DXY",        "💵"),
        mkGrow("USDINR=X", "USD/INR",    "₹"),
        // Commodities
        mkGrow("GC=F",     "Gold",       "🥇"),
        mkGrow("SI=F",     "Silver",     "🥈"),
        mkGrow("CL=F",     "Crude Oil",  "🛢"),
        mkGrow("NG=F",     "Nat Gas",    "🔥"),
        // Crypto
        mkGrow("BTC-USD",  "Bitcoin",    "₿"),
      ].filter(r => r.value !== "—" || r.label.includes("NIFTY")))

      // ── Top convergence ──
      const SUPPRESS = /^(ANTELOP|ACUTAAS|BMWVENTURE)/i
      const tech = ((techR?.data ?? []) as any[]).filter((x:any) => !SUPPRESS.test(String(x.symbol??"")))
      setOpps(tech.slice(0,10).map((x:any) => {
        const score  = Math.round(num(x.buy_zone_score ?? x.probability_score ?? 55))
        const action: Action = score>=75 || x.volume_expansion || x.nr7 ? "BUY" : score>=55 ? "WATCH" : "HOLD"
        return { symbol:x.symbol, name:x.company_name, score, action, reasons:[x.nr7?"NR7 compression":"Technical signal", x.volume_expansion?"Volume expansion":"Watch volume"] }
      }))

      // ── Sectors ──
      const hot = (sectorR?.hot_sectors ?? sectorR?.sectors ?? []) as any[]
      const sectorList = hot.slice(0,6).map((s:any) => ({
        name: s.industry_group, performance: num(s.return_3m ?? s.return_6m),
        score: Math.round(num(s.rotation_score)), signal: s.rotation_signal,
      }))
      setSectors(sectorList)
      setTopSectors(sectorList.slice(0,3).map((s:any)=>s.name).filter(Boolean))

      // ── IPOs ──
      const ipoList = (ipoR?.ipos ?? ipoR?.data ?? []) as any[]
      setIpos(ipoList.slice(0,4).map((i:any) => {
        const lqi = num(i.lqi ?? i.score?.listingScore ?? 0)
        const rec = lqi>=75 ? "APPLY" : lqi>=50 ? "WATCH" : "SKIP"
        return { name: i.company_name ?? i.name ?? i.ipo_name, recommendation: i.score?.recommendation ?? rec, score: Math.round(lqi)||undefined }
      }))

      setBrokerOk(typeof brokerR?.connected==="boolean" ? brokerR.connected : null)
      setUpdatedAt(new Date().toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit",second:"2-digit"}))
    } finally { setLoading(false); setRefreshing(false) }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 60s during market hours (9:15AM – 3:30PM IST)
  useEffect(() => {
    const isMarketHours = () => {
      const now = new Date()
      const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }))
      const h = ist.getHours(), m = ist.getMinutes()
      const mins = h * 60 + m
      const day = ist.getDay()
      return day >= 1 && day <= 5 && mins >= 555 && mins <= 930 // 9:15 to 15:30
    }
    const interval = setInterval(() => {
      if (isMarketHours()) load(true)
    }, 60000) // every 60 seconds
    return () => clearInterval(interval)
  }, [load])

  const rc  = REGIME[regime]
  const day = useMemo(() => new Date().toLocaleString("en-IN",{weekday:"long",day:"numeric",month:"short",timeZone:"Asia/Kolkata"}), [])

  return (
    <div className="min-h-screen bg-[#F7F9FC] text-slate-900">
      <div className="mx-auto max-w-[1680px] px-5 py-4">

        {/* ── Page header ── */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h1 className="text-[22px] font-black tracking-tight text-slate-950">Today's Market Brief</h1>
            <p className="mt-0.5 font-mono text-[11px] text-slate-500">{day}, {updatedAt ? `${updatedAt} IST · Updated ${updatedAt}` : "Loading…"}</p>
          </div>
          <button onClick={()=>load(true)} className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[12px] font-semibold text-slate-600 shadow-sm hover:bg-slate-50">
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing?"animate-spin text-teal-500":"text-slate-400"}`}/> Refresh
          </button>
          <button onClick={()=>{const s=prompt("Search stock (e.g. RELIANCE)");if(s)(window as any).sendPrompt?.(`Open ${s.trim().toUpperCase()} in workspace`)}} 
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[12px] font-semibold text-slate-600 shadow-sm hover:bg-slate-50">
            🔍 Search
          </button>
        </div>

        {/* ── Main 2-col grid ── */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_380px]">

          {/* LEFT */}
          <div className="space-y-4 min-w-0">

            {/* Regime hero */}
            {loading ? <Skeleton className="h-40" /> : (
              <section className={`relative overflow-hidden rounded-2xl border ${rc.border} bg-white p-5 shadow-sm`}>
                <div className={`pointer-events-none absolute inset-y-0 right-0 w-2/5 bg-gradient-to-l ${rc.glow} to-transparent`}/>
                <div className="relative flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="mb-1 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">System Macro Regime</div>
                    <div className={`text-[44px] font-black leading-none tracking-tight ${rc.text}`}>{rc.title}</div>
                    <p className="mt-2 text-[14px] font-semibold text-slate-700">{rc.advice}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {topSectors.length
                        ? topSectors.map((s,i) => <React.Fragment key={s}><span className="text-[12px] font-medium text-slate-600">{s}</span>{i<topSectors.length-1&&<span className="text-slate-300">·</span>}</React.Fragment>)
                        : <span className="text-[12px] text-slate-400">Sector rotation import pending</span>}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">Deployment</div>
                    <div className={`text-[34px] font-black ${rc.text}`}>{rc.deploy}</div>
                    <div className="mt-2 h-2 rounded-full bg-slate-100">
                      <div style={{width:`${rc.pct}%`}} className={`h-full rounded-full ${rc.bar}`}/>
                    </div>
                    <div className="mt-1.5 text-[11px] text-slate-500">{rc.tone}</div>
                  </div>
                </div>
              </section>
            )}

            {/* Top Convergence + IPO DNA */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Card title="Top Convergence" meta="Technical Signals" icon={<Flame className="h-3.5 w-3.5 text-orange-500"/>}>
                {loading ? <Skeleton className="h-36"/> : opps.length
                  ? <div className="space-y-1 max-h-72 overflow-y-auto pr-1">{opps.map(o=>(
                      <button key={o.symbol} onClick={()=>onStockSelect?.(o.symbol)}
                        className="group flex w-full items-center justify-between rounded-xl border border-transparent px-2 py-2.5 text-left hover:border-slate-200 hover:bg-slate-50">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[13px] font-black text-slate-900 group-hover:text-teal-600">{o.symbol}</span>
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">Score {o.score}</span>
                          </div>
                          <div className="truncate text-[11px] text-slate-400">{o.reasons?.slice(0,2).join(" · ")}</div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Spark positive={o.action!=="AVOID"}/>
                          <ActionPill action={o.action}/>
                          <ChevronRight className="h-3.5 w-3.5 text-slate-300"/>
                        </div>
                      </button>
                    ))}</div>
                  : <div className="rounded-xl bg-slate-50 p-5 text-center text-[12px] text-slate-400">No technical signals yet.</div>
                }
              </Card>

              <Card title="IPO DNA" meta="Primary Market" icon={<Award className="h-3.5 w-3.5 text-teal-600"/>}>
                {loading ? <Skeleton className="h-36"/> : ipos.length
                  ? <div className="space-y-1">{ipos.map(i=>{
                      const rec = String(i.recommendation??"WATCH").toUpperCase()
                      const action: Action = rec.includes("APPLY")?"APPLY": rec.includes("SKIP")||rec.includes("AVOID")?"SKIP":"WATCH"
                      return (
                        <div key={i.name} className="flex items-center justify-between rounded-xl px-2 py-2.5 hover:bg-slate-50">
                          <div className="min-w-0">
                            <div className="truncate text-[13px] font-bold text-slate-900">{i.name}</div>
                            <div className="font-mono text-[10px] text-slate-400">Conviction {i.score!=null?Math.round(num(i.score)):"—"}</div>
                          </div>
                          <ActionPill action={action}/>
                        </div>
                      )
                    })}</div>
                  : <div className="rounded-xl bg-slate-50 p-5 text-center text-[12px] text-slate-400">No open IPOs.</div>
                }
              </Card>
            </div>

            {/* Sector Leadership */}
            <Card title="Sector Leadership" meta="Rotation Engine" icon={<BarChart2 className="h-3.5 w-3.5 text-indigo-500"/>}>
              {loading ? <Skeleton className="h-28"/> : sectors.length
                ? <div className="grid grid-cols-1 gap-2 md:grid-cols-2">{sectors.map(s=>(
                    <div key={s.name} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                      <div className="min-w-0">
                        <div className="truncate text-[12px] font-bold text-slate-900">{s.name}</div>
                        <div className="text-[10px] text-slate-400">{s.signal==="Strong Rotate In"?"Strong Rotate In": s.signal==="Rotate In"?"Rotate In": s.signal??"Strong Rotate In"}</div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0 font-mono">
                        <span className={num(s.performance)>=0?"text-[12px] font-bold text-emerald-600":"text-[12px] font-bold text-rose-600"}>{sgn(s.performance)}</span>
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-[11px] font-black text-indigo-700">{s.score??"—"}</span>
                      </div>
                    </div>
                  ))}</div>
                : <div className="rounded-xl bg-slate-50 p-4 text-center text-[12px] text-slate-400">Sector rotation data pending.</div>
              }
            </Card>
          </div>

          {/* RIGHT */}
          <div className="space-y-4">

            {/* Domestic Market */}
            <Card title="Domestic Market" meta={brokerOk ? "Live / Cache" : "Cache"} icon={<Activity className="h-3.5 w-3.5 text-teal-600"/>}>
              {loading ? <Skeleton className="h-72"/> : (
                <div className="space-y-2">
                  {/* NIFTY — large */}
                  <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">NIFTY</div>
                      <div className="font-mono text-[26px] font-black text-slate-950">{nifty.val}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={nifty.chg!=null&&nifty.chg>=0?"font-mono text-[12px] font-bold text-emerald-600":"font-mono text-[12px] font-bold text-rose-600"}>{sgn(nifty.chg)}</span>
                      <Spark positive={(nifty.chg??0)>=0}/>
                    </div>
                  </div>
                  {/* BANK NIFTY — large */}
                  <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">BANK NIFTY</div>
                      <div className="font-mono text-[26px] font-black text-slate-950">{bankNifty.val}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={bankNifty.chg!=null&&bankNifty.chg>=0?"font-mono text-[12px] font-bold text-emerald-600":"font-mono text-[12px] font-bold text-rose-600"}>{sgn(bankNifty.chg)}</span>
                      <Spark positive={(bankNifty.chg??0)>=0}/>
                    </div>
                  </div>
                  {/* VIX + FII */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                      <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">VIX</div>
                      <div className="font-mono text-[18px] font-black text-slate-950">{vix.val}</div>
                      {vix.note && <div className="text-[10px] font-bold text-slate-400">{vix.note}</div>}
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                      <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">FII</div>
                      <div className={`font-mono text-[18px] font-black ${fii.startsWith("+")?"text-emerald-600":fii.startsWith("-")?"text-rose-600":"text-slate-950"}`}>{fii}</div>
                      <div className="text-[10px] text-slate-400">Cash flow</div>
                    </div>
                  </div>
                  {/* DII + PCR */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                      <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">DII</div>
                      <div className={`font-mono text-[18px] font-black ${dii.startsWith("+")?"text-emerald-600":dii.startsWith("-")?"text-rose-600":"text-slate-950"}`}>{dii}</div>
                      <div className="text-[10px] text-slate-400">Cash flow</div>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                      <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">PCR</div>
                      <div className="font-mono text-[18px] font-black text-slate-950">{pcr.val}</div>
                      {pcr.note && <div className={`text-[10px] font-bold ${pcr.note==="BULLISH"?"text-emerald-600":pcr.note==="CAUTION"?"text-amber-600":"text-slate-400"}`}>{pcr.note}</div>}
                    </div>
                  </div>
                </div>
              )}
            </Card>

            {/* Global Markets */}
            <Card title="Global Markets" meta="20 assets · Live" icon={<Globe className="h-3.5 w-3.5 text-blue-500"/>}>
              {loading ? <Skeleton className="h-48"/> : (
                <div className="space-y-1 max-h-96 overflow-y-auto pr-1">
                  {globalRows.map(g => (
                    <div key={g.label} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                      <span className="text-[12px] font-semibold text-slate-700">{g.label}</span>
                      <div className="flex items-center gap-3 font-mono">
                        <span className="text-[12px] font-bold text-slate-900">{g.value??"—"}</span>
                        <span className={`text-[11px] font-bold ${(g.change??0)>=0?"text-emerald-600":"text-rose-600"}`}>{sgn(g.change)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

          </div>
        </div>

        {/* Footer */}
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-slate-100 bg-white px-4 py-2.5 text-[11px] text-slate-400 shadow-sm">
          <span className="text-blue-400">ℹ</span> All data is real-time or cached as per source availability. Not financial advice.
        </div>

      </div>
    </div>
  )
}
