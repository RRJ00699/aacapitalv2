export default function Spark({ data, color, h=55 }: { data:number[], color:string, h?:number }) {
  if (!data?.length) return null
  const mx = Math.max(...data)||1, n = data.length, gap=3, W=300, H=h
  const bw = Math.floor((W-(n-1)*gap)/n)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width:"100%", height:h, display:"block" }}>
      {data.map((v,i) => {
        const bh = Math.max(3,Math.round((v/mx)*(H-2))), x=i*(bw+gap), isLast=i===n-1
        const alpha = isLast?1:0.35+((i/(n-1))*0.45)
        const up = v>=(data[i-1]??v)
        return (
          <g key={i}>
            <rect x={x} y={H-bh} width={bw} height={bh} fill={color} opacity={alpha} rx={2}/>
            {isLast && <text x={x+bw/2} y={H-bh-4} textAnchor="middle" fontSize="9" fill={up?"#16a34a":"#dc2626"} fontWeight="700">{up?"↑":"↓"}</text>}
          </g>
        )
      })}
    </svg>
  )
}
