"use client"

import React, { useCallback, useEffect, useState } from "react"
import { Activity, Award, BarChart2, ChevronRight, Flame, Globe, RefreshCw } from "lucide-react"

type Regime = "HOT" | "NORMAL" | "CAUTION" | "COLD" | "FROZEN"
type Action = "BUY" | "WATCH" | "HOLD" | "APPLY" | "SKIP" | "ACCUMULATE" | "AVOID" | "TRIM"

interface MarketTile { label: string; value: string; change?: number | null; note?: string }
interface Opportunity { symbol: string; name?: string; score: number; action: Action; reasons?: string[] }
interface IpoRow { name: string; score?: number; recommendation?: string }
interface SectorRow { name: string; performance?: number; score?: number; signal?: string }
interface GlobalRow { label: string; value?: string; change?: number | null }

const nf = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 })
const n2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 })

const num = (v: unknown, fallback = 0) => { const x = Number(v); return Number.isFinite(x) ? x : fallback }
const hasValue = (v: unknown) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v))
const fmtNumber = (v: unknown, decimals = 2) => hasValue(v) ? (decimals === 0 ? nf.format(num(v)) : n2.format(num(v))) : "—"
const signed = (v?: number | null, suffix = "%") => typeof v === "number" && Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${n2.format(v)}${suffix}` : "—"
const moneyCr = (v: unknown) => hasValue(v) ? `${num(v) >= 0 ? "+" : ""}${nf.format(num(v))} Cr` : "—"
const pickFirst = (...values: unknown[]) => values.find(hasValue)

const normalizeRegime = (r: unknown): Regime => {
  const x = String(r || "").toUpperCase()
  if (x === "BULLISH" || x === "HOT" || x === "RISK_ON") return "HOT"
  if (x === "BEARISH" || x === "CAUTION" || x === "DEFENSIVE") return "CAUTION"
  if (x === "COLD") return "COLD"
  if (x === "FROZEN" || x === "RISK_OFF") return "FROZEN"
  return "NORMAL"
}

const REGIME: Record<Regime, { title: string; advice: string; tone: string; deploy: string; pct: number; border: string; text: string; glow: string; bar: string }> = {
  HOT:     { title:"HOT",     advice:"Risk ON. Aggressively deploy capital into top-ranked sectors.", tone:"Aggressive deployment", deploy:"75–95%", pct:92, border:"border-emerald-200", text:"text-emerald-600", glow:"from-emerald-50", bar:"bg-emerald-500" },
  NORMAL:  { title:"NORMAL",  advice:"Deploy selectively. Focus only on high-conviction names.",     tone:"Selective deployment",  deploy:"50–70%", pct:72, border:"border-emerald-100", text:"text-emerald-600", glow:"from-emerald-50", bar:"bg-emerald-500" },
  CAUTION: { title:"CAUTION", advice:"Protect capital. Avoid fresh leveraged positions.",             tone:"Defensive selection",   deploy:"25–45%", pct:42, border:"border-amber-200",   text:"text-amber-600",   glow:"from-amber-50",   bar:"bg-amber-500"   },
  COLD:    { title:"COLD",    advice:"Preserve capital. Wait for breadth and liquidity to improve.", tone:"Low deployment",         deploy:"10–30%", pct:24, border:"border-blue-200",    text:"text-blue-600",    glow:"from-blue-50",    bar:"bg-blue-500"    },
  FROZEN:  { title:"FROZEN",  advice:"Risk OFF. Hold cash and avoid new positions.",                 tone:"Cash protocol",          deploy:"0–15%",  pct:8,  border:"border-rose-200",    text:"text-rose-600",    glow:"from-rose-50",    bar:"bg-rose-500"    },
}

// Operator suppression list
const SUPPRESS = /^(ANTELOP|ACUTAAS|BMWVENTURE)/i

function Spark({ positive = true }: { positive?: boolean }) {
  const bars = positive ? [24, 38, 31, 54, 48, 68, 82] : [80, 62, 70, 50, 42, 35, 28]
  return <div className="flex h-7 w-16 items-end gap-0.5 opacity-80">
    {bars.map((h, i) => <span key={i} style={{ height: `${h}%` }} className={positive ? "w-full rounded-t bg-teal-400" : "w-full rounded-t bg-rose-400"} />)}
  </div>
}

function Skeleton({ className = "h-20" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl border border-slate-100 bg-slate-50 ${className}`} />
}

