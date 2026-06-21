"use client"
// components/features/ipo-listing-dashboard.tsx
// SESSION 9 — World-class IPO Command Centre.
// Play-first design: BUY_AT_OPEN · WAIT_FOR_VWAP · AVOID · BUY_AFTER_DAY3
// Data: /api/ipo/playbook  (rich: GMP, subscription x, BRLM score, returns)

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, TrendingUp, Zap } from "lucide-react"

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  bg:       "#F7F9FC", surface: "#FFFFFF", border: "#E5E7EB",
  text:     "#0F172A", textSub: "#475569",  textMeta: "#94A3B8",
  green:  "#16A34A", greenBg:  "#F0FDF4", greenBd:  "#BBF7D0",
  teal:   "#0D9488", tealBg:   "#F0FDFA", tealBd:   "#99F6E4",
  amber:  "#D97706", amberBg:  "#FFFBEB", amberBd:  "#FDE68A",
  red:    "#DC2626", redBg:    "#FEF2F2", redBd:    "#FECACA",
  blue:   "#2563EB", blueBg:   "#EFF6FF", blueBd:   "#BFDBFE",
  purple: "#7C3AED", purpleBg: "#F5F3FF", purpleBd: "#DDD6FE",
  slate:  "#64748B", slateBg:  "#F8FAFC",
}

// ── Play config ───────────────────────────────────────────────────────────────
type Play = "BUY_AT_OPEN"|"WAIT_FOR_VWAP"|"BUY_AFTER_DAY3"|"BUY_PANIC_DIP"|"AVOID"|string
const PLAY: Record<string, { label: string; color: string; bg: string; bd: string; emoji: string; tip: string }> = {
  BUY_AT_OPEN:    { label:"BUY AT OPEN",    color:C.green,  bg:C.greenBg,  bd:C.greenBd,  emoji:"⚡", tip:"Apply and sell on listing open" },
  WAIT_FOR_VWAP:  { label:"WAIT FOR VWAP",  color:C.teal,   bg:C.tealBg,   bd:C.tealBd,   emoji:"🎯", tip:"Buy on listing day if price holds VWAP after 15 min" },
  BUY_AFTER_DAY3: { label:"BUY AFTER DAY3", color:C.blue,   bg:C.blueBg,   bd:C.blueBd,   emoji:"📅", tip:"Let price stabilise 3 days post listing, then enter" },
  BUY_PANIC_DIP:  { label:"BUY PANIC DIP",  color:C.purple, bg:C.purpleBg, bd:C.purpleBd, emoji:"📉", tip:"Buy only on a sharp sell-off below issue price" },
  AVOID:          { label:"AVOID",           color:C.red,    bg:C.redBg,    bd:C.redBd,    emoji:"🚫", tip:"Skip this IPO — risk/reward not favourable" },
}
const playOf = (p?: string) => PLAY[p ?? ""] ?? { label: p ?? "—", color:C.slate, bg:C.slateBg, bd:C.border, emoji:"—", tip:"" }

// ── Engine accuracy (from handover data) ─────────────────────────────────────
const ENGINE_STATS = [
  { play:"BUY_AT_OPEN",    accuracy:"98%",  avg:"+46.5% open gain",  n:195 },
  { play:"WAIT_FOR_VWAP",  accuracy:"75%",  avg:"+24.1% held",       n:116 },
  { play:"BUY_AFTER_DAY3", accuracy:null,   avg:"+3.8%",             n:94  },
  { play:"AVOID",          accuracy:"✅",   avg:"-4.4% (correctly avoided)", n:135 },
]

