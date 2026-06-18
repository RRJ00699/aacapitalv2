"use client"

import React, { useCallback, useEffect, useMemo, useState } from "react"
import { Activity, Award, BarChart2, ChevronRight, Flame, Globe, RefreshCw, Shield, TrendingDown, TrendingUp, Zap } from "lucide-react"

type Regime = "HOT" | "NORMAL" | "CAUTION" | "COLD" | "FROZEN"
type Action = "BUY" | "WATCH" | "HOLD" | "APPLY" | "SKIP" | "ACCUMULATE" | "AVOID" | "TRIM"

interface MarketTile { label: string; value: string; change?: number | null; note?: string }
interface Opportunity { symbol: string; name?: string; score: number; action: Action; investability?: number; operatorRisk?: string; reasons?: string[] }
interface IpoRow { name: string; score?: number; recommendation?: string }
interface SectorRow { name: string; performance?: number; score?: number; signal?: string }
interface GlobalRow { label: string; value?: string; change?: number | null; symbol?: string }

const nf = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 })
const n2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 })
const num = (v: unknown, fallback = 0) => {
  const x = Number(v)
  return Number.isFinite(x) ? x : fallback
}
const signed = (v?: number | null, suffix = "%") => typeof v === "number" ? `${v >= 0 ? "+" : ""}${n2.format(v)}${suffix}` : "—"
const moneyCr = (v: unknown) => {
  const x = num(v, NaN)
  return Number.isFinite(x) ? `${x >= 0 ? "+" : ""}${nf.format(x)} Cr` : "—"
}

const REGIME: Record<Regime, { title: string; advice: string; tone: string; deploy: string; pct: number; border: string; text: string; glow: string }> = {
  HOT: { title: "HOT", advice: "Risk ON. Aggressively deploy capital into top-ranked sectors.", tone: "Aggressive deployment", deploy: "75–95%", pct: 92, border: "border-emerald-500/25", text: "text-emerald-300", glow: "from-emerald-500/20" },
  NORMAL: { title: "NORMAL", advice: "Deploy selectively. Focus only on high-conviction names.", tone: "Selective deployment", deploy: "50–70%", pct: 72, border: "border-teal-500/25", text: "text-teal-300", glow: "from-teal-500/20" },
  CAUTION: { title: "CAUTION", advice: "Protect capital. Avoid fresh leveraged positions.", tone: "Defensive selection", deploy: "25–45%", pct: 42, border: "border-amber-500/25", text: "text-amber-300", glow: "from-amber-500/20" },
  COLD: { title: "COLD", advice: "Preserve capital. Wait for breadth and liquidity to improve.", tone: "Low deployment", deploy: "10–30%", pct: 24, border: "border-blue-500/25", text: "text-blue-300", glow: "from-blue-500/20" },
  FROZEN: { title: "FROZEN", advice: "Risk OFF. Hold cash and avoid new positions.", tone: "Cash protocol", deploy: "0–15%", pct: 8, border: "border-rose-500/25", text: "text-rose-300", glow: "from-rose-500/20" },
}

function Spark({ positive = true }: { positive?: boolean }) {
  const bars = positive ? [24, 38, 31, 54, 48, 68, 82] : [80, 62, 70, 50, 42, 35, 28]
  return <div className="flex h-6 w-16 items-end gap-0.5 opacity-70">{bars.map((h, i) => <span key={i} style={{ height: `${h}%` }} className={positive ? "w-full rounded-t-sm bg-emerald-400/70" : "w-full rounded-t-sm bg-rose-400/70"} />)}</div>
}

