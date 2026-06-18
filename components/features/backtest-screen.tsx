"use client"
// components/features/backtest-screen.tsx
// IPO Backtest UI — runs historical strategy analysis

import { useState, useCallback } from "react"
import { RefreshCw, Play, BarChart2, TrendingUp, AlertTriangle } from "lucide-react"

const C = {
  green:"#16A34A",greenBg:"#F0FDF4",blue:"#2563EB",blueBg:"#EFF6FF",
  amber:"#D97706",amberBg:"#FFFBEB",red:"#DC2626",redBg:"#FEF2F2",
  purple:"#7C3AED",purpleBg:"#F5F3FF",gray:"#6B7280",grayBg:"#F9FAFB",
  text:"#111827",border:"#E5E7EB",surface:"#FFFFFF",
}
const n = (v: unknown) => parseFloat(String(v||0))||0

function Stat({ label, value, color=C.text }: { label:string; value:string; color?:string }) {
  return (
    <div style={{background:C.grayBg,borderRadius:10,padding:"10px 14px",border:`1px solid ${C.border}`}}>
      <div style={{fontSize:10,color:C.gray,marginBottom:3,fontWeight:600,textTransform:"uppercase" as const,letterSpacing:"0.05em"}}>{label}</div>
      <div style={{fontSize:22,fontWeight:800,color}}>{value}</div>
    </div>
  )
}

