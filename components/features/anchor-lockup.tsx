"use client"
// components/features/anchor-lockup.tsx
// Tracks 30-day and 90-day anchor lock-in expiry dates.
// Dates derived from IPO listing month (approximate — assumes mid-month listing).
// Renders inside IPO tab.

import { useState, useEffect } from "react"

// ── Date helpers ──────────────────────────────────────────────────────────────

function parseListingDate(listing: string | undefined): Date | null {
  if (!listing) return null
  const match = listing.match(/([A-Za-z]+)\s+'?(\d{2,4})/)
  if (!match) return null
  const months: Record<string, number> = {
    Jan:0, Feb:1, Mar:2, Apr:3, May:4, Jun:5,
    Jul:6, Aug:7, Sep:8, Oct:9, Nov:10, Dec:11
  }
  const month = months[match[1]]
  const year  = parseInt(match[2].length === 2 ? "20" + match[2] : match[2])
  return isNaN(month) || isNaN(year) ? null : new Date(year, month, 10)
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d); r.setDate(r.getDate() + n); return r
}

function daysFrom(d: Date): number {
  return Math.round((d.getTime() - Date.now()) / 864e5)
}

function fmtDate(d: Date): string {
  return d.toLocaleDateString("en-IN", { day:"numeric", month:"short", year:"numeric" })
}

function urgency(days: number): { c: string; bg: string; bd: string; label: string } {
  if (days < 0)   return { c:"#9CA3AF", bg:"#F9FAFB", bd:"#E5E7EB", label:"Expired" }
  if (days <= 5)  return { c:"#DC2626", bg:"#FEF2F2", bd:"#FECACA", label:"Imminent" }
  if (days <= 21) return { c:"#D97706", bg:"#FFFBEB", bd:"#FDE68A", label:"Soon" }
  return            { c:"#2563EB", bg:"#EFF6FF", bd:"#BFDBFE", label:"Upcoming" }
}

const TIER1_KEYWORDS = [
  "BlackRock","Vanguard","GIC","Temasek","Norges","CPPIB",
  "SBI MF","HDFC MF","ICICI Pru","Nippon","Axis MF","Kotak MF",
  "Fidelity","Nomura","Goldman","Morgan Stanley","Wellington","LIC",
]

function countTier1(anchors: string[]): number {
  return anchors.filter(a => TIER1_KEYWORDS.some(k => a.includes(k))).length
}

// ── Component ─────────────────────────────────────────────────────────────────

