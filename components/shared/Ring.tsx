export default function Ring({ score, max=100, size=70 }: { score:number, max?:number, size?:number }) {
  const rv = size/2-7, circ = 2*Math.PI*rv, pct = score/max
  const c = pct>=0.8?"#16a34a":pct>=0.65?"#1d4ed8":pct>=0.5?"#d97706":"#dc2626"
  return (
    <div style={{ position:"relative", width:size, height:size, flexShrink:0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform:"rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={rv} fill="none" stroke="#e5e7eb" strokeWidth="6"/>
        <circle cx={size/2} cy={size/2} r={rv} fill="none" stroke={c} strokeWidth="6" strokeDasharray={circ} strokeDashoffset={circ*(1-pct)} strokeLinecap="round"/>
      </svg>
      <div style={{ position:"absolute", inset:0, display:"flex", alignItems:"center", justifyContent:"center" }}>
        <span style={{ fontSize:size>65?16:12, fontWeight:700, color:c }}>{score}</span>
      </div>
    </div>
  )
}