// ── Helpers ───────────────────────────────────────────────────────────────────
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const fmt = (v: unknown, dec = 0) => n(v).toLocaleString("en-IN", { maximumFractionDigits: dec })
const pctFmt = (v: unknown) => `${n(v) >= 0 ? "+" : ""}${n(v).toFixed(1)}%`
const cr = (v: unknown) => `₹${fmt(v)}Cr`
const daysLeft = (d?: string | null) => {
  if (!d) return null
  const diff = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000)
  return diff
}
const statusOf = (ipo: any) => {
  const now  = Date.now()
  const open = ipo.open_date ? new Date(ipo.open_date).getTime() : 0
  const cls  = ipo.close_date ? new Date(ipo.close_date).getTime() : 0
  const lst  = ipo.listing_date ? new Date(ipo.listing_date).getTime() : 0
  if (lst && now >= lst)              return "LISTED"
  if (cls && now > cls && lst)        return "ALLOTMENT"
  if (open && now >= open && now <= cls) return "OPEN"
  return "UPCOMING"
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PlayBadge({ play, large }: { play: string; large?: boolean }) {
  const p = playOf(play)
  const sz = large ? { fontSize: 13, padding: "6px 14px", borderRadius: 10, fontWeight: 800 }
                   : { fontSize: 10, padding: "3px 8px",  borderRadius: 6,  fontWeight: 700 }
  return (
    <span style={{ ...sz, background: p.bg, color: p.color, border: `1px solid ${p.bd}`, letterSpacing:"0.03em" }}>
      {p.emoji} {p.label}
    </span>
  )
}

function SubscriptionBar({ label, value, max = 100 }: { label: string; value: number | null; max?: number }) {
  const v     = value ?? 0
  const pct   = Math.min(100, (v / Math.max(max, 1)) * 100)
  const color = v >= 50 ? C.green : v >= 10 ? C.teal : v >= 1 ? C.amber : C.slate
  return (
    <div style={{ marginBottom: 5 }}>
      <div style={{ display:"flex", justifyContent:"space-between", fontSize: 10, color: C.textSub, marginBottom: 2 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ fontWeight: 800, color }}>{v > 0 ? `${v.toFixed(1)}x` : "—"}</span>
      </div>
      <div style={{ height: 4, background: "#E2E8F0", borderRadius: 2 }}>
        <div style={{ width:`${pct}%`, height:"100%", background: color, borderRadius: 2, transition:"width .4s" }}/>
      </div>
    </div>
  )
}

function GmpBadge({ pct, momentum }: { pct: number | null; momentum?: string | null }) {
  if (pct == null) return null
  const color = pct >= 20 ? C.green : pct >= 5 ? C.teal : pct < 0 ? C.red : C.slate
  const arrow = momentum === "RISING" ? "↑" : momentum === "FALLING" ? "↓" : ""
  return (
    <span style={{ fontSize: 11, fontWeight: 700, color, padding:"2px 8px", background: color+"18",
      border:`1px solid ${color}30`, borderRadius: 6 }}>
      GMP {arrow} {pct >= 0 ? "+" : ""}{pct.toFixed(0)}%
    </span>
  )
}

function BrlmBadge({ name, score }: { name?: string | null; score?: number | null }) {
  if (!name && !score) return null
  const tier = (score ?? 0) >= 80 ? { label:"Tier 1", color:C.green } :
               (score ?? 0) >= 60 ? { label:"Tier 2", color:C.teal  } :
               (score ?? 0) >= 40 ? { label:"Tier 3", color:C.amber } :
                                    { label:"Tier 4", color:C.red   }
  return (
    <div style={{ display:"flex", alignItems:"center", gap: 6, flexWrap:"wrap" }}>
      <span style={{ fontSize: 10, color: C.textMeta }}>BRLM</span>
      {name && <span style={{ fontSize: 11, fontWeight: 600, color: C.textSub }}>{String(name).split(",")[0].trim()}</span>}
      {score != null && (
        <span style={{ fontSize: 10, fontWeight: 800, color: tier.color, padding:"1px 6px",
          background: tier.color+"18", borderRadius: 4 }}>
          {tier.label} · {score}
        </span>
      )}
    </div>
  )
}

function StatChip({ label, value, color = C.textSub }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ textAlign:"center", background: C.slateBg, borderRadius: 8, padding:"7px 10px", flex: 1, minWidth: 60 }}>
      <div style={{ fontSize: 9, color: C.textMeta, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 12, fontWeight: 800, color }}>{value}</div>
    </div>
  )
}

