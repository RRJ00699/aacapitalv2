"use client"
// components/features/settings-tab.tsx
// Capital goal configuration, IPO thresholds, alert preferences.
// Persists to Neon via /api/settings.

import { useState, useEffect } from "react"

interface UserSettings {
  startingCapital: number
  targetCapital:   number
  targetYears:     number
  portfolioStartDate: string
  ipoConvictionThreshold: number
  riskAppetite: "Conservative" | "Moderate" | "Aggressive"
  marketRegimeAlerts: boolean
  telegramChatId: string
}

const DEFAULT: UserSettings = {
  startingCapital:        500000,
  targetCapital:         5000000,
  targetYears:                 5,
  portfolioStartDate: new Date().toISOString().split("T")[0],
  ipoConvictionThreshold:     80,
  riskAppetite:      "Moderate",
  marketRegimeAlerts:       true,
  telegramChatId:             "",
}

// ── Design tokens (matching AACapital system) ────────────────────────────────
const T = {
  white: "#FFFFFF", bg: "#FAFAF8", border: "#E5E7EB",
  text: "#111827", gray: "#6B7280", grayBg: "#F9FAFB",
  blue: "#2563EB", blueBg: "#EFF6FF", blueBd: "#BFDBFE",
  green: "#16A34A", greenBg: "#F0FDF4",
  amber: "#D97706", amberBg: "#FFFBEB",
  red: "#DC2626",
}

function Card({ children, style = {} }: { children: any; style?: any }) {
  return (
    <div style={{ background: T.white, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20, marginBottom: 14, ...style }}>
      {children}
    </div>
  )
}

function SectionTitle({ text }: { text: string }) {
  return <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 14 }}>{text}</div>
}

function FieldLabel({ text }: { text: string }) {
  return <div style={{ fontSize: 11, color: T.gray, marginBottom: 5, fontWeight: 500 }}>{text}</div>
}

function TextInput({ value, onChange, type = "text", placeholder = "" }: any) {
  return (
    <input
      type={type} value={value} onChange={onChange} placeholder={placeholder}
      style={{
        width: "100%", boxSizing: "border-box" as const,
        border: `1px solid ${T.border}`, borderRadius: 8,
        padding: "9px 12px", fontSize: 13, color: T.text,
        background: T.grayBg, fontFamily: "inherit",
      }}
    />
  )
}

