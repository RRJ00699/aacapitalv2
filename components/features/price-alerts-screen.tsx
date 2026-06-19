"use client"
// components/features/price-alerts-screen.tsx
// Price alerts — set targets, get notified when price hits

import { useState, useEffect, useCallback } from "react"
import { Bell, Plus, Trash2, TrendingUp, TrendingDown, RefreshCw } from "lucide-react"

const T = {
  bg:"#F7F9FC", surface:"#FFFFFF", border:"#E5E7EB", border2:"#F1F5F9",
  text:"#0F172A", textSub:"#64748B", textMeta:"#94A3B8",
  green:"#16A34A", greenBg:"#F0FDF4", greenBd:"#BBF7D0",
  blue:"#2563EB",  blueBg:"#EFF6FF",  blueBd:"#BFDBFE",
  amber:"#D97706", amberBg:"#FFFBEB", amberBd:"#FDE68A",
  red:"#DC2626",   redBg:"#FEF2F2",   redBd:"#FECACA",
}
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0

export function PriceAlertsScreen({ onStockSelect }: { onStockSelect?: (s: string) => void }) {
  const [alerts,   setAlerts]   = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [sym,      setSym]      = useState("")
  const [price,    setPrice]    = useState("")
  const [dir,      setDir]      = useState<"above"|"below">("above")
  const [note,     setNote]     = useState("")
  const [adding,   setAdding]   = useState(false)
  const [error,    setError]    = useState<string|null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    const r = await fetch("/api/price-alerts").then(d => d.json()).catch(() => null)
    setAlerts(r?.alerts ?? [])
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  async function addAlert() {
    if (!sym.trim() || !price) return
    setAdding(true); setError(null)
    try {
      const r = await fetch("/api/price-alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym.trim().toUpperCase(), target_price: parseFloat(price), direction: dir, note }),
      })
      const d = await r.json()
      if (!d.ok) { setError(d.error); return }
      setSym(""); setPrice(""); setNote("")
      await load()
    } catch { setError("Failed to add alert") }
    finally { setAdding(false) }
  }

  async function removeAlert(id: number) {
    await fetch("/api/price-alerts", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })
    await load()
  }

  const active    = alerts.filter(a => !a.triggered)
  const triggered = alerts.filter(a => a.triggered)

  return (
    <div style={{ background: T.bg, minHeight: "100vh", paddingBottom: 80 }}>

      {/* Header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "16px 20px", position: "sticky", top: 52, zIndex: 9 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Bell size={18} color={T.amber} fill={T.amber}/>
              <span style={{ fontSize: 20, fontWeight: 700, color: T.text }}>Price Alerts</span>
            </div>
            <div style={{ fontSize: 12, color: T.textSub, marginTop: 2 }}>
              {active.length} active · {triggered.length} triggered
            </div>
          </div>
          <button onClick={load} style={{ display: "flex", alignItems: "center", gap: 5,
            padding: "7px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
            background: T.surface, fontSize: 12, color: T.textSub, cursor: "pointer" }}>
            <RefreshCw size={12}/> Refresh
          </button>
        </div>

        {/* Add alert form */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 100px auto auto auto", gap: 6 }}>
          <input value={sym} onChange={e => setSym(e.target.value.toUpperCase())}
            placeholder="Symbol e.g. ARVIND"
            style={{ padding: "9px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
              fontSize: 13, fontFamily: "inherit", outline: "none" }}/>
          <input value={price} onChange={e => setPrice(e.target.value)} type="number"
            placeholder="₹ Price"
            style={{ padding: "9px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
              fontSize: 13, fontFamily: "inherit", outline: "none" }}/>
          <select value={dir} onChange={e => setDir(e.target.value as any)}
            style={{ padding: "9px 10px", borderRadius: 8, border: `1px solid ${T.border}`,
              fontSize: 12, fontFamily: "inherit", background: T.surface, cursor: "pointer" }}>
            <option value="above">Above ↑</option>
            <option value="below">Below ↓</option>
          </select>
          <input value={note} onChange={e => setNote(e.target.value)}
            placeholder="Note (optional)"
            style={{ padding: "9px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
              fontSize: 12, fontFamily: "inherit", outline: "none" }}/>
          <button onClick={addAlert} disabled={adding || !sym.trim() || !price}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 16px",
              borderRadius: 8, border: "none",
              background: sym.trim() && price ? T.blue : T.border,
              color: sym.trim() && price ? "#fff" : T.textMeta,
              fontSize: 13, fontWeight: 600, cursor: sym.trim() && price ? "pointer" : "default" }}>
            <Plus size={14}/> {adding ? "Adding…" : "Add"}
          </button>
        </div>
        {error && <div style={{ fontSize: 11, color: T.red, marginTop: 6 }}>{error}</div>}
      </div>

      <div style={{ maxWidth: 720, margin: "0 auto", padding: "16px 16px 0" }}>

        {loading ? (
          <div style={{ padding: "60px 0", textAlign: "center" as const, color: T.textMeta }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>🔔</div>
            <div>Loading alerts…</div>
          </div>
        ) : alerts.length === 0 ? (
          <div style={{ background: T.surface, border: `1px dashed ${T.border}`,
            borderRadius: 16, padding: "48px 24px", textAlign: "center" as const }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🔔</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: T.text, marginBottom: 6 }}>No price alerts set</div>
            <div style={{ fontSize: 13, color: T.textSub }}>
              Add a symbol and target price above. Alerts are checked daily by the system.
            </div>
          </div>
        ) : (
          <>
            {/* Active alerts */}
            {active.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.textSub,
                  textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
                  Active — {active.length}
                </div>
                {active.map((a: any) => (
                  <div key={a.id} style={{ background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderLeft: `3px solid ${a.direction === "above" ? T.green : T.red}`,
                    borderRadius: 12, padding: "12px 14px", marginBottom: 8,
                    display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                      background: a.direction === "above" ? T.greenBg : T.redBg,
                      display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {a.direction === "above"
                        ? <TrendingUp size={16} color={T.green}/>
                        : <TrendingDown size={16} color={T.red}/>}
                    </div>
                    <div style={{ flex: 1, cursor: "pointer" }} onClick={() => onStockSelect?.(a.symbol)}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                        <span style={{ fontSize: 15, fontWeight: 800, color: T.text }}>{a.symbol}</span>
                        <span style={{ fontSize: 11, color: a.direction === "above" ? T.green : T.red,
                          fontWeight: 600 }}>
                          {a.direction === "above" ? "↑ Alert above" : "↓ Alert below"} ₹{n(a.target_price).toLocaleString("en-IN")}
                        </span>
                      </div>
                      {a.note && <div style={{ fontSize: 11, color: T.textSub }}>{a.note}</div>}
                      <div style={{ fontSize: 10, color: T.textMeta }}>
                        Set {new Date(a.created_at).toLocaleDateString("en-IN")}
                      </div>
                    </div>
                    <button onClick={() => removeAlert(a.id)}
                      style={{ padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.redBd}`,
                        background: T.redBg, color: T.red, cursor: "pointer" }}>
                      <Trash2 size={12}/>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Triggered alerts */}
            {triggered.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.textSub,
                  textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
                  Triggered — {triggered.length}
                </div>
                {triggered.map((a: any) => (
                  <div key={a.id} style={{ background: T.amberBg,
                    border: `1px solid ${T.amberBd}`, borderRadius: 12,
                    padding: "12px 14px", marginBottom: 8,
                    display: "flex", alignItems: "center", gap: 12, opacity: 0.8 }}>
                    <Bell size={16} color={T.amber} fill={T.amber}/>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>
                        {a.symbol} hit ₹{n(a.target_price).toLocaleString("en-IN")} ✓
                      </div>
                      <div style={{ fontSize: 11, color: T.textSub }}>
                        Triggered {a.triggered_at ? new Date(a.triggered_at).toLocaleDateString("en-IN") : ""}
                      </div>
                    </div>
                    <button onClick={() => removeAlert(a.id)}
                      style={{ padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.border}`,
                        background: T.surface, color: T.textSub, cursor: "pointer" }}>
                      <Trash2 size={12}/>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
