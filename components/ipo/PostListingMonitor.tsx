"use client"
import { useState, useEffect } from "react"

const C = { green:"#15803d", greenBg:"#f0fdf4", amber:"#b45309", amberBg:"#fefce8", red:"#b91c1c", redBg:"#fef2f2", blue:"#1d4ed8", blueBg:"#eff6ff", gray:"#6b7280", grayBg:"#f9fafb", purple:"#7c3aed", purpleBg:"#f5f3ff" }

const sigColor = (s:string) =>
  s==="BUY AFTER LISTING"?[C.green,C.greenBg]:s==="ACCUMULATE"?[C.blue,C.blueBg]:[C.gray,C.grayBg]

export default function PostListingMonitor() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/ipo/monitor").then(r=>r.json()).then(d=>{setData(d);setLoading(false)}).catch(()=>setLoading(false))
  }, [])

  if (loading) return <div style={{ padding:20, textAlign:"center", color:C.gray, fontSize:12 }}>Loading post-listing opportunities…</div>
  if (!data) return null

  const opps = data.postListingOpportunities || []
  const buys = opps.filter((o:any) => o.signal === "BUY AFTER LISTING")
  const acc  = opps.filter((o:any) => o.signal === "ACCUMULATE")
  const watch= opps.filter((o:any) => o.signal === "WATCHLIST")

  return (
    <div style={{ border:"1px solid #e5e7eb", borderRadius:14, overflow:"hidden", background:"#fff", marginBottom:12 }}>
      {/* Header */}
      <div style={{ background:"#0f172a", padding:"12px 16px" }}>
        <div style={{ fontSize:11, fontWeight:900, color:"#f8fafc", letterSpacing:"0.06em" }}>POST-LISTING OPPORTUNITY MONITOR</div>
        <div style={{ fontSize:9, color:"#475569", marginTop:1 }}>
          IPOs that listed weak but have strong fundamentals — future Kaynes / NSDL patterns
        </div>
      </div>

      {/* Stats */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:0, borderBottom:"1px solid #f3f4f6" }}>
        {[
          { l:"Buy After Listing", v:buys.length,  c:C.green,  bg:C.greenBg },
          { l:"Accumulate",        v:acc.length,   c:C.blue,   bg:C.blueBg  },
          { l:"Watchlist",         v:watch.length, c:C.gray,   bg:C.grayBg  },
        ].map(s => (
          <div key={s.l} style={{ padding:"10px 0", textAlign:"center", background:s.bg, borderRight:"1px solid #f3f4f6" }}>
            <div style={{ fontSize:20, fontWeight:900, color:s.c }}>{s.v}</div>
            <div style={{ fontSize:8, color:C.gray, textTransform:"uppercase" }}>{s.l}</div>
          </div>
        ))}
      </div>

      <div style={{ padding:"12px 16px" }}>
        {opps.length === 0 && <div style={{ fontSize:11, color:C.gray }}>No post-listing opportunities identified currently.</div>}
        {opps.map((o:any, i:number) => {
          const [fg, bg] = sigColor(o.signal)
          return (
            <div key={i} style={{ display:"flex", alignItems:"center", gap:10, padding:"9px 11px", background:C.grayBg, borderRadius:9, marginBottom:5 }}>
              <div style={{ flex:1 }}>
                <div style={{ display:"flex", gap:6, alignItems:"center", marginBottom:3 }}>
                  <span style={{ fontSize:12, fontWeight:700, color:"#111827" }}>{o.name}</span>
                  <span style={{ fontSize:8, color:C.gray }}>{o.year} · {o.sector}</span>
                </div>
                <div style={{ fontSize:10, color:C.gray, lineHeight:1.5 }}>{o.reason}</div>
              </div>
              <div style={{ display:"flex", flexDirection:"column", gap:4, alignItems:"flex-end", flexShrink:0 }}>
                <span style={{ padding:"2px 8px", borderRadius:99, fontSize:9, fontWeight:800, background:bg, color:fg }}>{o.signal}</span>
                <div style={{ display:"flex", gap:8 }}>
                  <div style={{ textAlign:"right" }}>
                    <div style={{ fontSize:7, color:C.gray }}>D1</div>
                    <div style={{ fontSize:11, fontWeight:700, color:o.listingGain>=0?C.green:C.red }}>{o.listingGain>=0?"+":""}{Number(o.listingGain).toFixed(1)}%</div>
                  </div>
                  <div style={{ textAlign:"right" }}>
                    <div style={{ fontSize:7, color:C.gray }}>6M</div>
                    <div style={{ fontSize:11, fontWeight:700, color:o.m6Return>=0?C.green:C.red }}>{o.m6Return>=0?"+":""}{Number(o.m6Return).toFixed(1)}%</div>
                  </div>
                  <div style={{ textAlign:"right" }}>
                    <div style={{ fontSize:7, color:C.gray }}>Score</div>
                    <div style={{ fontSize:11, fontWeight:700, color:C.purple }}>{o.ipoScore}</div>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Phase 2 features */}
      <div style={{ borderTop:"1px solid #f3f4f6", padding:"8px 16px", background:"#fafafa" }}>
        <div style={{ fontSize:9, color:C.gray }}>
          Phase 2 (paid): Smart Money Tracker · Anchor Lock-in Alerts · Institutional buying signals · Volume expansion alerts
        </div>
      </div>
    </div>
  )
}

