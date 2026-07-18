// components/features/zerodha-status-banner.tsx
// Sprint 14: Shows a banner when Zerodha session expires instead of silent 500
// Drop-in: add near top of command-center.tsx or AACapitalApp.tsx
// import { ZerodhaStatusBanner } from "./zerodha-status-banner"
// <ZerodhaStatusBanner />

"use client"
import { useState, useEffect } from "react"

export function ZerodhaStatusBanner() {
  const [status, setStatus]   = useState<"checking" | "connected" | "expired" | "error">("checking")
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    fetch("/api/auth/zerodha/status")
      .then(async r => {
        const body = await r.json().catch(() => ({}))
        if (r.status === 401 || body?.connected === false) {
          setStatus("expired")
        } else if (r.ok && body?.connected) {
          setStatus("connected")
        } else {
          setStatus("error")
        }
      })
      .catch(() => setStatus("error"))
  }, [])

  // Don't show anything if connected or dismissed
  if (status === "connected" || status === "checking" || dismissed) return null

  return (
    <div style={{
      background: status === "expired" ? "#FEF3C7" : "#FEF2F2",
      border: `1px solid ${status === "expired" ? "#FDE68A" : "#FECACA"}`,
      borderRadius: 8,
      padding: "10px 14px",
      margin: "0 0 12px 0",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 16 }}>
          {status === "expired" ? "⚠️" : "❌"}
        </span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600,
            color: status === "expired" ? "#92400E" : "#991B1B" }}>
            {status === "expired"
              ? "Zerodha session expired — reconnect to see portfolio data"
              : "Zerodha connection error"}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>
            Holdings, portfolio alerts, and trade sync will not work until reconnected
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
        <a
          href="/api/auth/zerodha"
          style={{
            fontSize: 12, fontWeight: 600,
            padding: "6px 14px",
            background: "#2563EB", color: "#fff",
            borderRadius: 6, textDecoration: "none",
            border: "none", cursor: "pointer",
          }}
        >
          Reconnect Zerodha
        </a>
        <button
          onClick={() => setDismissed(true)}
          style={{
            fontSize: 11, color: "#6b7280",
            background: "none", border: "none",
            cursor: "pointer", padding: "6px 8px",
          }}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