export function AnchorLockupTracker() {
  const [ipos,    setIpos]    = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/ipo")
      .then(r  => r.json())
      .then(d  => { setIpos(d.ipos || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return null

  // Build lock-up events only for IPOs with anchor data + parseable listing dates
  const events = ipos
    .filter(ipo => ipo.anchors?.length && ipo.listing)
    .map(ipo => {
      const listDate  = parseListingDate(ipo.listing)
      if (!listDate) return null
      const d30       = addDays(listDate, 30)
      const d90       = addDays(listDate, 90)
      const t1Count   = countTier1(ipo.anchors)
      return {
        name: ipo.name, sector: ipo.sector,
        listing: ipo.listing, listDate,
        d30, d90,
        days30: daysFrom(d30), days90: daysFrom(d90),
        anchorCount: ipo.anchors.length, tier1Count: t1Count,
        listingScore: ipo.score?.listingScore || 0,
      }
    })
    .filter(Boolean) as any[]

  // Sort by nearest non-expired event
  events.sort((a, b) => {
    const nearA = [a.days30, a.days90].filter(d => d >= 0).reduce((m, v) => Math.min(m, v), Infinity)
    const nearB = [b.days30, b.days90].filter(d => d >= 0).reduce((m, v) => Math.min(m, v), Infinity)
    return nearA - nearB
  })

  if (!events.length) return null

  const hasImminent = events.some(e => (e.days30 >= 0 && e.days30 <= 5) || (e.days90 >= 0 && e.days90 <= 5))

  return (
    <div style={{ background:"#fff", border:`1px solid ${hasImminent ? "#FECACA" : "#E5E7EB"}`, borderRadius:14, padding:16, marginBottom:14 }}>

      {/* Header */}
      <div style={{ marginBottom:14 }}>
        <div style={{ fontSize:14, fontWeight:700, color:"#111827", marginBottom:3 }}>
          ⏰ Anchor Lock-in Tracker
          {hasImminent && <span style={{ marginLeft:8, fontSize:11, fontWeight:700, color:"#DC2626", background:"#FEF2F2", padding:"2px 8px", borderRadius:4 }}>⚠ UNLOCK IMMINENT</span>}
        </div>
        <div style={{ fontSize:11, color:"#6B7280" }}>
          30-day (50% of anchor allotment) and 90-day (remaining 50%) unlock dates.
          Dates approximate — based on expected mid-month listing.
        </div>
      </div>

      {/* Event cards */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(290px,1fr))", gap:10, marginBottom:12 }}>
        {events.map(ev => {
          const u30 = urgency(ev.days30)
          const u90 = urgency(ev.days90)
          const sellingRisk = ev.tier1Count >= 3 ? "LOW (Tier-1 holders tend to hold)" : ev.tier1Count >= 1 ? "MODERATE" : "HIGH (mostly AIF/PMS)"
          const sellingRiskColor = ev.tier1Count >= 3 ? "#16A34A" : ev.tier1Count >= 1 ? "#D97706" : "#DC2626"

          return (
            <div key={ev.name} style={{ background:"#F9FAFB", border:"1px solid #E5E7EB", borderRadius:10, padding:"13px 14px" }}>
              {/* Name */}
              <div style={{ fontSize:13, fontWeight:700, color:"#111827", marginBottom:2, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                {ev.name}
              </div>
              <div style={{ fontSize:10, color:"#9CA3AF", marginBottom:10 }}>
                Listed ~{ev.listing} · {ev.tier1Count} Tier-1 / {ev.anchorCount} anchors
              </div>

              {/* Unlock dates */}
              <div style={{ display:"flex", gap:8, marginBottom:10 }}>
                {/* 30-day */}
                <div style={{ flex:1, background:u30.bg, border:`1px solid ${u30.bd}`, borderRadius:8, padding:"9px 10px" }}>
                  <div style={{ fontSize:9, color:"#9CA3AF", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:4 }}>30-Day Unlock</div>
                  <div style={{ fontSize:16, fontWeight:900, color:u30.c, lineHeight:1, marginBottom:2 }}>
                    {ev.days30 < 0 ? "✓ Done" : ev.days30 === 0 ? "Today" : `${ev.days30}d`}
                  </div>
                  <div style={{ fontSize:9, color:u30.c, fontWeight:600, marginBottom:3 }}>{u30.label}</div>
                  <div style={{ fontSize:9, color:"#6B7280" }}>{fmtDate(ev.d30)}</div>
                </div>
                {/* 90-day */}
                <div style={{ flex:1, background:u90.bg, border:`1px solid ${u90.bd}`, borderRadius:8, padding:"9px 10px" }}>
                  <div style={{ fontSize:9, color:"#9CA3AF", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:4 }}>90-Day Unlock</div>
                  <div style={{ fontSize:16, fontWeight:900, color:u90.c, lineHeight:1, marginBottom:2 }}>
                    {ev.days90 < 0 ? "✓ Done" : ev.days90 === 0 ? "Today" : `${ev.days90}d`}
                  </div>
                  <div style={{ fontSize:9, color:u90.c, fontWeight:600, marginBottom:3 }}>{u90.label}</div>
                  <div style={{ fontSize:9, color:"#6B7280" }}>{fmtDate(ev.d90)}</div>
                </div>
              </div>

              {/* Selling pressure */}
              <div style={{ fontSize:10, color:"#6B7280" }}>
                Selling risk: <span style={{ fontWeight:700, color:sellingRiskColor }}>{sellingRisk}</span>
              </div>

              {/* Alert */}
              {ev.days30 >= 0 && ev.days30 <= 5 && (
                <div style={{ marginTop:8, padding:"5px 9px", background:"#FEF2F2", border:"1px solid #FECACA", borderRadius:6, fontSize:10, color:"#DC2626", fontWeight:600 }}>
                  🚨 30-day unlock in {ev.days30 === 0 ? "hours" : `${ev.days30} day${ev.days30 === 1 ? "" : "s"}`} — watch order book depth
                </div>
              )}
              {ev.days90 >= 0 && ev.days90 <= 5 && (
                <div style={{ marginTop:8, padding:"5px 9px", background:"#FFFBEB", border:"1px solid #FDE68A", borderRadius:6, fontSize:10, color:"#D97706", fontWeight:600 }}>
                  ⚠ Full unlock in {ev.days90 === 0 ? "hours" : `${ev.days90} day${ev.days90 === 1 ? "" : "s"}`} — {ev.tier1Count >= 2 ? "reduced" : "elevated"} exit risk
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ padding:"8px 12px", background:"#F0F9FF", border:"1px solid #BAE6FD", borderRadius:8, fontSize:10, color:"#0369A1", lineHeight:1.6 }}>
        📌 <strong>Strategy:</strong> 30-day unlock = buy dips caused by panic selling (real investors, not flippers, exit here).
        90-day unlock = if stock has held above issue price, it's a conviction hold signal from remaining anchors.
        Tier-1 anchor presence halves expected selling pressure.
      </div>
    </div>
  )
}