function Section({ title, meta, icon, children }: { title: string; meta?: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2.5">
      <h2 className="flex items-center gap-2 text-[12px] font-black uppercase tracking-[0.1em] text-slate-900">{icon}{title}</h2>
      {meta && <span className="font-mono text-[10px] text-slate-400">{meta}</span>}
    </div>
    {children}
  </section>
}

function ActionPill({ action }: { action: Action }) {
  const a = String(action).toUpperCase()
  const cls = a === "BUY" || a === "APPLY" || a === "ACCUMULATE"
    ? "border-emerald-300 bg-emerald-50 text-emerald-700"
    : a === "SKIP" || a === "AVOID" || a === "TRIM"
    ? "border-rose-300 bg-rose-50 text-rose-700"
    : "border-amber-300 bg-amber-50 text-amber-700"
  return <span className={`min-w-[64px] rounded-full border px-3 py-1 text-center font-mono text-[10px] font-black tracking-wider ${cls}`}>{a}</span>
}

function getGlobalRow(source: any, keys: string[], label: string): GlobalRow {
  for (const key of keys) {
    const row = source?.[key]
    if (!row) continue
    const price = pickFirst(row.price, row.value, row.regularMarketPrice)
    const change = pickFirst(row.changePct, row.change_percent, row.regularMarketChangePercent, row.change)
    return { label, value: hasValue(price) ? n2.format(num(price)) : "—", change: hasValue(change) ? num(change) : null }
  }
  return { label, value: "—", change: null }
}

export function TodayScreen({ onStockSelect }: { simple?: boolean; onStockSelect?: (s: string) => void; commandCenter?: React.ReactNode }) {
  const [loading, setLoading]       = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [regime, setRegime]         = useState<Regime>("NORMAL")
  const [market, setMarket]         = useState<MarketTile[]>([])
  const [globalRows, setGlobalRows] = useState<GlobalRow[]>([])
  const [opps, setOpps]             = useState<Opportunity[]>([])
  const [ipos, setIpos]             = useState<IpoRow[]>([])
  const [sectors, setSectors]       = useState<SectorRow[]>([])
  const [brokerOk, setBrokerOk]     = useState<boolean | null>(null)
  const [updatedAt, setUpdatedAt]   = useState<string>("")
  const [day, setDay]               = useState("")

  const load = useCallback(async (quiet = false) => {
    quiet ? setRefreshing(true) : setLoading(true)
    try {
      const [globalR, snapR, techR, sectorR, ipoR, brokerR] = await Promise.all([
        fetch("/api/market/global",                              { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/market/snapshot",                            { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/technical/screener?timeframe=daily&limit=20",{ cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/sector-rotation?view=hot",                   { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/ipo/intelligence?limit=5",                   { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/broker/status",                              { cache: "no-store" }).then(r => r.json()).catch(() => null),
      ])

      // ── India market data ──────────────────────────────────────────────────
      const snapshot = snapR?.data ?? {}
      const indiaRaw = globalR?.india ?? {}
      const india = {
        // Nifty - from Kite via global route (india.nifty) or snapshot (nifty_price)
        nifty:        pickFirst(indiaRaw.nifty, indiaRaw.nifty_price, snapshot.nifty_price, snapshot.nifty_close),
        niftyChg:     pickFirst(indiaRaw.niftyChg, indiaRaw.nifty_change_pct, snapshot.nifty_change_pct),
        bankNifty:    pickFirst(indiaRaw.bankNifty, indiaRaw.banknifty_price, snapshot.banknifty_price),
        bankNiftyChg: pickFirst(indiaRaw.bankNiftyChg, indiaRaw.banknifty_change_pct, snapshot.banknifty_change_pct),
        // VIX - from Kite via global route or snapshot
        vix:          pickFirst(indiaRaw.vix, indiaRaw.india_vix, snapshot.vix, snapshot.india_vix),
        pcr:          pickFirst(indiaRaw.pcr, snapshot.pcr, snapshot.nifty_pcr),
        // FII/DII - snapshot reads daily_institutional_flows
        fii:          pickFirst(indiaRaw.fii, indiaRaw.fii_flow, snapshot.fii_flow, snapshot.fii_net),
        dii:          pickFirst(indiaRaw.dii, indiaRaw.dii_flow, snapshot.dii_flow, snapshot.dii_net),
        // Regime
        regime:       pickFirst(indiaRaw.regime, snapshot.regime, snapshot.market_regime, "NORMAL"),
        deployMin:    pickFirst(snapshot.deploy_min, indiaRaw.deployMin, 50),
        deployMax:    pickFirst(snapshot.deploy_max, indiaRaw.deployMax, 70),
      }

      setRegime(normalizeRegime(india.regime))

      setMarket([
        { label:"NIFTY",      value:fmtNumber(india.nifty, 0),     change:hasValue(india.niftyChg)     ? num(india.niftyChg)     : null },
        { label:"BANK NIFTY", value:fmtNumber(india.bankNifty, 0), change:hasValue(india.bankNiftyChg) ? num(india.bankNiftyChg) : null },
        { label:"VIX",        value:fmtNumber(india.vix, 2),        change:null, note:hasValue(india.vix) ? (num(india.vix) < 14 ? "LOW VOL" : num(india.vix) > 18 ? "HIGH VOL" : "NORMAL") : "Pending" },
        { label:"FII",        value:moneyCr(india.fii),              note:"Cash flow" },
        { label:"DII",        value:moneyCr(india.dii),              note:"Cash flow" },
        { label:"PCR",        value:fmtNumber(india.pcr, 2),         note:hasValue(india.pcr) ? (num(india.pcr) >= 1.1 ? "BULLISH" : num(india.pcr) <= 0.8 ? "CAUTION" : "NEUTRAL") : "Pending" },
      ])

      // ── Global markets ────────────────────────────────────────────────────
      const g = globalR?.global ?? {}
      setGlobalRows([
        { label:"GIFT NIFTY", value:fmtNumber(pickFirst(india.nifty), 2), change:hasValue(india.niftyChg) ? num(india.niftyChg) : null },
        getGlobalRow(g, ["^NDX"],       "NASDAQ"),
        getGlobalRow(g, ["^GSPC"],      "S&P 500"),
        getGlobalRow(g, ["DX-Y.NYB"],   "DXY"),
        getGlobalRow(g, ["GC=F"],       "GOLD"),
        getGlobalRow(g, ["BTC-USD"],    "BTC"),
      ])

      // ── Top Convergence — operator suppressed ─────────────────────────────
      const techData = (techR?.data ?? []) as any[]
      const filtered = techData.filter((x: any) => {
        const sym  = String(x.symbol ?? x.nse_symbol ?? "")
        const mcap = num(x.market_cap ?? 0)
        if (SUPPRESS.test(sym)) return false
        if (mcap > 0 && mcap < 500) return false
        return true
      })
      setOpps(filtered.slice(0, 5).map((x: any) => {
        const score = Math.round(num(x.buy_zone_score ?? x.probability_score ?? x.convergence_score ?? 55))
        const action: Action = score >= 75 || x.volume_expansion || x.nr7 ? "BUY" : score >= 55 ? "WATCH" : "HOLD"
        return {
          symbol:  x.symbol ?? x.nse_symbol,
          name:    x.company_name ?? x.name,
          score,
          action,
          reasons: [x.nr7 ? "NR7 compression" : "Technical signal", x.volume_expansion ? "Volume expansion" : "Watch volume"],
        }
      }))

      // ── Sectors ───────────────────────────────────────────────────────────
      const hot = (sectorR?.hot_sectors ?? sectorR?.sectors ?? []) as any[]
      setSectors(hot.slice(0, 6).map((s: any) => ({
        name:        s.industry_group ?? s.name ?? s.sector,
        performance: num(s.return_3m ?? s.return_6m),
        score:       Math.round(num(s.rotation_score ?? s.score)),
        signal:      s.rotation_signal,
      })))

      // ── IPOs ──────────────────────────────────────────────────────────────
      const ipoList = (ipoR?.ipos ?? ipoR?.data ?? []) as any[]
      setIpos(ipoList.slice(0, 5).map((i: any) => {
        const lqi = num(i.lqi ?? i.conviction_score ?? i.score?.listingScore ?? 0)
        const rec = lqi >= 75 ? "APPLY" : lqi >= 50 ? "WATCH" : "SKIP"
        return { name: i.company_name ?? i.name ?? i.ipo_name, recommendation: rec, score: Math.round(lqi) || undefined }
      }))

      setBrokerOk(typeof brokerR?.connected === "boolean" ? brokerR.connected : null)
      setUpdatedAt(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit" }))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    setDay(new Date().toLocaleString("en-IN", { weekday:"long", day:"numeric", month:"short", hour:"2-digit", minute:"2-digit", timeZone:"Asia/Kolkata" }))
  }, [])

  const rc = REGIME[regime]
  const topSectors = sectors.slice(0, 3).map(s => s.name).filter(Boolean)

  return (
    <div className="min-h-screen bg-[#F7F9FC] text-slate-900 overflow-x-hidden">
      <main className="mx-auto max-w-[1680px] space-y-4 px-4 py-4">

        {/* Date + refresh row */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-[22px] font-black tracking-tight text-slate-950">Today's Market Brief</h1>
            <p className="mt-0.5 font-mono text-[11px] text-slate-500">
              {day || "Loading..."} IST{updatedAt ? ` · Updated ${updatedAt}` : ""}
            </p>
          </div>
          <button onClick={() => load(true)} className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[12px] font-bold text-slate-700 shadow-sm hover:bg-slate-50">
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {/* Main 2-col grid */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_380px]">

          {/* ── LEFT COLUMN ─────────────────────────────────────────────── */}
          <div className="space-y-4 min-w-0">

            {/* SECTION 1: REGIME HERO */}
            {loading ? <Skeleton className="h-44" /> : (
              <section className={`relative overflow-hidden rounded-2xl border ${rc.border} bg-white p-6 shadow-sm`}>
                <div className={`pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-gradient-to-l ${rc.glow} to-transparent`} />
                <div className="relative flex items-start justify-between gap-6">
                  <div className="flex-1">
                    <div className="mb-1 text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">System Macro Regime</div>
                    <div className={`text-[46px] font-black leading-none tracking-tight ${rc.text}`}>{rc.title}</div>
                    <p className="mt-2 text-[15px] font-bold text-slate-900">{rc.advice}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                      {topSectors.length > 0
                        ? topSectors.map((s, i) => <React.Fragment key={s}><span className="text-[12px] font-semibold text-slate-600">{s}</span>{i < topSectors.length - 1 && <span className="text-slate-300">·</span>}</React.Fragment>)
                        : <span className="text-[12px] text-slate-400">Sector rotation import pending</span>}
                    </div>
                  </div>
                  <div className="min-w-[180px] text-right">
                    <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">Deployment</div>
                    <div className={`mt-1 text-[36px] font-black ${rc.text}`}>{rc.deploy}</div>
                    <div className="mt-2 h-2 rounded-full bg-slate-100">
                      <div style={{ width:`${rc.pct}%` }} className={`h-full rounded-full ${rc.bar}`} />
                    </div>
                    <div className="mt-2 text-[11px] font-medium text-slate-500">{rc.tone}</div>
                  </div>
                </div>
              </section>
            )}

            {/* SECTIONS 2+3: TOP CONVERGENCE + IPO DNA side by side */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">

              {/* TOP CONVERGENCE */}
              <Section title="Top Convergence" meta="Technical Signals" icon={<Flame className="h-4 w-4 text-orange-500" />}>
                {loading ? <Skeleton className="h-36" /> : opps.length > 0
                  ? <div className="space-y-1">
                      {opps.map(o => (
                        <button key={o.symbol} onClick={() => onStockSelect?.(o.symbol)}
                          className="group flex w-full items-center justify-between rounded-xl px-2 py-2.5 text-left hover:bg-slate-50 border border-transparent hover:border-slate-100">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-[13px] font-black text-slate-950 group-hover:text-teal-600">{o.symbol}</span>
                              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-500">Score {o.score}</span>
                            </div>
                            <div className="truncate text-[11px] text-slate-400">{o.reasons?.slice(0,2).join(" · ")}</div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Spark positive={o.action !== "AVOID"} />
                            <ActionPill action={o.action} />
                            <ChevronRight className="h-4 w-4 text-slate-300" />
                          </div>
                        </button>
                      ))}
                    </div>
                  : <div className="rounded-xl bg-slate-50 p-5 text-center text-[12px] text-slate-400">No technical signals yet.</div>
                }
              </Section>

              {/* IPO DNA */}
              <Section title="IPO DNA" meta="Primary Market" icon={<Award className="h-4 w-4 text-cyan-500" />}>
                {loading ? <Skeleton className="h-36" /> : ipos.length > 0
                  ? <div className="space-y-1">
                      {ipos.map(i => {
                        const rec = String(i.recommendation ?? "WATCH").toUpperCase()
                        const action: Action = rec.includes("APPLY") ? "APPLY" : rec.includes("SKIP") || rec.includes("AVOID") ? "SKIP" : "WATCH"
                        return (
                          <div key={i.name} className="flex items-center justify-between rounded-xl px-2 py-2.5 hover:bg-slate-50">
                            <div className="min-w-0">
                              <div className="truncate text-[13px] font-black text-slate-950">{i.name}</div>
                              <div className="font-mono text-[11px] text-slate-400">Conviction {i.score != null ? Math.round(num(i.score)) : "—"}</div>
                            </div>
                            <ActionPill action={action} />
                          </div>
                        )
                      })}
                    </div>
                  : <div className="rounded-xl bg-slate-50 p-5 text-center text-[12px] text-slate-400">No open IPOs.</div>
                }
              </Section>
            </div>

            {/* SECTION 4: SECTOR LEADERSHIP */}
            <Section title="Sector Leadership" meta="Rotation Engine" icon={<BarChart2 className="h-4 w-4 text-blue-500" />}>
              {loading ? <Skeleton className="h-28" /> : sectors.length > 0
                ? <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    {sectors.map(s => (
                      <div key={s.name} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                        <div className="min-w-0">
                          <div className="truncate text-[13px] font-black text-slate-950">{s.name}</div>
                          <div className="text-[11px] text-slate-400">{s.signal ?? "Rotate In"}</div>
                        </div>
                        <div className="flex items-center gap-3 font-mono">
                          <span className={num(s.performance) >= 0 ? "text-[12px] font-black text-emerald-600" : "text-[12px] font-black text-rose-600"}>
                            {signed(s.performance)}
                          </span>
                          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-black text-blue-700">{s.score ?? "—"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                : <div className="rounded-xl bg-slate-50 p-4 text-center text-[12px] text-slate-400">Sector rotation data pending.</div>
              }
            </Section>

          </div>

          {/* ── RIGHT COLUMN ────────────────────────────────────────────── */}
          <div className="space-y-4 min-w-0">

            {/* DOMESTIC MARKET */}
            <Section title="Domestic Market" meta={brokerOk ? "Live / Cache" : "Cache"} icon={<Activity className="h-4 w-4 text-cyan-500" />}>
              {loading ? <Skeleton className="h-72" /> : (
                <div className="space-y-2">
                  {/* NIFTY — full width large */}
                  {market[0] && (
                    <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <div>
                        <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">{market[0].label}</div>
                        <div className="mt-0.5 font-mono text-[24px] font-black text-slate-950">{market[0].value}</div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className={(market[0].change ?? 0) >= 0 ? "font-mono text-[12px] font-black text-emerald-600" : "font-mono text-[12px] font-black text-rose-600"}>
                          {signed(market[0].change)}
                        </span>
                        <Spark positive={(market[0].change ?? 0) >= 0} />
                      </div>
                    </div>
                  )}
                  {/* BANK NIFTY — full width large */}
                  {market[1] && (
                    <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <div>
                        <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">{market[1].label}</div>
                        <div className="mt-0.5 font-mono text-[24px] font-black text-slate-950">{market[1].value}</div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className={(market[1].change ?? 0) >= 0 ? "font-mono text-[12px] font-black text-emerald-600" : "font-mono text-[12px] font-black text-rose-600"}>
                          {signed(market[1].change)}
                        </span>
                        <Spark positive={(market[1].change ?? 0) >= 0} />
                      </div>
                    </div>
                  )}
                  {/* VIX, FII, DII, PCR — 2x2 grid */}
                  <div className="grid grid-cols-2 gap-2">
                    {market.slice(2).map(m => (
                      <div key={m.label} className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                        <div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">{m.label}</div>
                        <div className={`mt-0.5 font-mono text-[17px] font-black ${
                          m.label === "FII" || m.label === "DII"
                            ? (m.value.startsWith("+") ? "text-emerald-600" : m.value.startsWith("-") ? "text-rose-600" : "text-slate-950")
                            : "text-slate-950"
                        }`}>{m.value}</div>
                        {m.note && (
                          <div className={`mt-0.5 text-[10px] font-bold ${
                            m.note === "BULLISH" ? "text-emerald-600"
                            : m.note === "CAUTION" ? "text-amber-600"
                            : m.note === "HIGH VOL" ? "text-rose-600"
                            : "text-slate-400"
                          }`}>{m.note}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Section>

            {/* GLOBAL MARKETS */}
            <Section title="Global Markets" meta="Macro Overlay" icon={<Globe className="h-4 w-4 text-blue-500" />}>
              {loading ? <Skeleton className="h-48" /> : (
                <div className="space-y-1">
                  {globalRows.map(g => (
                    <div key={g.label} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 font-mono">
                      <span className="font-sans text-[12px] font-bold text-slate-700">{g.label}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-[12px] font-black text-slate-950">{g.value ?? "—"}</span>
                        <span className={`min-w-[54px] text-right text-[11px] font-black ${(g.change ?? 0) >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                          {signed(g.change)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>

          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 rounded-xl border border-slate-100 bg-white px-4 py-2.5 text-[11px] text-slate-400">
          <span className="text-blue-400">ℹ</span>
          All data is real-time or cached as per source availability. Not financial advice.
        </div>

      </main>
    </div>
  )
}