export function BacktestScreen() {
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState<any>(null)
  const [error,   setError]   = useState<string|null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [runName, setRunName] = useState("")
  const [yearFrom, setYearFrom] = useState(2020)
  const [yearTo,   setYearTo]   = useState(2024)

  const loadHistory = useCallback(async () => {
    const r = await fetch("/api/backtest").then(d=>d.json()).catch(()=>null)
    if (r?.ok) setHistory(r.runs||[])
  }, [])

  const runBacktest = async () => {
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await fetch("/api/backtest", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          runName: runName || `Backtest ${new Date().toLocaleDateString("en-IN")}`,
          filters: { yearFrom, yearTo },
        })
      })
      const d = await r.json()
      if (!r.ok || d.error) { setError(d.error||"Backtest failed"); return }
      setResult(d)
      await loadHistory()
    } catch (e:any) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div style={{background:"#FAFAF8",minHeight:"100vh",paddingBottom:80}}>
      <div style={{maxWidth:860,margin:"0 auto",padding:"16px 16px 0"}}>

        <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16}}>
          <BarChart2 size={20} color={C.blue}/>
          <span style={{fontSize:20,fontWeight:800,color:C.text}}>IPO Backtest Engine</span>
        </div>

        {/* Config panel */}
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:14,padding:18,marginBottom:14}}>
          <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:12}}>Run configuration</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 2fr auto",gap:10,alignItems:"end"}}>
            <div>
              <div style={{fontSize:11,color:C.gray,marginBottom:4}}>Year from</div>
              <input type="number" value={yearFrom} onChange={e=>setYearFrom(+e.target.value)} min={2015} max={2024}
                style={{width:"100%",padding:"8px 10px",borderRadius:8,border:`1px solid ${C.border}`,fontSize:13}}/>
            </div>
            <div>
              <div style={{fontSize:11,color:C.gray,marginBottom:4}}>Year to</div>
              <input type="number" value={yearTo} onChange={e=>setYearTo(+e.target.value)} min={2015} max={2025}
                style={{width:"100%",padding:"8px 10px",borderRadius:8,border:`1px solid ${C.border}`,fontSize:13}}/>
            </div>
            <div>
              <div style={{fontSize:11,color:C.gray,marginBottom:4}}>Run name (optional)</div>
              <input type="text" value={runName} onChange={e=>setRunName(e.target.value)} placeholder="My backtest run"
                style={{width:"100%",padding:"8px 10px",borderRadius:8,border:`1px solid ${C.border}`,fontSize:13}}/>
            </div>
            <button onClick={runBacktest} disabled={loading}
              style={{display:"flex",alignItems:"center",gap:6,padding:"8px 18px",borderRadius:8,border:"none",background:loading?C.grayBg:C.blue,color:loading?C.gray:"#fff",fontSize:13,fontWeight:700,cursor:loading?"not-allowed":"pointer"}}>
              {loading ? <RefreshCw size={14} className="animate-spin"/> : <Play size={14}/>}
              {loading?"Running…":"Run"}
            </button>
          </div>
        </div>

        {error && (
          <div style={{background:C.redBg,border:`1px solid #FCA5A5`,borderRadius:10,padding:12,marginBottom:14,display:"flex",gap:8,alignItems:"center"}}>
            <AlertTriangle size={14} color={C.red}/>
            <span style={{fontSize:12,color:C.red}}>{error}</span>
          </div>
        )}

        {result && (
          <div style={{marginBottom:16}}>
            <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:10}}>
              Results — {result.sampleSize} IPOs ({result.dateRange})
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:14}}>
              {result.strategies?.slice(0,4).map((s:any) => (
                <div key={s.strategy} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:14}}>
                  <div style={{fontSize:10,color:C.gray,marginBottom:6,fontWeight:600}}>{s.strategy.replace(/_/g," ").toUpperCase()}</div>
                  <div style={{fontSize:22,fontWeight:800,color:n(s.winRate)>=70?C.green:n(s.winRate)>=55?C.amber:C.red}}>
                    {s.winRate}%
                  </div>
                  <div style={{fontSize:11,color:C.gray}}>Win rate</div>
                  <div style={{marginTop:8,display:"grid",gridTemplateColumns:"1fr 1fr",gap:6}}>
                    <div><div style={{fontSize:9,color:C.gray}}>Avg return</div><div style={{fontSize:12,fontWeight:700,color:C.green}}>+{n(s.avgReturn).toFixed(1)}%</div></div>
                    <div><div style={{fontSize:9,color:C.gray}}>Drawdown</div><div style={{fontSize:12,fontWeight:700,color:C.red}}>{n(s.maxDrawdown).toFixed(1)}%</div></div>
                    <div><div style={{fontSize:9,color:C.gray}}>Sample</div><div style={{fontSize:12,fontWeight:700}}>{s.sampleSize}</div></div>
                  </div>
                </div>
              ))}
            </div>

            {result.weightCalibration?.length > 0 && (
              <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:14}}>
                <div style={{fontSize:12,fontWeight:700,color:C.text,marginBottom:10}}>Weight calibration recommendations</div>
                {result.weightCalibration.map((c:any) => (
                  <div key={c.name} style={{display:"flex",justifyContent:"space-between",padding:"6px 0",borderBottom:`1px solid ${C.border}`,fontSize:12}}>
                    <span style={{color:C.text,fontWeight:600}}>{c.name}</span>
                    <span style={{color:C.gray}}>Current: {n(c.currentWeight).toFixed(0)}% → <strong style={{color:C.blue}}>{n(c.suggestedWeight).toFixed(0)}%</strong></span>
                    <span style={{color:C.gray,fontSize:10,maxWidth:200,textAlign:"right" as const}}>{c.reason}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* History */}
        {history.length > 0 && (
          <div>
            <div style={{fontSize:13,fontWeight:700,color:C.text,marginBottom:10}}>Previous runs</div>
            {history.map((r:any) => (
              <div key={r.id} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:10,padding:"10px 14px",marginBottom:8,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <div>
                  <div style={{fontSize:13,fontWeight:700,color:C.text}}>{r.run_name}</div>
                  <div style={{fontSize:11,color:C.gray}}>{r.sample_size} IPOs · {new Date(r.created_at).toLocaleDateString("en-IN")}</div>
                </div>
                <div style={{display:"flex",gap:16,fontFamily:"monospace",fontSize:12}}>
                  <span style={{color:C.green}}>Win: {r.win_rate}%</span>
                  <span style={{color:C.blue}}>Avg: +{n(r.avg_return).toFixed(1)}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
