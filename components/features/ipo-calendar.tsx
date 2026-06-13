"use client"
// components/features/ipo-calendar.tsx
// Timeline of all IPOs: open, upcoming, recently listed.
// Fetches /api/ipo — renders above the IPO list in the IPO tab.

import { useState, useEffect } from "react"

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function daysUntil(d: Date | null): number | null {
  if (!d) return null
  return Math.round((d.getTime() - Date.now()) / 864e5)
}

function recColor(rec: string | undefined) {
  if (!rec) return "#6B7280"
  if (rec.includes("Aggressively")) return "#16A34A"
  if (rec.includes("Avoid"))        return "#DC2626"
  if (rec.includes("Trade"))        return "#0891B2"
  if (rec.includes("Watch"))        return "#D97706"
  return "#2563EB"
}

// ── Component ─────────────────────────────────────────────────────────────────

export function IpoCalendar() {
  const [ipos,    setIpos]    = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/ipo")
      .then(r  => r.json())
      .then(d  => { setIpos(d.ipos || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ textAlign:"center", padding:20, color:"#9CA3AF", fontSize:12 }}>
      Loading IPO calendar…
    </div>
  )
  if (!ipos.length) return null

  const active  = ipos.filter(i => i.status === "OPEN" || i.status === "UPCOMING")
  const listed  = ipos.filter(i => i.status === "LISTED").slice(0, 3)

  return (
    <div style={{ background:"#fff", border:"1px solid #E5E7EB", borderRadius:14, padding:16, marginBottom:14 }}>

      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14 }}>
        <div style={{ fontSize:14, fontWeight:700, color:"#111827" }}>📅 IPO Calendar</div>
        <div style={{ fontSize:11, color:"#6B7280" }}>
          {active.length} active · {listed.length} recently listed
        </div>
      </div>

      {/* Active / Upcoming */}
      {active.length > 0 && (
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:600, color:"#6B7280", textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:8 }}>
            Open &amp; Upcoming
          </div>
          {active.map(ipo => {
            const listDate    = parseListingDate(ipo.listing)
            const daysToList  = daysUntil(listDate)
            const s           = ipo.score || {}
            const ip          = ipo.priceBandHigh || ipo.priceBandLow || 0
            const gmpEntry    = ipo.gmpPrice ? ip + ipo.gmpPrice : null
            const isOpen      = ipo.status === "OPEN"
            const rc          = recColor(s.recommendation)
            const scoreColor  = (s.listingScore || 0) >= 70 ? "#16A34A"
                              : (s.listingScore || 0) >= 50 ? "#2563EB" : "#6B7280"

            return (
              <div key={ipo.name} style={{
                display:"flex", alignItems:"center", gap:12,
                padding:"11px 13px", marginBottom:7, borderRadius:10,
                background: isOpen ? "#F0FDF4" : "#EFF6FF",
                border: `1px solid ${isOpen ? "#BBF7D0" : "#BFDBFE"}`,
                flexWrap:"wrap",
              }}>
                {/* Status pill */}
                <div style={{
                  padding:"3px 9px", borderRadius:20, fontSize:10, fontWeight:700,
                  background: isOpen ? "#16A34A" : "#2563EB", color:"#fff", flexShrink:0,
                }}>
                  {ipo.status}
                </div>

                {/* Name + sector */}
                <div style={{ flex:"2 1 140px", minWidth:0 }}>
                  <div style={{ fontSize:13, fontWeight:700, color:"#111827", marginBottom:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                    {ipo.name}
                  </div>
                  <div style={{ fontSize:10, color:"#6B7280" }}>{ipo.sector} · ₹{ipo.issueSize}Cr</div>
                </div>

                {/* Listing date */}
                <div style={{ textAlign:"center", flexShrink:0 }}>
                  <div style={{ fontSize:9, color:"#9CA3AF", marginBottom:2 }}>LISTING</div>
                  <div style={{ fontSize:12, fontWeight:600, color:"#374151" }}>{ipo.listing || "TBD"}</div>
                  {daysToList !== null && daysToList >= 0 && (
                    <div style={{ fontSize:10, color: daysToList <= 7 ? "#DC2626" : "#6B7280", fontWeight:600 }}>
                      {daysToList === 0 ? "Today!" : `in ${daysToList}d`}
                    </div>
                  )}
                </div>

                {/* Price band */}
                <div style={{ textAlign:"center", flexShrink:0 }}>
                  <div style={{ fontSize:9, color:"#9CA3AF", marginBottom:2 }}>BAND</div>
                  <div style={{ fontSize:12, fontWeight:600, color:"#374151" }}>{ipo.band || `₹${ip}`}</div>
                </div>

                {/* GMP */}
                {gmpEntry && (
                  <div style={{ textAlign:"center", flexShrink:0 }}>
                    <div style={{ fontSize:9, color:"#9CA3AF", marginBottom:2 }}>GMP ENTRY</div>
                    <div style={{ fontSize:12, fontWeight:700, color:"#16A34A" }}>₹{Math.round(gmpEntry)}</div>
                    <div style={{ fontSize:10, color:"#16A34A" }}>GMP +₹{ipo.gmpPrice}</div>
                  </div>
                )}

                {/* Score */}
                <div style={{ textAlign:"center", flexShrink:0 }}>
                  <div style={{ fontSize:9, color:"#9CA3AF", marginBottom:2 }}>SCORE</div>
                  <div style={{ fontSize:22, fontWeight:900, color:scoreColor, lineHeight:1 }}>
                    {s.listingScore ?? "—"}
                  </div>
                </div>

                {/* Recommendation */}
                {s.recommendation && (
                  <div style={{
                    padding:"4px 9px", borderRadius:6, fontSize:10, fontWeight:700,
                    color:rc, background:rc + "18", border:`1px solid ${rc}30`,
                    flexShrink:0, maxWidth:100, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                  }}>
                    {s.recommendation.split("—")[0].trim().split(" ").slice(0, 2).join(" ")}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Recently listed */}
      {listed.length > 0 && (
        <div>
          <div style={{ fontSize:10, fontWeight:600, color:"#6B7280", textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:8 }}>
            Recently Listed
          </div>
          <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
            {listed.map(ipo => {
              const s = ipo.score || {}
              return (
                <div key={ipo.name} style={{
                  flex:"1 1 180px", padding:"10px 12px",
                  background:"#F9FAFB", border:"1px solid #E5E7EB", borderRadius:9,
                }}>
                  <div style={{ fontSize:12, fontWeight:700, color:"#6B7280", marginBottom:2, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                    {ipo.name}
                  </div>
                  <div style={{ fontSize:10, color:"#9CA3AF", marginBottom:8 }}>{ipo.listing} · {ipo.sector}</div>
                  <div style={{ display:"flex", gap:10, alignItems:"baseline" }}>
                    <span style={{ fontSize:16, fontWeight:900, color:(s.listingScore||0)>=60?"#16A34A":"#6B7280" }}>
                      {s.listingScore ?? "—"}
                    </span>
                    <span style={{ fontSize:10, color:"#9CA3AF" }}>listing score</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
