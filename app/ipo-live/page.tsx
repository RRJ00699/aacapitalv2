import IpoLiveTickPanel from "@/components/ipo/IpoLiveTickPanel"

export const dynamic = "force-dynamic"

export default function IpoLivePage() {
  return (
    <div style={{ maxWidth: 760, margin: "28px auto", padding: "0 16px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0F1B2D", marginBottom: 4 }}>IPO Live — Listing Day</h1>
      <p style={{ fontSize: 13, color: "#64748b", marginTop: 0, marginBottom: 18, fontFamily: "'IBM Plex Mono',monospace" }}>
        Live feed from ipo_tick_feed · run the ticker locally with --write-db
      </p>
      <IpoLiveTickPanel symbol="TURTLEMINT" />
    </div>
  )
}
