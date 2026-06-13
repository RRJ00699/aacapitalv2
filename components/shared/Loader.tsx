export default function Loader({ text="Loading..." }: { text?:string }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:10, padding:"40px 20px", color:"#9ca3af", fontSize:12 }}>
      <div className="spin" style={{ width:18, height:18, border:"2px solid #e5e7eb", borderTopColor:"#3b82f6", borderRadius:"50%" }}/>
      {text}
    </div>
  )
}
