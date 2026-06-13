export default function StatCard({ label, value, sub, color, tip }: { label:string, value:string|number, sub?:string, color?:string, tip?:string }) {
  return (
    <div title={tip} style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:10, padding:"11px 13px", boxShadow:"0 1px 3px rgba(0,0,0,0.04)", cursor:tip?"help":"default" }}>
      <div style={{ fontSize:8, letterSpacing:"0.8px", textTransform:"uppercase", color:"#9ca3af", marginBottom:3, borderBottom:tip?"1px dashed #d1d5db":"none", display:"inline-block" }}>{label}</div>
      <div style={{ fontSize:16, fontWeight:700, color:color||"#111827", marginTop:2 }}>{value}</div>
      {sub && <div style={{ fontSize:10, color:"#9ca3af", marginTop:1 }}>{sub}</div>}
    </div>
  )
}
