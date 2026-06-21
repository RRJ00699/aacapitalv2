"use client"
// components/features/roi-tracker.tsx
// SESSION 9 — ROI Tracker: engine calls vs actual outcomes
// Simple P&L comparison: did the play_recommendation deliver?
// Data from /api/ipo/playbook — already has return_listing_open, return_day7 etc.

import { useState, useEffect, useCallback } from "react"
import { TrendingUp, TrendingDown, Target, RefreshCw } from "lucide-react"

const C = {
  bg:"#F7F9FC", surface:"#FFFFFF", border:"#E5E7EB",
  text:"#0F172A", textSub:"#475569", textMeta:"#94A3B8",
  green:"#16A34A", greenBg:"#F0FDF4", greenBd:"#BBF7D0",
  red:"#DC2626",   redBg:"#FEF2F2",   redBd:"#FECACA",
  amber:"#D97706", amberBg:"#FFFBEB", amberBd:"#FDE68A",
  blue:"#2563EB",  blueBg:"#EFF6FF",  blueBd:"#BFDBFE",
  teal:"#0D9488",  tealBg:"#F0FDFA",
}

const PLAY_COLOR: Record<string, string> = {
  BUY_AT_OPEN: C.green, WAIT_FOR_VWAP: C.teal,
  BUY_AFTER_DAY3: C.blue, AVOID: C.red, BUY_PANIC_DIP: "#7C3AED",
}

const n  = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const p2 = (v: unknown) => `${n(v) >= 0 ? "+" : ""}${n(v).toFixed(1)}%`
const pclr = (v: number) => v >= 0 ? C.green : C.red

interface PlayStats {
  play:       string
  count:      number
  wins:       number        // return > 0
  avgReturn:  number        // avg return_listing_open
  avgDay7:    number
  accuracy:   number        // pct with return > 5%
  totalPnl:   number        // sum of all returns (as pct pts)
}

function computeStats(ipos: any[]): PlayStats[] {
  const map: Record<string, any[]> = {}
  for (const ipo of ipos) {
    const play = ipo.play_recommendation
    if (!play || play === "NONE") continue
    const ret = n(ipo.return_listing_open ?? ipo.return_day1_close ?? ipo.listing_gain)
    if (ret === 0 && !ipo.listing_date) continue  // not yet listed
    if (!map[play]) map[play] = []
    map[play].push({ ret, day7: n(ipo.return_day7) })
  }
  return Object.entries(map)
    .map(([play, rows]) => ({
      play,
      count:      rows.length,
      wins:       rows.filter(r => r.ret > 0).length,
      avgReturn:  rows.reduce((s, r) => s + r.ret, 0) / rows.length,
      avgDay7:    rows.filter(r => r.day7 !== 0).reduce((s, r) => s + r.day7, 0) /
                  Math.max(1, rows.filter(r => r.day7 !== 0).length),
      accuracy:   (rows.filter(r => r.ret > 5).length / rows.length) * 100,
      totalPnl:   rows.reduce((s, r) => s + r.ret, 0),
    }))
    .sort((a, b) => b.count - a.count)
}

function StatBox({ label, value, sub, color = C.text }: {
  label: string; value: string; sub?: string; color?: string
}) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: "12px 14px", flex: 1, minWidth: 80 }}>
      <div style={{ fontSize: 9, color: C.textMeta, textTransform:"uppercase",
        letterSpacing:"0.08em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 900, color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: C.textMeta, marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

function AccuracyBar({ pct }: { pct: number }) {
  const color = pct >= 70 ? C.green : pct >= 50 ? C.amber : C.red
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display:"flex", justifyContent:"space-between", fontSize: 10,
        color: C.textMeta, marginBottom: 3 }}>
        <span>Accuracy (&gt;5% gain)</span>
        <span style={{ fontWeight: 700, color }}>{pct.toFixed(0)}%</span>
      </div>
      <div style={{ height: 5, background: "#E2E8F0", borderRadius: 3 }}>
        <div style={{ width:`${Math.min(100,pct)}%`, height:"100%",
          background: color, borderRadius: 3, transition:"width .4s" }} />
      </div>
    </div>
  )
}