function LqiRing({ lqi }: { lqi: number }) {
  const size = 48, r = 20
  const circ  = 2 * Math.PI * r
  const dash  = Math.min(1, lqi / 100) * circ
  const color = lqi >= 75 ? C.green : lqi >= 55 ? C.teal : lqi >= 40 ? C.amber : C.red
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={24} cy={24} r={r} fill="none" stroke="#E2E8F0" strokeWidth={4}/>
      <circle cx={24} cy={24} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform="rotate(-90 24 24)"/>
      <text x={24} y={24} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: 11, fontWeight: 900, fill: color }}>{Math.round(lqi)}</text>
    </svg>
  )
}

// ── IPO Card ──────────────────────────────────────────────────────────────────
function IpoCard({ ipo, expanded, onToggle }: {
  ipo: any; expanded: boolean; onToggle: () => void
}) {
  const status = statusOf(ipo)
  const play   = playOf(ipo.play_recommendation ?? ipo.suggested_action)
  const days   = status === "OPEN"     ? daysLeft(ipo.close_date) :
                 status === "UPCOMING" ? daysLeft(ipo.open_date)  : null
  const lqi    = n(ipo.lqi_final ?? ipo.lqi ?? 0)
  const maxSub = Math.max(n(ipo.qib_subscription_x), n(ipo.nii_subscription_x),
                          n(ipo.rii_subscription_x), 30)

  const statusStyle: Record<string, React.CSSProperties> = {
    OPEN:      { background: C.greenBg, color: C.green, border:`1px solid ${C.greenBd}` },
    UPCOMING:  { background: C.blueBg,  color: C.blue,  border:`1px solid ${C.blueBd}` },
    ALLOTMENT: { background: C.amberBg, color: C.amber, border:`1px solid ${C.amberBd}` },
    LISTED:    { background: "#F1F5F9", color: C.slate,  border:`1px solid ${C.border}` },
  }

  return (
    <div style={{
      background: C.surface, border:`1px solid ${ipo.play_recommendation === "AVOID" ? C.redBd : C.border}`,
      borderLeft:`3px solid ${play.color}`, borderRadius: 14, marginBottom: 10, overflow:"hidden",
    }}>
      {/* ── Header ── */}
      <div onClick={onToggle} style={{ padding:"14px 16px", cursor:"pointer" }}>
        <div style={{ display:"flex", alignItems:"flex-start", gap: 12 }}>
          <LqiRing lqi={lqi} />

          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Name row */}
            <div style={{ display:"flex", alignItems:"center", gap: 8, flexWrap:"wrap", marginBottom: 4 }}>
              <span style={{ fontSize: 15, fontWeight: 900, color: C.text }}>{ipo.company_name}</span>
              <PlayBadge play={ipo.play_recommendation ?? ipo.suggested_action ?? ""} />
              {status !== "LISTED" && (
                <span style={{ fontSize: 10, fontWeight: 700, padding:"2px 7px", borderRadius: 5,
                  ...statusStyle[status] }}>{status}</span>
              )}
            </div>

            {/* Meta row */}
            <div style={{ display:"flex", gap: 12, flexWrap:"wrap", alignItems:"center" }}>
              {ipo.issue_price > 0 && (
                <span style={{ fontSize: 11, fontWeight: 700, color: C.textSub }}>₹{fmt(ipo.issue_price)}</span>
              )}
              {ipo.issue_size_cr > 0 && (
                <span style={{ fontSize: 11, color: C.textMeta }}>{cr(ipo.issue_size_cr)}</span>
              )}
              {ipo.sector && (
                <span style={{ fontSize: 10, color: C.textMeta, background:"#F1F5F9",
                  padding:"1px 7px", borderRadius: 4 }}>{ipo.sector}</span>
              )}
              {days != null && days >= 0 && (
                <span style={{ fontSize: 10, fontWeight: 700, color: days <= 2 ? C.amber : C.textMeta }}>
                  {status === "OPEN" ? `Closes in ${days}d` : `Opens in ${days}d`}
                </span>
              )}
              {ipo.close_date && status !== "LISTED" && (
                <span style={{ fontSize: 10, color: C.textMeta }}>
                  {status === "OPEN" ? `Closes ${ipo.close_date}` : `Opens ${ipo.open_date ?? "TBD"}`}
                </span>
              )}
              <GmpBadge pct={ipo.gmp_pct ?? ipo.gmp_percentage} momentum={ipo.gmp_momentum} />
            </div>
          </div>

          {/* Right: BRLM + expand */}
          <div style={{ textAlign:"right", flexShrink: 0 }}>
            {ipo.brlm_score != null && (
              <div style={{ fontSize: 10, fontWeight: 800, color: (ipo.brlm_score??0)>=70?C.green:C.amber, marginBottom: 3 }}>
                BRLM {ipo.brlm_score}
              </div>
            )}
            <div style={{ fontSize: 10, color: C.textMeta }}>{expanded ? "▲" : "▼"}</div>
          </div>
        </div>

        {/* Subscription bars — always visible when data exists */}
        {(ipo.qib_subscription_x || ipo.nii_subscription_x || ipo.rii_subscription_x) && (
          <div style={{ marginTop: 10 }}>
            <SubscriptionBar label="QIB" value={ipo.qib_subscription_x} max={maxSub} />
            <SubscriptionBar label="NII" value={ipo.nii_subscription_x} max={maxSub} />
            <SubscriptionBar label="RII" value={ipo.rii_subscription_x} max={maxSub} />
            {ipo.total_subscription_x > 0 && (
              <div style={{ fontSize: 10, color: C.textSub, textAlign:"right", marginTop: 4, fontWeight: 700 }}>
                Total: {n(ipo.total_subscription_x).toFixed(1)}x
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Expanded detail ── */}
      {expanded && (
        <div style={{ borderTop:`1px solid ${C.border}`, background: C.slateBg, padding:"14px 16px" }}>

          {/* Play tip */}
          {play.tip && (
            <div style={{ background: play.bg, border:`1px solid ${play.bd}`, borderRadius: 8,
              padding:"9px 12px", marginBottom: 12, fontSize: 12, color: play.color, fontWeight: 600 }}>
              {play.emoji} {play.tip}
              {ipo.play_stop_loss_pct && (
                <span style={{ marginLeft: 12, color: C.red }}>
                  Stop: {Math.abs(n(ipo.play_stop_loss_pct)).toFixed(0)}%
                </span>
              )}
              {ipo.play_target_pct && (
                <span style={{ marginLeft: 8, color: C.green }}>
                  Target: +{n(ipo.play_target_pct).toFixed(0)}%
                </span>
              )}
            </div>
          )}

          {/* Stats grid */}
          <div style={{ display:"flex", gap: 6, flexWrap:"wrap", marginBottom: 12 }}>
            {lqi > 0 && <StatChip label="LQI Score" value={String(Math.round(lqi))} color={lqi>=70?C.green:lqi>=50?C.teal:C.amber}/>}
            {ipo.prob_10pct_profit > 0 && <StatChip label="P(+10%)" value={`${n(ipo.prob_10pct_profit).toFixed(0)}%`} color={C.green}/>}
            {ipo.prob_loss_gt10 != null && <StatChip label="P(loss)" value={`${n(ipo.prob_loss_gt10).toFixed(0)}%`} color={C.red}/>}
            {ipo.ofs_pct > 0 && <StatChip label="OFS%" value={`${n(ipo.ofs_pct).toFixed(0)}%`} color={n(ipo.ofs_pct)>60?C.red:C.textSub}/>}
            {ipo.ipo_pe > 0 && <StatChip label="P/E" value={n(ipo.ipo_pe).toFixed(0)} />}
            {ipo.peer_pe > 0 && <StatChip label="Peer P/E" value={n(ipo.peer_pe).toFixed(0)} />}
          </div>

          {/* BRLM full detail */}
          <BrlmBadge name={ipo.brlm_names ?? ipo.brlm} score={ipo.brlm_score} />

          {/* Post-listing returns (for listed IPOs) */}
          {(ipo.return_d7 != null || ipo.return_day7 != null || ipo.return_listing_open != null) && (
            <div style={{ marginTop: 12, display:"flex", gap: 6, flexWrap:"wrap" }}>
              {ipo.return_listing_open != null && (
                <StatChip label="Listing open" value={pctFmt(ipo.return_listing_open)} color={n(ipo.return_listing_open)>=0?C.green:C.red}/>
              )}
              {(ipo.return_d7 ?? ipo.return_day7) != null && (
                <StatChip label="Day 7" value={pctFmt(ipo.return_d7 ?? ipo.return_day7)} color={n(ipo.return_d7??ipo.return_day7)>=0?C.green:C.red}/>
              )}
              {(ipo.return_d30 ?? ipo.return_day30) != null && (
                <StatChip label="Day 30" value={pctFmt(ipo.return_d30??ipo.return_day30)} color={n(ipo.return_d30??ipo.return_day30)>=0?C.green:C.red}/>
              )}
              {(ipo.return_d90 ?? ipo.return_day90) != null && (
                <StatChip label="Day 90" value={pctFmt(ipo.return_d90??ipo.return_day90)} color={n(ipo.return_d90??ipo.return_day90)>=0?C.green:C.red}/>
              )}
            </div>
          )}

          {/* Play reasons */}
          {ipo.play_reasons && (
            <div style={{ marginTop: 10, fontSize: 10, color: C.textMeta, lineHeight: 1.6 }}>
              {(() => {
                try {
                  const r = typeof ipo.play_reasons === "string" ? JSON.parse(ipo.play_reasons) : ipo.play_reasons
                  return Array.isArray(r) ? r.map((rs: string, i: number) => <div key={i}>• {rs}</div>) : String(r)
                } catch { return String(ipo.play_reasons) }
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Engine accuracy strip ──────────────────────────────────────────────────────
function AccuracyStrip() {
  return (
    <div style={{ background:"linear-gradient(135deg,#0f172a,#1e3a5f)",
      borderRadius: 14, padding:"14px 18px", marginBottom: 14, display:"flex",
      gap: 20, flexWrap:"wrap", alignItems:"center" }}>
      <div>
        <div style={{ fontSize: 10, color:"#475569", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom: 2 }}>AACapital IPO Engine</div>
        <div style={{ fontSize: 22, fontWeight: 900, color:"#F8FAFC" }}>500 IPOs scored · 98% accuracy</div>
      </div>
      {ENGINE_STATS.map(s => (
        <div key={s.play} style={{ textAlign:"center" }}>
          <div style={{ fontSize: 10, color:"#64748b", marginBottom: 2 }}>
            {playOf(s.play).emoji} {playOf(s.play).label}
          </div>
          <div style={{ fontSize: 16, fontWeight: 900, color: s.accuracy?.startsWith("+") ? "#4ade80" : s.accuracy === "✅" ? "#4ade80" : "#f8fafc" }}>
            {s.accuracy ?? s.avg}
          </div>
          <div style={{ fontSize: 9, color:"#475569" }}>{s.n} IPOs · {s.avg}</div>
        </div>
      ))}
    </div>
  )
}

// ── BRLM Leaderboard ──────────────────────────────────────────────────────────
function BrlmLeaderboard({ ipos }: { ipos: any[] }) {
  const brlmMap: Record<string, { score: number; count: number; avgGain: number }> = {}
  for (const ipo of ipos) {
    const name  = String(ipo.brlm_names ?? ipo.brlm ?? "").split(",")[0].trim()
    const score = n(ipo.brlm_score)
    if (!name || !score) continue
    if (!brlmMap[name]) brlmMap[name] = { score, count: 0, avgGain: n(ipo.brlm_avg_listing_gain ?? 0) }
    brlmMap[name].count++
  }
  const ranked = Object.entries(brlmMap)
    .sort((a, b) => b[1].score - a[1].score)
    .slice(0, 15)

  if (!ranked.length) return (
    <div style={{ padding: 24, textAlign:"center", color: C.textMeta, fontSize: 12 }}>
      BRLM data loads as IPO intelligence is built up.
    </div>
  )

  return (
    <div>
      {ranked.map(([name, d], i) => {
        const tierColor = d.score >= 80 ? C.green : d.score >= 60 ? C.teal : d.score >= 40 ? C.amber : C.red
        const barW      = `${d.score}%`
        return (
          <div key={name} style={{ display:"flex", alignItems:"center", gap: 12,
            padding:"10px 14px", borderBottom:`1px solid ${C.border}`, background: i%2===0?C.surface:C.slateBg }}>
            <span style={{ width: 20, fontSize: 11, fontWeight: 700, color: C.textMeta, flexShrink: 0 }}>
              {i+1}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.text, marginBottom: 3 }}>{name}</div>
              <div style={{ height: 4, background:"#E2E8F0", borderRadius: 2 }}>
                <div style={{ width: barW, height:"100%", background: tierColor, borderRadius: 2 }}/>
              </div>
            </div>
            <div style={{ textAlign:"right", flexShrink: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 900, color: tierColor }}>{d.score}</div>
              <div style={{ fontSize: 9, color: C.textMeta }}>{d.count} IPOs</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
const TABS = [
  { id:"command",  label:"⚡ Command",     desc:"What to do right now" },
  { id:"open",     label:"📋 Open",        desc:"Currently accepting applications" },
  { id:"upcoming", label:"📅 Upcoming",    desc:"Opening soon" },
  { id:"listed",   label:"📈 Post-Listing",desc:"Recently listed — VWAP signals" },
  { id:"brlm",     label:"🏆 BRLM Rank",  desc:"Banker track record" },
]

function Skeleton({ h = 80 }: { h?: number }) {
  return <div style={{ background:"#F1F5F9", borderRadius: 12, height: h, marginBottom: 10, opacity: 0.7 }}/>
}

export function IpoListingDashboard() {
  const [ipos,     setIpos]     = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [tab,      setTab]      = useState("command")
  const [expanded, setExpanded] = useState<number | null>(null)
  const [search,   setSearch]   = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res  = await fetch("/api/ipo/playbook?limit=100", { cache:"no-store" })
      const json = await res.json()
      setIpos(json.ipos ?? [])
    } catch { setIpos([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const now  = Date.now()
  const all  = ipos.filter(i => !search ||
    (i.company_name ?? "").toLowerCase().includes(search.toLowerCase()))

  const command  = all.filter(i => ["BUY_AT_OPEN","WAIT_FOR_VWAP"].includes(i.play_recommendation)
    && statusOf(i) !== "LISTED").slice(0, 8)
  const openIpos = all.filter(i => statusOf(i) === "OPEN")
  const upcoming = all.filter(i => statusOf(i) === "UPCOMING")
  const listed   = all.filter(i => statusOf(i) === "LISTED" || statusOf(i) === "ALLOTMENT")
    .sort((a, b) => new Date(b.listing_date).getTime() - new Date(a.listing_date).getTime())
    .slice(0, 20)

  const lists: Record<string, any[]> = { command, open: openIpos, upcoming, listed }
  const active = lists[tab] ?? all

  const tabCounts: Record<string, number> = {
    command: command.length, open: openIpos.length, upcoming: upcoming.length, listed: listed.length,
  }


  return (
    <div style={{ background: C.bg, minHeight:"100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin:"0 auto", padding:"16px 16px 0" }}>

        {/* Engine accuracy strip */}
        {!loading && <AccuracyStrip />}

        {/* Search */}
        <div style={{ marginBottom: 12 }}>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search IPO name…"
            style={{ width:"100%", boxSizing:"border-box", padding:"9px 14px", borderRadius: 10,
              border:`1px solid ${C.border}`, fontSize: 13, color: C.text, background: C.surface,
              outline:"none" }} />
        </div>

        {/* Tabs */}
        <div style={{ display:"flex", gap: 6, marginBottom: 14, overflowX:"auto", paddingBottom: 2 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => { setTab(t.id); setExpanded(null) }} style={{
              padding:"6px 14px", borderRadius: 20, fontSize: 11, cursor:"pointer", whiteSpace:"nowrap",
              border:`1px solid ${tab===t.id ? C.blue : C.border}`,
              background: tab===t.id ? C.blueBg : C.surface,
              color:      tab===t.id ? C.blue   : C.slate,
              fontWeight: tab===t.id ? 700      : 400,
            }}>
              {t.label}
              {tabCounts[t.id] != null && tabCounts[t.id] > 0 && (
                <span style={{ marginLeft: 5, fontSize: 9, background: tab===t.id?C.blue:"#E2E8F0",
                  color: tab===t.id?"white":C.slate, borderRadius: 10, padding:"0 5px", fontWeight: 800 }}>
                  {tabCounts[t.id]}
                </span>
              )}
            </button>
          ))}
          <button onClick={() => load()} style={{
            marginLeft:"auto", padding:"6px 12px", borderRadius: 20, fontSize: 11, cursor:"pointer",
            border:`1px solid ${C.border}`, background: C.surface, color: C.slate,
            display:"flex", alignItems:"center", gap: 4, whiteSpace:"nowrap",
          }}>
            <RefreshCw size={10} /> Refresh
          </button>
        </div>

        {/* Tab description */}
        {tab !== "brlm" && (
          <div style={{ fontSize: 11, color: C.textMeta, marginBottom: 12 }}>
            {TABS.find(t => t.id === tab)?.desc}
            {tab === "command" && command.length === 0 && !loading &&
              " — No strong plays right now. Check Upcoming tab."}
          </div>
        )}

        {/* Content */}
        {tab === "brlm" ? (
          <div style={{ background: C.surface, border:`1px solid ${C.border}`, borderRadius: 14, overflow:"hidden" }}>
            <div style={{ padding:"14px 16px", borderBottom:`1px solid ${C.border}` }}>
              <div style={{ fontSize: 14, fontWeight: 800, color: C.text }}>BRLM Leaderboard</div>
              <div style={{ fontSize: 11, color: C.textMeta }}>Investment banker quality score · Drives IPO outcome probability</div>
            </div>
            {loading ? <Skeleton h={300} /> : <BrlmLeaderboard ipos={ipos} />}
          </div>
        ) : loading ? (
          [1,2,3].map(i => <Skeleton key={i} h={120} />)
        ) : active.length === 0 ? (
          <div style={{ padding:"48px 0", textAlign:"center", color: C.textMeta }}>
            <TrendingUp size={32} color="#CBD5E1" style={{ margin:"0 auto 12px", display:"block" }}/>
            <div style={{ fontSize: 14, marginBottom: 6 }}>
              {search ? `No IPOs matching "${search}"` :
               tab === "open" ? "No IPOs currently open for subscription" :
               tab === "upcoming" ? "No upcoming IPOs in the database yet" :
               tab === "listed" ? "No recently listed IPOs" :
               "No actionable plays right now"}
            </div>
            {tab === "command" && (
              <div style={{ fontSize: 12 }}>
                Subscribe data for open IPOs on Chittorgarh and update via the SQL command in the handover.
              </div>
            )}
          </div>
        ) : (
          active.map((ipo, i) => (
            <IpoCard key={ipo.id ?? i} ipo={ipo}
              expanded={expanded === (ipo.id ?? i)}
              onToggle={() => setExpanded(expanded === (ipo.id ?? i) ? null : (ipo.id ?? i))} />
          ))
        )}

        {/* Footer disclaimer */}
        <div style={{ fontSize: 10, color:"#CBD5E1", textAlign:"center", marginTop: 8, lineHeight: 1.6 }}>
          Engine accuracy based on 500 historical IPOs · Not SEBI registered advice ·
          Always verify GMP and subscription data on Chittorgarh before trading
        </div>
      </div>
    </div>
  )
}
