"use client";
import { Card, SectionHeader, Badge } from "@/components/ui/primitives";
import { VARS as C, FONT } from "@/lib/theme";

type R=Record<string,any>; // snapshot is runtime-validated by its versioned builder
const show=(v:any)=>v==null||v===""?"—":typeof v==="object"?JSON.stringify(v):String(v);
function F({label,f}:{label:string;f:R}){return <div className="detail-field"><span>{label}</span><b>{show(f?.value)}</b><Badge label={f?.state||"MISSING"}/>{f?.state!=="AVAILABLE"&&<small>{f?.reason}</small>}</div>}
export default function CompleteDetails({details:d}:{details:R}){
 const v=d.valuation||{}, o=d.listing_outcome||{}, dec=d.decision||{};
 return <main data-testid="complete-details" style={{display:"grid",gap:14,minWidth:0}}>
  <Card><div style={{display:"flex",flexWrap:"wrap",gap:8,alignItems:"center"}}><h1 style={{fontFamily:FONT.display,margin:0}}>{d.identity.company_name}</h1><Badge label={d.identity.isin}/></div><F label="Listing date" f={d.identity.listing_date}/></Card>
  <Card><SectionHeader>Issue details</SectionHeader>{Object.entries(d.issue).map(([k,f])=><F key={k} label={k.replaceAll("_"," ")} f={f as R}/>)}</Card>
  <section aria-labelledby="ai-analysis" style={{background:C.blueBg,border:`2px solid ${C.blueBd}`,borderRadius:14,padding:16}}><h2 id="ai-analysis" style={{marginTop:0}}>AI analysis</h2><div style={{fontSize:12,color:C.meta}}>Model {show(d.ai_analysis.model)} · Prompt {show(d.ai_analysis.prompt_version)} · Confidence {show(d.ai_analysis.confidence)} · {show(d.ai_analysis.analyzed_at)}</div>{d.ai_analysis.state==="AVAILABLE"?<div style={{whiteSpace:"pre-wrap",marginTop:10}}>{show(d.ai_analysis.findings)}</div>:<p>{d.ai_analysis.reason}</p>}</section>
  <section aria-labelledby="verified-evidence" style={{background:C.greenBg,border:`2px solid ${C.greenBd}`,borderRadius:14,padding:16}}><h2 id="verified-evidence" style={{marginTop:0}}>Verified evidence</h2>{d.verified_evidence.length?d.verified_evidence.map((e:R,i:number)=><article key={`${e.doc_id}-${e.page_number}-${i}`} style={{borderTop:i?`1px solid ${C.line}`:"none",padding:"10px 0"}}><strong>Verified excerpt, p.{e.page_number}</strong><blockquote style={{margin:"7px 0",paddingLeft:12,borderLeft:`3px solid ${C.green}`}}>{e.excerpt}</blockquote><small>{e.document.doc_type} · {e.document.url} · {e.category} · {e.direction} · {e.source_type}</small></article>):<p>No verified excerpts are currently available.</p>}</section>
  <Card><SectionHeader>Governance and risk</SectionHeader>{Object.entries(d.governance_and_risk).map(([k,f])=><F key={k} label={k.replaceAll("_"," ")} f={f as R}/>)}</Card>
  <Card><SectionHeader>Decision</SectionHeader><F label="Verdict" f={dec.verdict}/><F label="Reasons" f={dec.reasons}/><F label="Evidence" f={dec.evidence}/>{dec.verdict?.value==="JUNK"&&<F label="Derived kill_reason" f={dec.kill_reason}/>}</Card>
  <Card><SectionHeader>Valuation provenance</SectionHeader>{["score","band","engine_version","computed_at","pe","pb","pe_source","pb_source","peer_median_pe","fair_value_low","fair_value_high","margin_of_safety","inputs_used","missing_inputs"].map(k=><F key={k} label={k==="margin_of_safety"?"Derived margin-of-safety range":k.replaceAll("_"," ")} f={v[k]}/>)}</Card>
  <Card><SectionHeader>Listing outcome</SectionHeader>{Object.entries(o).map(([k,f])=>typeof f==="object"&&f&&"state" in f?<F key={k} label={k==="ceiling_20"?"Historical ceiling indicator — non-executable":k.replaceAll("_"," ")} f={f as R}/>:null)}</Card>
  <section data-testid="gmp-stale" style={{border:`1px solid ${C.amberBd}`,background:C.amberBg,borderRadius:14,padding:16}}><h2 style={{marginTop:0}}>GMP · STALE</h2><p>Available: false · Last updated: {d.gmp.last_updated}</p><p>{d.gmp.reason}</p></section>
  <style jsx>{`.detail-field{display:grid;grid-template-columns:minmax(130px,.7fr) minmax(0,1fr) auto;gap:8px;padding:8px 0;border-bottom:1px solid ${C.line};overflow-wrap:anywhere}.detail-field>span{color:${C.meta};text-transform:capitalize}.detail-field small{grid-column:2/4;color:${C.meta}}@media(max-width:600px){.detail-field{grid-template-columns:1fr auto}.detail-field>b,.detail-field small{grid-column:1/3}}`}</style>
 </main>
}