function PlayCard({ s }: { s: PlayStats }) {
  const color = PLAY_COLOR[s.play] ?? C.textSub
  const label = s.play.replace(/_/g," ")
  return (
    <div style={{ background: C.surface, border:`1px solid ${C.border}`,
      borderLeft:`3px solid ${color}`, borderRadius: 12, padding:"14px 16px",
      marginBottom: 10 }}>
      <div style={{ display:"flex", alignItems:"center",
        justifyContent:"space-between", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color }}>{label}</div>
          <div style={{ fontSize: 10, color: C.textMeta }}>{s.count} IPOs tracked</div>
        </div>
        <div style={{ textAlign:"right" }}>
          <div style={{ fontSize: 22, fontWeight: 900, color: pclr(s.avgReturn) }}>
            {p2(s.avgReturn)}
          </div>
          <div style={{ fontSize: 9, color: C.textMeta }}>avg listing return</div>
        </div>
      </div>

      <div style={{ display:"flex", gap: 6 }}>
        <StatBox label="Wins" value={`${s.wins}/${s.count}`}
          color={s.wins/s.count > 0.7 ? C.green : C.amber}
          sub={`${((s.wins/s.count)*100).toFixed(0)}% win rate`} />
        <StatBox label="Avg Day 7" value={p2(s.avgDay7)}
          color={pclr(s.avgDay7)} />
        <StatBox label="Total P&L" value={p2(s.totalPnl)}
          color={pclr(s.totalPnl)} sub="sum of all returns" />
      </div>

      <AccuracyBar pct={s.accuracy} />
    </div>
  )
}

