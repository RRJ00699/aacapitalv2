"use client"
import { useState } from "react"
import Loader from "@/components/shared/Loader"

export default function MarketPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)

  const fetchMarket = async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/market")
      const json = await res.json()
      setData(json.data)
      setFetched(true)
    } catch { }
    setLoading(false)
  }

  const pcr = data?.niftyPcr?.value || 0
  const vix = data?.vix?.value || 0
  const pcrColor = pcr<0.7?"#16a34a":pcr<0.9?"#059669":pcr<1.1?"#d97706":pcr<1.2?"#ea580c":"#dc2626"
  const pcrSignal = pcr<0.7?"STRONG BUY":pcr<0.9?"BUY ZONE":pcr<1.1?"NEUTRAL":pcr<1.2?"CAUTION":"SELL SIGNAL"
  const vixColor = vix<14?"#16a34a":vix<16?"#d97706":vix<20?"#ea580c":"#dc2626"

  return (
    <div style={{ maxWidth:900, margin:"0 auto", padding:16 }}>
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", marginBottom:16, flexWrap:"wrap", gap:10 }}>
        <div>
          <div style={{ fontWeight:800, fontSize:22, color:"#111827", marginBottom:4 }}>📡 Market Pulse</div>
          <div style={{ fontSize:10, color:"#9ca3af" }}>PCR · India VIX · Nifty · Bank Nifty — live signals</div>
        </div>
        <button onClick={fetchMarket} disabled={loading} style={{ padding:"9px 20px", background:"#0f172a", border:"none", borderRadius:8, color:"#fff", fontWeight:600, fontSize:13, cursor:"pointer", display:"flex", alignItems:"center", gap:8, opacity:loading?0.7:1 }}>
          {loading?<div className="spin" style={{ width:14, height:14, border:"2px solid #475569", borderTopColor:"#fff", borderRadius:"50%" }}/>:"🔄"}
          {loading?"Fetching...":"Fetch Live Data"}
        </button>
      </div>

      {!fetched && !loading && (
        <div style={{ textAlign:"center", padding:"60px 20px" }}>
          <div style={{ fontSize:48, marginBottom:16 }}>📡</div>
          <div style={{ fontWeight:700, fontSize:18, color:"#374151", marginBottom:8 }}>Hit "Fetch Live Data" to load market signals</div>
          <div style={{ fontSize:11, color:"#9ca3af", lineHeight:1.7 }}>
            Pulls live India VIX and Nifty PCR.<br/>
            PCR below 0.7 = buy signal · PCR above 1.2 = sell signal<br/>
            VIX below 14 = calm · VIX above 20 = fear / buy opportunity
          </div>
        </div>
      )}

      {loading && <Loader text="Searching for live PCR and India VIX..." />}

      {fetched && data && !loading && (
        <div className="fade">
          {data.simulated && (
            <div style={{ background:"#fffbeb", border:"1px solid #fde68a", borderRadius:8, padding:"8px 14px", marginBottom:14, fontSize:10, color:"#92400e" }}>
              ⚠ Showing simulated data. Deploy backend cron for real NSE PCR + VIX.
            </div>
          )}

          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))", gap:10, marginBottom:16 }}>
            {[
              { l:"Nifty 50", v:data.nifty?.value?.toLocaleString("en-IN"), ch:data.nifty?.change, pct:data.nifty?.changePct, c:"#1d4ed8" },
              { l:"Bank Nifty", v:data.bankNifty?.value?.toLocaleString("en-IN"), ch:data.bankNifty?.change, pct:data.bankNifty?.changePct, c:"#7c3aed" },
              { l:"India VIX", v:Number(vix).toFixed(2), ch:data.vix?.change, c:vixColor, extra:data.vix?.trend },
              { l:"Nifty PCR", v:Number(pcr).toFixed(2), c:pcrColor, extra:pcrSignal },
            ].map(s => (
              <div key={s.l} style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:14 }}>
                <div style={{ fontSize:8, color:"#9ca3af", letterSpacing:"1px", textTransform:"uppercase", marginBottom:6 }}>{s.l}</div>
                <div style={{ fontSize:24, fontWeight:800, color:s.c }}>{s.v}</div>
                {s.ch!=null && <div style={{ fontSize:11, color:Number(s.ch)>=0?"#16a34a":"#dc2626", marginTop:2 }}>{Number(s.ch)>=0?"+":""}{Number(s.ch).toFixed(2)}{s.pct!=null?` (${Number(s.pct).toFixed(2)}%)`:""}</div>}
                {s.extra && <div style={{ fontSize:9, fontWeight:700, color:s.c, marginTop:3 }}>{s.extra}</div>}
              </div>
            ))}
          </div>

          <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:14, padding:18, marginBottom:14 }}>
            <div style={{ fontSize:9, color:"#9ca3af", letterSpacing:"1.5px", textTransform:"uppercase", marginBottom:14 }}>Put/Call Ratio — Market Sentiment</div>
            <div style={{ display:"flex", alignItems:"center", gap:20, flexWrap:"wrap", marginBottom:16 }}>
              <div style={{ textAlign:"center" }}>
                <div style={{ fontSize:48, fontWeight:800, color:pcrColor, lineHeight:1 }}>{pcr.toFixed(2)}</div>
                <div style={{ fontSize:9, color:"#9ca3af", marginTop:4 }}>Nifty PCR (F&O)</div>
              </div>
              <div style={{ flex:1, minWidth:200 }}>
                <div style={{ fontSize:18, fontWeight:800, color:pcrColor, marginBottom:4 }}>{pcrSignal}</div>
                <div style={{ fontSize:12, color:"#6b7280", lineHeight:1.6 }}>
                  {pcr<0.7?"Excessive put buying = retail fear. Contrarian BUY signal. Institutional buyers stepping in.":
                   pcr<0.9?"More puts than calls. Good time to accumulate quality names.":
                   pcr<1.1?"Balanced market. No strong directional signal.":
                   pcr<1.2?"Call OI building. Market getting complacent. Tighten stops.":
                   "Extreme call buying = retail euphoria. Institutional distribution likely."}
                </div>
              </div>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8 }}>
              {[
                { range:"< 0.7", signal:"⚡ STRONG BUY", c:"#16a34a", active:pcr<0.7 },
                { range:"0.7–0.9", signal:"✅ BUY ZONE", c:"#059669", active:pcr>=0.7&&pcr<0.9 },
                { range:"0.9–1.1", signal:"🟡 NEUTRAL", c:"#d97706", active:pcr>=0.9&&pcr<1.1 },
                { range:"1.1–1.2", signal:"⚠ CAUTION", c:"#ea580c", active:pcr>=1.1&&pcr<1.2 },
                { range:"> 1.2", signal:"🔴 SELL", c:"#dc2626", active:pcr>=1.2 },
              ].map(r => (
                <div key={r.range} style={{ background:r.active?`${r.c}12`:"#f9fafb", border:`2px solid ${r.active?r.c:"#e5e7eb"}`, borderRadius:10, padding:"10px 12px" }}>
                  <div style={{ fontSize:9, fontWeight:700, color:r.active?r.c:"#9ca3af", marginBottom:3 }}>{r.range}</div>
                  <div style={{ fontSize:10, fontWeight:700, color:r.active?r.c:"#9ca3af" }}>{r.signal}</div>
                  {r.active && <div style={{ marginTop:6, padding:"2px 6px", background:r.c, borderRadius:4, display:"inline-block", fontSize:8, color:"#fff", fontWeight:700 }}>NOW</div>}
                </div>
              ))}
            </div>
          </div>

          <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:14, padding:18 }}>
            <div style={{ fontSize:9, color:"#9ca3af", letterSpacing:"1.5px", textTransform:"uppercase", marginBottom:14 }}>India VIX — Fear Index</div>
            <div style={{ display:"flex", gap:20, alignItems:"flex-start", flexWrap:"wrap" }}>
              <div>
                <div style={{ fontSize:48, fontWeight:800, color:vixColor, lineHeight:1 }}>{vix.toFixed(2)}</div>
                <div style={{ fontSize:9, color:"#9ca3af", marginTop:4 }}>India VIX</div>
                <div style={{ fontSize:10, fontWeight:700, color:vixColor, marginTop:4 }}>{data.vix?.trend}</div>
              </div>
              <div style={{ flex:1, minWidth:220 }}>
                <div style={{ fontSize:14, fontWeight:700, color:vixColor, marginBottom:6 }}>
                  {vix<12?"Extreme Calm":vix<14?"Low Volatility":vix<16?"Normal":vix<20?"Elevated — Caution":vix<25?"High Fear — BUY":"Extreme Fear — MAX OPPORTUNITY"}
                </div>
                <div style={{ fontSize:12, color:"#6b7280", lineHeight:1.7 }}>
                  {vix>20?"📌 VIX above 20 = fear is high. This is where multibaggers are bought. Buy quality on dips.":"VIX normal. Continue systematic accumulation of Tier 1A setups."}
                </div>
                <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginTop:10 }}>
                  {[{r:"<12",l:"Complacency"},{r:"12–16",l:"Normal"},{r:"16–20",l:"Caution"},{r:"20–25",l:"Fear=BUY"},{r:">25",l:"Panic"}].map(z => (
                    <div key={z.r} style={{ padding:"4px 8px", borderRadius:5, background:"#f3f4f6", border:"1px solid #e5e7eb" }}>
                      <div style={{ fontSize:8, fontWeight:700, color:"#374151" }}>{z.r}</div>
                      <div style={{ fontSize:7, color:"#9ca3af" }}>{z.l}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