export function SettingsTab() {
  const [settings, setSettings] = useState<UserSettings>(DEFAULT)
  const [loading,  setLoading]  = useState(true)
  const [saving,   setSaving]   = useState(false)
  const [saved,    setSaved]    = useState(false)

  useEffect(() => {
    fetch("/api/settings")
      .then(r => r.json())
      .then(d => {
        if (d.settings && Object.keys(d.settings).length > 0) {
          setSettings(prev => ({ ...prev, ...d.settings }))
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch {}
    setSaving(false)
  }

  const set = (key: keyof UserSettings, value: any) =>
    setSettings(prev => ({ ...prev, [key]: value }))

  // Required CAGR to hit target
  const requiredCAGR = (
    settings.targetCapital > 0 &&
    settings.startingCapital > 0 &&
    settings.targetYears > 0
  )
    ? (((settings.targetCapital / settings.startingCapital) ** (1 / settings.targetYears) - 1) * 100).toFixed(1)
    : "—"

  const multiplier = settings.startingCapital > 0
    ? (settings.targetCapital / settings.startingCapital).toFixed(1)
    : "—"

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, color: T.gray, fontSize: 13 }}>
      Loading settings...
    </div>
  )

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: 16 }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, color: T.text, marginBottom: 4 }}>Settings</div>
          <div style={{ fontSize: 12, color: T.gray }}>Capital goals · IPO thresholds · Alert preferences</div>
        </div>
        <button onClick={save} disabled={saving} style={{
          padding: "9px 22px",
          background: saved ? T.green : T.blue,
          border: "none", borderRadius: 8, color: "#fff",
          fontWeight: 700, fontSize: 13, cursor: saving ? "default" : "pointer",
          opacity: saving ? 0.7 : 1, transition: "background 0.2s",
        }}>
          {saving ? "Saving…" : saved ? "✓ Saved" : "Save Settings"}
        </button>
      </div>

      {/* Capital Compounding Goal */}
      <Card>
        <SectionTitle text="💰 Capital Compounding Goal" />

        {/* Summary bar */}
        <div style={{
          background: "linear-gradient(135deg,#0f172a,#1e3a5f)",
          borderRadius: 10, padding: "14px 18px", marginBottom: 16,
          display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center",
        }}>
          {[
            { l: "Starting Capital",  v: `₹${Number(settings.startingCapital).toLocaleString("en-IN")}`, c: "#60a5fa" },
            { l: "Target Capital",    v: `₹${Number(settings.targetCapital).toLocaleString("en-IN")}`,   c: "#4ade80" },
            { l: "Multiplier",        v: `${multiplier}x`,                                                c: "#c084fc" },
            { l: "Time Horizon",      v: `${settings.targetYears} years`,                                 c: "#94a3b8" },
            { l: "Required CAGR",     v: `${requiredCAGR}%`,                                              c: "#fbbf24" },
          ].map(s => (
            <div key={s.l} style={{ flex: 1, minWidth: 90 }}>
              <div style={{ fontSize: 10, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3 }}>{s.l}</div>
              <div style={{ fontSize: 18, fontWeight: 900, color: s.c, lineHeight: 1 }}>{s.v}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {[
            { label: "Starting Capital (₹)", key: "startingCapital" as const, type: "number", ph: "500000" },
            { label: "Target Capital (₹)",   key: "targetCapital"   as const, type: "number", ph: "5000000" },
            { label: "Time Horizon (years)",  key: "targetYears"     as const, type: "number", ph: "5" },
            { label: "Portfolio Start Date",  key: "portfolioStartDate" as const, type: "date", ph: "" },
          ].map(f => (
            <div key={f.key}>
              <FieldLabel text={f.label} />
              <TextInput
                type={f.type}
                value={settings[f.key]}
                placeholder={f.ph}
                onChange={(e: any) => set(f.key, f.type === "number" ? parseFloat(e.target.value) || 0 : e.target.value)}
              />
            </div>
          ))}
        </div>
      </Card>

      {/* IPO Strategy */}
      <Card>
        <SectionTitle text="🚀 IPO Strategy Thresholds" />

        <div style={{ marginBottom: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: T.gray, fontWeight: 500 }}>Minimum Conviction to Apply</span>
            <span style={{ fontSize: 20, fontWeight: 900, color: T.blue }}>{settings.ipoConvictionThreshold}</span>
          </div>
          <input
            type="range" min={70} max={95} step={1}
            value={settings.ipoConvictionThreshold}
            onChange={e => set("ipoConvictionThreshold", parseInt(e.target.value))}
            style={{ width: "100%", accentColor: T.blue }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            {[70, 75, 80, 85, 90, 95].map(v => (
              <span key={v} style={{
                fontSize: 10,
                color: settings.ipoConvictionThreshold === v ? T.blue : T.gray,
                fontWeight: settings.ipoConvictionThreshold === v ? 700 : 400,
                fontFamily: "monospace",
              }}>{v}</span>
            ))}
          </div>
          <div style={{ marginTop: 8, padding: "8px 11px", background: T.blueBg, border: `1px solid ${T.blueBd}`, borderRadius: 7, fontSize: 11, color: T.blue, lineHeight: 1.5 }}>
            Current regime: COLD — threshold auto-raised to max({settings.ipoConvictionThreshold}, 90).
            Only IPOs with Conviction ≥ {Math.max(settings.ipoConvictionThreshold, 90)} will be flagged Apply.
          </div>
        </div>

        <div>
          <FieldLabel text="Risk Appetite" />
          <div style={{ display: "flex", gap: 8 }}>
            {(["Conservative", "Moderate", "Aggressive"] as const).map(r => (
              <button key={r} onClick={() => set("riskAppetite", r)} style={{
                flex: 1, padding: "9px 0",
                border: `2px solid ${settings.riskAppetite === r ? T.blue : T.border}`,
                background: settings.riskAppetite === r ? T.blueBg : "transparent",
                color: settings.riskAppetite === r ? T.blue : T.gray,
                borderRadius: 8, fontSize: 12,
                fontWeight: settings.riskAppetite === r ? 700 : 500,
                cursor: "pointer", transition: "all 0.15s",
              }}>{r}</button>
            ))}
          </div>
        </div>
      </Card>

      {/* Alert Preferences */}
      <Card>
        <SectionTitle text="🔔 Alert Preferences" />

        {/* Toggle */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <div>
            <div style={{ fontSize: 13, color: T.text, fontWeight: 600, marginBottom: 2 }}>Market Regime Change Alerts</div>
            <div style={{ fontSize: 11, color: T.gray }}>Notify when regime shifts HOT → COLD or COLD → FROZEN</div>
          </div>
          <button
            onClick={() => set("marketRegimeAlerts", !settings.marketRegimeAlerts)}
            style={{
              width: 46, height: 26, borderRadius: 13, border: "none", cursor: "pointer",
              background: settings.marketRegimeAlerts ? T.blue : T.border,
              position: "relative", transition: "background 0.2s", flexShrink: 0,
            }}
          >
            <div style={{
              width: 20, height: 20, borderRadius: "50%", background: "#fff",
              position: "absolute", top: 3,
              left: settings.marketRegimeAlerts ? 23 : 3,
              transition: "left 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
            }} />
          </button>
        </div>

        {/* Telegram */}
        <div>
          <FieldLabel text="Telegram Chat ID (for alerts)" />
          <TextInput
            value={settings.telegramChatId}
            onChange={(e: any) => set("telegramChatId", e.target.value)}
            placeholder="@yourusername or numeric chat ID"
          />
          <div style={{ fontSize: 11, color: T.gray, marginTop: 5, lineHeight: 1.5 }}>
            Get your ID from @userinfobot on Telegram. Used for IPO subscription alerts and regime change alerts.
            Leave blank to disable Telegram.
          </div>
        </div>
      </Card>

      {/* Broker & Data status */}
      <Card>
        <SectionTitle text="🔗 Broker & Data Connections" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {[
            { l: "Zerodha Kite",   v: "Connected ✓", sub: "Paid plan · active until 10 Jul 2026", c: T.green, bg: T.greenBg },
            { l: "Neon Postgres",  v: "Active ✓",    sub: "Free tier · 512MB limit",               c: T.green, bg: T.greenBg },
            { l: "Claude API",     v: "Active ✓",    sub: "AI memos + DRHP scanner",               c: T.blue,  bg: T.blueBg  },
            { l: "RAPIDAPI_KEY",   v: "Review",      sub: "Confirm if still in use",               c: T.amber, bg: T.amberBg },
          ].map(s => (
            <div key={s.l} style={{ background: s.bg, borderRadius: 9, padding: "11px 13px" }}>
              <div style={{ fontSize: 11, color: T.gray, marginBottom: 3 }}>{s.l}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: s.c }}>{s.v}</div>
              <div style={{ fontSize: 10, color: T.gray, marginTop: 2 }}>{s.sub}</div>
            </div>
          ))}
        </div>
      </Card>

    </div>
  )
}