// Recent calls table
function RecentCalls({ ipos }: { ipos: any[] }) {
  const listed = ipos
    .filter(i => i.return_listing_open != null || i.listing_gain != null)
    .sort((a, b) => new Date(b.listing_date ?? 0).getTime() -
                    new Date(a.listing_date ?? 0).getTime())
    .slice(0, 20)

  if (!listed.length) return (
    <div style={{ padding:24, textAlign:"center", color:C.textMeta, fontSize:12 }}>
      No listed IPOs with return data yet.
    </div>
  )

  return (
    <div style={{ overflowX:"auto" }}>
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr style={{ background:"#F8FAFC" }}>
            {["IPO","Play","Listing Date","Open Return","Day 7","Result"].map(h => (
              <th key={h} style={{ padding:"8px 12px", textAlign:"left", fontSize:10,
                color:C.textMeta, textTransform:"uppercase", letterSpacing:"0.05em",
                borderBottom:`1px solid ${C.border}`, fontWeight:600, whiteSpace:"nowrap" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {listed.map((ipo, i) => {
            const ret  = n(ipo.return_listing_open ?? ipo.listing_gain)
            const day7 = n(ipo.return_day7)
            const play = ipo.play_recommendation ?? "—"
            const color = PLAY_COLOR[play] ?? C.textSub
            const won = ret > 5
            return (
              <tr key={ipo.id ?? i}
                style={{ borderBottom:`1px solid ${i===listed.length-1?"transparent":"#F1F5F9"}` }}>
                <td style={{ padding:"9px 12px", fontSize:12, fontWeight:700, color:C.text }}>
                  {String(ipo.company_name ?? "").split(" ").slice(0,2).join(" ")}
                </td>
                <td style={{ padding:"9px 12px" }}>
                  <span style={{ fontSize:9, fontWeight:700, padding:"2px 6px", borderRadius:4,
                    background:color+"18", color, border:`1px solid ${color}30` }}>
                    {play.replace(/_/g," ")}
                  </span>
                </td>
                <td style={{ padding:"9px 12px", fontSize:11, color:C.textMeta }}>
                  {ipo.listing_date ?? "—"}
                </td>
                <td style={{ padding:"9px 12px", fontSize:12, fontWeight:700, color:pclr(ret) }}>
                  {ret !== 0 ? p2(ret) : "—"}
                </td>
                <td style={{ padding:"9px 12px", fontSize:12, color:pclr(day7) }}>
                  {day7 !== 0 ? p2(day7) : "—"}
                </td>
                <td style={{ padding:"9px 12px" }}>
                  <span style={{ fontSize:10, fontWeight:700,
                    color: won ? C.green : ret < 0 ? C.red : C.amber }}>
                    {won ? "✅ Win" : ret < 0 ? "❌ Loss" : "⚠ Small"}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function RoiTracker() {
  const [ipos,    setIpos]    = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState<"overview"|"calls">("overview")

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

  const listed = ipos.filter(i =>
    (i.return_listing_open != null || i.listing_gain != null) && i.listing_date)
  const stats  = computeStats(listed)
  const totalIpos = listed.length
  const overallWin = totalIpos > 0
    ? (listed.filter(i => n(i.return_listing_open ?? i.listing_gain) > 5).length / totalIpos) * 100
    : 0
  const overallAvg = totalIpos > 0
    ? listed.reduce((s, i) => s + n(i.return_listing_open ?? i.listing_gain), 0) / totalIpos
    : 0

  const Sk = ({ h=40 }) => <div style={{ background:"#F1F5F9", borderRadius:10,
    height:h, marginBottom:8, opacity:.7 }} />

  return (
    <div style={{ background:C.bg, minHeight:"100vh", paddingBottom:80 }}>
      <div style={{ maxWidth:720, margin:"0 auto", padding:"16px 16px 0" }}>

        {/* Header */}
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
          <div>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <Target size={18} color={C.blue} />
              <div style={{ fontSize:20, fontWeight:900, color:C.text }}>ROI Tracker</div>
            </div>
            <div style={{ fontSize:11, color:C.textMeta }}>Engine calls vs actual outcomes · All listed IPOs</div>
          </div>
          <button onClick={load} style={{ display:"flex", alignItems:"center", gap:4,
            padding:"6px 12px", borderRadius:8, border:`1px solid ${C.border}`,
            background:C.surface, fontSize:11, color:C.textSub, cursor:"pointer" }}>
            <RefreshCw size={11} /> Refresh
          </button>
        </div>

        {/* Overall stats */}
        {!loading && totalIpos > 0 && (
          <div style={{ background:"linear-gradient(135deg,#0f172a,#1e3a5f)",
            borderRadius:14, padding:"14px 18px", marginBottom:14,
            display:"flex", gap:20, flexWrap:"wrap", alignItems:"center" }}>
            <div>
              <div style={{ fontSize:10, color:"#475569", textTransform:"uppercase",
                letterSpacing:"0.1em", marginBottom:2 }}>Engine overall</div>
              <div style={{ fontSize:28, fontWeight:900, color:"#F8FAFC" }}>
                {overallAvg >= 0 ? "+" : ""}{overallAvg.toFixed(1)}% avg
              </div>
            </div>
            {[
              { l:"IPOs tracked", v:String(totalIpos)     },
              { l:">5% accuracy", v:`${overallWin.toFixed(0)}%` },
              { l:"Best play",    v:stats[0]?.play.replace(/_/g," ").split(" ").slice(0,2).join(" ") ?? "—" },
            ].map(s => (
              <div key={s.l} style={{ textAlign:"center" }}>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:2 }}>{s.l}</div>
                <div style={{ fontSize:18, fontWeight:900, color:"#f8fafc" }}>{s.v}</div>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div style={{ display:"flex", gap:6, marginBottom:14 }}>
          {([["overview","📊 By Play"],["calls","📋 All Calls"]] as const).map(([id,label]) => (
            <button key={id} onClick={() => setTab(id)} style={{
              padding:"6px 14px", borderRadius:20, fontSize:11, cursor:"pointer",
              border:`1px solid ${tab===id?C.blue:C.border}`,
              background:tab===id?C.blueBg:C.surface,
              color:tab===id?C.blue:C.textSub,
              fontWeight:tab===id?700:400,
            }}>{label}</button>
          ))}
        </div>

        {loading ? [1,2,3].map(i => <Sk key={i} h={120} />) :
         tab === "overview" ? (
          stats.length === 0 ? (
            <div style={{ padding:48, textAlign:"center", color:C.textMeta }}>
              <TrendingUp size={32} color="#CBD5E1" style={{ margin:"0 auto 12px", display:"block" }} />
              <div style={{ fontSize:14 }}>No listed IPOs with return data yet.</div>
              <div style={{ fontSize:12, marginTop:6 }}>
                Returns populate as IPOs list and return_listing_open is recorded.
              </div>
            </div>
          ) : stats.map(s => <PlayCard key={s.play} s={s} />)
         ) : (
          <div style={{ background:C.surface, border:`1px solid ${C.border}`,
            borderRadius:14, overflow:"hidden" }}>
            <div style={{ padding:"12px 16px", borderBottom:`1px solid ${C.border}` }}>
              <div style={{ fontSize:13, fontWeight:700, color:C.text }}>
                All calls — most recent first
              </div>
            </div>
            <RecentCalls ipos={ipos} />
          </div>
         )}

        <div style={{ fontSize:10, color:"#CBD5E1", textAlign:"center",
          marginTop:8, lineHeight:1.6 }}>
          Returns = return_listing_open from ipo_intelligence · Win = &gt;5% gain ·
          Not financial advice
        </div>
      </div>
    </div>
  )
}
