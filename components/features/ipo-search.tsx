// components/features/ipo-search.tsx
// IPO search — filters the IPO Command Center by company name or symbol.
// Queries /api/ipo-command's cards client-side (already loaded) for instant results.
"use client"
import { useState, useEffect, useRef } from "react"

const BRONZE = "#B6700E", BRONZE_DK = "#A26109"
const C = { surface:"#FFFFFF", border:"#E2E8F2", text:"#1A2438", sub:"#68738C", bg:"#F4F6FA" }

interface IpoHit { company_name: string; sym?: string; playbook_setup?: string; listing_gap_pct?: number|null; ipo_status?: string }
interface Props { onSelect: (company: string) => void; placeholder?: string }

const setupColor = (s?: string) =>
  s==="stack"||s==="core" ? "#0E7A4D" : s==="avoid" ? "#C4443A" : s==="core-lite" ? "#2E5A9E" : "#68738C"

export function IpoSearch({ onSelect, placeholder = "Search IPO by name or symbol..." }: Props) {
  const [query, setQuery] = useState("")
  const [all, setAll] = useState<IpoHit[]>([])
  const [results, setResults] = useState<IpoHit[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // load the IPO list once (from the command endpoint the page already uses)
  useEffect(() => {
    let live = true
    fetch("/api/ipo-command").then(r=>r.json()).then(d => {
      if (!live) return
      const cards = (d?.cards ?? []) as IpoHit[]
      setAll(cards.map(c => ({ company_name:c.company_name, sym:(c as any).sym,
        playbook_setup:(c as any).playbook_setup, listing_gap_pct:(c as any).listing_gap_pct,
        ipo_status:(c as any).ipo_status })))
    }).catch(()=>{})
    return () => { live = false }
  }, [])

  useEffect(() => {
    function h(e: MouseEvent){ if(ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h)
  }, [])

  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 1) { setResults([]); setOpen(false); return }
    const hits = all.filter(c =>
      (c.company_name||"").toLowerCase().includes(q) || (c.sym||"").toLowerCase().includes(q)
    ).slice(0, 12)
    setResults(hits); setOpen(true)
  }, [query, all])

  function pick(company: string){ setQuery(""); setResults([]); setOpen(false); onSelect(company) }

  return (
    <div ref={ref} style={{ position:"relative", width:"100%" }}>
      <div style={{ position:"relative" }}>
        <input
          value={query}
          onChange={e=>setQuery(e.target.value)}
          onFocus={()=>{ if(results.length) setOpen(true) }}
          onKeyDown={e=>{
            if(e.key==="Escape"){ setOpen(false); setQuery("") }
            if(e.key==="Enter" && results[0]){ e.preventDefault(); pick(results[0].company_name) }
          }}
          placeholder={placeholder}
          autoComplete="off" spellCheck={false}
          style={{ width:"100%", boxSizing:"border-box",
            border:`1px solid ${open?BRONZE:C.border}`, borderRadius:10,
            padding:"9px 34px 9px 13px", fontSize:13, background:C.surface, color:C.text, outline:"none" }}
        />
        <div style={{ position:"absolute", right:11, top:"50%", transform:"translateY(-50%)", color:BRONZE, fontSize:14 }}>⌕</div>
      </div>

      {open && results.length > 0 && (
        <div style={{ position:"absolute", top:"calc(100% + 4px)", left:0, right:0, background:C.surface,
          border:`1px solid ${C.border}`, borderRadius:10, boxShadow:"0 6px 24px rgba(15,27,45,0.12)",
          zIndex:99999, overflow:"hidden", maxHeight:420, overflowY:"auto" }}>
          {results.map((r,i) => (
            <div key={r.company_name+i}
              onMouseDown={e=>{ e.preventDefault(); pick(r.company_name) }}
              style={{ padding:"10px 13px", cursor:"pointer",
                borderBottom: i<results.length-1?`1px solid ${C.bg}`:"none" }}
              onMouseEnter={e=>e.currentTarget.style.background=C.bg}
              onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
              <div style={{ display:"flex", alignItems:"center", gap:7 }}>
                <span style={{ fontSize:13.5, fontWeight:700, color:BRONZE }}>{r.company_name}</span>
                {r.sym && <span style={{ fontSize:10, fontFamily:"ui-monospace,monospace", color:C.sub, background:C.bg, padding:"1px 5px", borderRadius:4 }}>{r.sym}</span>}
                {r.playbook_setup && (
                  <span style={{ marginLeft:"auto", fontSize:9.5, fontWeight:800, letterSpacing:.5,
                    textTransform:"uppercase", color:setupColor(r.playbook_setup) }}>
                    {r.playbook_setup==="core-lite"?"core":r.playbook_setup}
                  </span>
                )}
              </div>
              {r.listing_gap_pct != null && (
                <div style={{ fontSize:10.5, color:C.sub, marginTop:2 }}>
                  {r.ipo_status?.replace(/_/g," ") || ""} {r.listing_gap_pct!=null?`· gap ${r.listing_gap_pct>0?"+":""}${Number(r.listing_gap_pct).toFixed(1)}%`:""}
                </div>
              )}
            </div>
          ))}
          <div style={{ padding:"6px 13px", background:C.bg, fontSize:10, color:C.sub, borderTop:`1px solid ${C.border}` }}>
            {results.length} IPO{results.length!==1?"s":""} · click to jump
          </div>
        </div>
      )}

      {open && query.length >= 1 && results.length === 0 && (
        <div style={{ position:"absolute", top:"calc(100% + 4px)", left:0, right:0, background:C.surface,
          border:`1px solid ${C.border}`, borderRadius:10, padding:"12px", textAlign:"center",
          fontSize:12, color:C.sub, zIndex:99999 }}>
          No IPO matches &ldquo;{query}&rdquo;
        </div>
      )}
    </div>
  )
}