function Skeleton({ className = "h-20" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl border border-slate-100 bg-slate-50 ${className}`} />
}

function Section({ title, meta, icon, children }: { title: string; meta?: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2.5">
      <h2 className="flex items-center gap-1.5 text-[12px] font-bold uppercase tracking-[0.1em] text-slate-900">{icon}{title}</h2>
      {meta && <span className="font-mono text-[10px] text-slate-400">{meta}</span>}
    </div>
    {children}
  </section>
}

function ActionPill({ action }: { action: Action }) {
  const a = String(action).toUpperCase()
  const cls = a === "BUY" || a === "APPLY" || a === "ACCUMULATE"
    ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
    : a === "SKIP" || a === "AVOID" || a === "TRIM"
    ? "border-rose-500/25 bg-rose-500/10 text-rose-300"
    : "border-amber-500/25 bg-amber-500/10 text-amber-300"
  return <span className={`min-w-[58px] rounded-md border px-2 py-0.5 text-center font-mono text-[10px] font-bold tracking-wider ${cls}`}>{a}</span>
}

export function TodayScreen({ onStockSelect }: { simple?: boolean; onStockSelect?: (s: string) => void; commandCenter?: React.ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [regime, setRegime] = useState<Regime>("NORMAL")
  const [market, setMarket] = useState<MarketTile[]>([])
  const [globalRows, setGlobalRows] = useState<GlobalRow[]>([])
  const [opps, setOpps] = useState<Opportunity[]>([])
  const [ipos, setIpos] = useState<IpoRow[]>([])
  const [sectors, setSectors] = useState<SectorRow[]>([])
  const [brokerConnected, setBrokerConnected] = useState<boolean | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const load = useCallback(async (quiet = false) => {
    quiet ? setRefreshing(true) : setLoading(true)
    try {
      const [globalR, snapR, techR, sectorR, ipoR, brokerR] = await Promise.all([
        fetch("/api/market/global", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/market/snapshot", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/technical/screener?timeframe=daily&limit=8", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/sector-rotation?view=hot", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/ipo/intelligence?limit=5", { cache: "no-store" }).then(r => r.json()).catch(() => null),
        fetch("/api/broker/status", { cache: "no-store" }).then(r => r.json()).catch(() => null),
      ])

      const india = globalR?.india ?? snapR?.data ?? {}
      const r = String(india.regime ?? snapR?.data?.regime ?? "NORMAL").toUpperCase() as Regime
      if (REGIME[r]) setRegime(r)

      setMarket([
        { label: "NIFTY", value: india.nifty ? nf.format(num(india.nifty)) : india.nifty_price ? nf.format(num(india.nifty_price)) : "—", change: india.niftyChg ?? null },
        { label: "BANK NIFTY", value: india.bankNifty ? nf.format(num(india.bankNifty)) : india.banknifty_price ? nf.format(num(india.banknifty_price)) : "—", change: india.bankNiftyChg ?? null },
        { label: "VIX", value: india.vix ? n2.format(num(india.vix)) : "—", note: num(india.vix) < 14 ? "LOW VOL" : num(india.vix) > 18 ? "HIGH VOL" : "NORMAL" },
        { label: "FII", value: moneyCr(india.fii ?? india.fii_flow), note: "Cash flow" },
        { label: "DII", value: moneyCr(india.dii ?? india.dii_flow), note: "Cash flow" },
        { label: "PCR", value: india.pcr ? n2.format(num(india.pcr)) : "—", note: num(india.pcr) >= 1.1 ? "BULLISH" : num(india.pcr) <= 0.8 ? "CAUTION" : "NEUTRAL" },
      ])

      const g = globalR?.global ?? {}
      const pick = (key: string, label?: string): GlobalRow => ({ label: label ?? g[key]?.label ?? key, value: g[key]?.price ? n2.format(num(g[key].price)) : "—", change: typeof g[key]?.changePct === "number" ? g[key].changePct : null, symbol: key })
      setGlobalRows([
        { label: "GIFT NIFTY", value: india.nifty ? nf.format(num(india.nifty)) : "—", change: india.niftyChg ?? null },
        pick("^NDX", "NASDAQ"), pick("^GSPC", "S&P 500"), pick("DX-Y.NYB", "DXY"), pick("GC=F", "GOLD"), pick("BTC-USD", "BTC"),
      ])

      const SUPPRESS = /^(ANTELOP|ACUTAAS|BMWVENTURE)/i
      const tech = (techR?.data ?? []) as any[]
      const techFiltered = tech.filter((x: any) => !SUPPRESS.test(String(x.symbol ?? "")))
      setOpps(techFiltered.slice(0, 5).map((x: any) => {
        const score = Math.round(num(x.buy_zone_score ?? x.probability_score ?? x.mb_score ?? 55))
        const action: Action = score >= 75 || x.volume_expansion || x.nr7 ? "BUY" : score >= 55 ? "WATCH" : "HOLD"
        return { symbol: x.symbol, name: x.company_name, score, action, investability: Math.min(99, Math.max(45, score + 8)), operatorRisk: score >= 70 ? "LOW" : "MEDIUM", reasons: [x.nr7 ? "NR7 compression" : "Technical signal", x.volume_expansion ? "Volume expansion" : "Watch volume"] }
      }))

      const hot = (sectorR?.hot_sectors ?? sectorR?.sectors ?? []) as any[]
      setSectors(hot.slice(0, 5).map((s: any) => ({ name: s.industry_group, performance: num(s.return_3m ?? s.return_6m), score: Math.round(num(s.rotation_score)), signal: s.rotation_signal })))

      const ipoList = (ipoR?.ipos ?? ipoR?.data ?? []) as any[]
      setIpos(ipoList.slice(0, 4).map((i: any) => {
        const lqi = num(i.lqi ?? i.score?.listingScore ?? i.conviction_score ?? 0)
        const rec = lqi >= 75 ? "APPLY" : lqi >= 50 ? "WATCH" : "SKIP"
        return { name: i.company_name ?? i.name ?? i.ipo_name, recommendation: i.score?.recommendation ?? i.recommendation ?? rec, score: Math.round(lqi) || undefined }
      }))

      setBrokerConnected(typeof brokerR?.connected === "boolean" ? brokerR.connected : null)
      setUpdatedAt(new Date())
    } finally {
      setLoading(false); setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const rc = REGIME[regime]
  const topSectors = sectors.slice(0, 3).map(s => s.name).filter(Boolean)
  const day = useMemo(() => new Date().toLocaleString("en-IN", { weekday: "long", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }), [])

  return <div className="min-h-screen bg-[#F7F9FC] text-slate-900">


    <main className="mx-auto grid max-w-[1700px] grid-cols-12 gap-3 px-4 py-3">
      <div className="col-span-12 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <div><h1 className="text-[14px] font-bold text-slate-900">Today’s Market Brief</h1><p className="font-mono text-[10px] text-slate-500">{day} IST · {updatedAt ? `Updated ${updatedAt.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}` : "Loading live state"}</p></div>
        <button onClick={() => load(true)} className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-bold text-slate-700 hover:bg-slate-50"><RefreshCw className={`h-3 w-3 text-teal-300 ${refreshing ? "animate-spin" : ""}`} />Refresh</button>
      </div>

      <div className="col-span-12 space-y-3 xl:col-span-8">
        {loading ? <Skeleton className="h-48" /> : <section className={`relative overflow-hidden rounded-2xl border ${rc.border} bg-[#FFFFFF] p-5 shadow-[0_18px_50px_rgba(0,0,0,0.28)]`}>
          <div className={`pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-gradient-to-l ${rc.glow} to-transparent`} />
          <div className="relative flex items-start justify-between gap-6">
            <div>
              <div className="mb-1 text-[11px] font-black uppercase tracking-[0.22em] text-[#626B76]">System Macro Regime</div>
              <div className={`text-[42px] font-black leading-none tracking-tight ${rc.text}`}>{rc.title}</div>
              <p className="mt-2 max-w-2xl text-[15px] font-semibold text-white">{rc.advice}</p>
              <div className="mt-4 flex flex-wrap gap-2">{topSectors.length ? topSectors.map(s => <span key={s} className="rounded-md border border-white/5 bg-black/25 px-2.5 py-1 text-[11px] font-semibold text-white/85">{s}</span>) : <span className="text-[12px] text-slate-500">Sector rotation import pending</span>}</div>
            </div>
            <div className="min-w-[150px] rounded-xl border border-white/5 bg-black/25 p-3 text-right">
              <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#75808D]">Deployment</div>
              <div className={`text-[30px] font-black ${rc.text}`}>{rc.deploy}</div>
              <div className="mt-2 h-2 rounded-full bg-white/10"><div style={{ width: `${rc.pct}%` }} className="h-full rounded-full bg-current opacity-70" /></div>
              <div className="mt-2 text-[11px] text-[#8B95A3]">{rc.tone}</div>
            </div>
          </div>
        </section>}

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <Section title="Top Convergence" meta="Technical Signals" icon={<Flame className="h-3.5 w-3.5 text-orange-400" />}>
            {loading ? <Skeleton className="h-36" /> : opps.length ? <div className="space-y-1.5">{opps.map(o => <button key={o.symbol} onClick={() => onStockSelect?.(o.symbol)} className="group flex w-full items-center justify-between rounded-xl border border-transparent p-2 text-left hover:border-[#29313B] hover:bg-[#171D25]">
              <div className="min-w-0"><div className="flex items-center gap-2"><span className="font-mono text-[13px] font-black text-white group-hover:text-teal-300">{o.symbol}</span><span className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-[#8D98A6]">Score {o.score}</span></div><div className="truncate text-[11px] text-[#687382]">{o.reasons?.slice(0, 2).join(" · ")}</div></div>
              <div className="flex items-center gap-3"><Spark positive={o.action !== "AVOID"} /><ActionPill action={o.action} /><ChevronRight className="h-3.5 w-3.5 text-slate-500" /></div>
            </button>)}</div> : <div className="rounded-xl bg-[#F9FAFB] p-5 text-center text-[12px] text-[#687382]">No technical signals yet. Wire/import <span className="font-mono">technical_signals</span>.</div>}
          </Section>

          <Section title="IPO DNA" meta="Primary Market" icon={<Award className="h-3.5 w-3.5 text-teal-300" />}>
            {loading ? <Skeleton className="h-36" /> : ipos.length ? <div className="space-y-1.5">{ipos.map(i => {
              const rec = String(i.recommendation ?? "WATCH").toUpperCase(); const action: Action = rec.includes("APPLY") ? "APPLY" : rec.includes("SKIP") || rec.includes("AVOID") ? "SKIP" : "WATCH"
              return <div key={i.name} className="flex items-center justify-between rounded-xl p-2 hover:bg-[#171D25]"><div className="min-w-0"><div className="truncate text-[13px] font-bold text-white">{i.name}</div><div className="font-mono text-[10px] text-[#687382]">Conviction {i.score ? Math.round(num(i.score)) : "—"}</div></div><ActionPill action={action} /></div>
            })}</div> : <div className="rounded-xl bg-[#F9FAFB] p-5 text-center text-[12px] text-[#687382]">No open IPOs.</div>}
          </Section>
        </div>

        <Section title="Sector Leadership" meta="Rotation Engine" icon={<BarChart2 className="h-3.5 w-3.5 text-indigo-300" />}>
          {loading ? <Skeleton className="h-28" /> : sectors.length ? <div className="grid grid-cols-1 gap-2 md:grid-cols-2">{sectors.map(s => <div key={s.name} className="flex items-center justify-between rounded-xl border border-slate-200 bg-[#F9FAFB] p-2.5"><div className="min-w-0"><div className="truncate text-[12px] font-bold text-white">{s.name}</div><div className="text-[10px] text-[#687382]">{s.signal ?? "Leadership improving"}</div></div><div className="flex items-center gap-3 font-mono"><span className={num(s.performance) >= 0 ? "text-[11px] font-bold text-emerald-300" : "text-[11px] font-bold text-rose-300"}>{signed(s.performance)}</span><span className="rounded-md border border-indigo-500/20 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-bold text-indigo-300">{s.score ?? "—"}</span></div></div>)}</div> : <div className="rounded-xl bg-[#F9FAFB] p-5 text-center text-[12px] text-[#687382]">Sector rotation data pending. Run import script.</div>}
        </Section>
      </div>

      <div className="col-span-12 space-y-3 xl:col-span-4">
        <Section title="Domestic Market" meta="Live / Cache" icon={<Activity className="h-3.5 w-3.5 text-teal-300" />}>
          {loading ? <Skeleton className="h-72" /> : <div className="grid grid-cols-2 gap-2">{market.map((m, idx) => <div key={m.label} className={idx < 2 ? "col-span-2 flex items-center justify-between rounded-xl border border-slate-200 bg-[#F9FAFB] p-3" : "rounded-xl border border-slate-200 bg-[#F9FAFB] p-3"}>
            <div><div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">{m.label}</div><div className={idx < 2 ? "font-mono text-[22px] font-black text-white" : "font-mono text-[16px] font-black text-white"}>{m.value}</div><div className="mt-1 text-[10px] font-bold text-[#687382]">{m.note ?? ""}</div></div>
            {idx < 2 && <div className="flex flex-col items-end gap-1"><span className={(m.change ?? 0) >= 0 ? "font-mono text-[12px] font-bold text-emerald-300" : "font-mono text-[12px] font-bold text-rose-300"}>{signed(m.change)}</span><Spark positive={(m.change ?? 0) >= 0} /></div>}
          </div>)}</div>}
        </Section>

        <Section title="Global Markets" meta="Macro Overlay" icon={<Globe className="h-3.5 w-3.5 text-blue-300" />}>
          {loading ? <Skeleton className="h-56" /> : <div className="space-y-1.5">{globalRows.map(g => <div key={g.label} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-2 font-mono"><span className="font-sans text-[11px] font-bold text-slate-600">{g.label}</span><div className="flex items-center gap-3"><span className="text-[11px] font-bold text-slate-900">{g.value ?? "—"}</span><span className={(g.change ?? 0) >= 0 ? "min-w-[50px] text-right text-[10px] font-bold text-emerald-300" : "min-w-[50px] text-right text-[10px] font-bold text-rose-300"}>{signed(g.change)}</span></div></div>)}</div>}
        </Section>
      </div>
    </main>
  </div>
}
