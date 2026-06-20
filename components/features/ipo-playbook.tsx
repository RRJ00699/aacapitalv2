"use client"
// components/features/ipo-playbook.tsx
// AACapital IPO Quick Profit Playbook
// ONE question: "Can I make money from this IPO in the next 1–5 sessions?"
// ONE answer: play card with reasons + optional context

import { useState, useEffect, useCallback } from "react"
import { RefreshCw, ChevronDown, ChevronUp, ExternalLink, TrendingUp, TrendingDown, AlertTriangle, Clock, Target, Shield } from "lucide-react"

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:       "#F7F9FC",
  surface:  "#FFFFFF",
  border:   "#E5E7EB",
  border2:  "#F1F5F9",
  text:     "#0F172A",
  textSub:  "#64748B",
  textMeta: "#94A3B8",
  green:    "#16A34A", greenBg:  "#F0FDF4", greenBd:  "#BBF7D0",
  blue:     "#2563EB", blueBg:   "#EFF6FF", blueBd:   "#BFDBFE",
  amber:    "#D97706", amberBg:  "#FFFBEB", amberBd:  "#FDE68A",
  red:      "#DC2626", redBg:    "#FEF2F2", redBd:    "#FECACA",
  purple:   "#7C3AED", purpleBg: "#F5F3FF", purpleBd: "#DDD6FE",
  teal:     "#0D9488", tealBg:   "#F0FDFA", tealBd:   "#99F6E4",
  gray:     "#6B7280", grayBg:   "#F9FAFB",
}
const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const pct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`

// ── Play config ───────────────────────────────────────────────────────────────
const PLAY_CFG = {
  BUY_AT_OPEN:       { label: "Buy at Open",         color: T.green,  bg: T.greenBg,  bd: T.greenBd,  icon: "🟢", emoji: "⚡" },
  WAIT_FOR_VWAP:     { label: "Wait for VWAP",       color: T.blue,   bg: T.blueBg,   bd: T.blueBd,   icon: "🔵", emoji: "⏳" },
  BUY_PANIC_DIP:     { label: "Buy Panic Dip",       color: T.teal,   bg: T.tealBg,   bd: T.tealBd,   icon: "🔵", emoji: "📉" },
  BUY_AFTER_DAY3:    { label: "Buy After Day 3",     color: T.purple, bg: T.purpleBg, bd: T.purpleBd, icon: "⚪", emoji: "📅" },
  BUY_AFTER_ANCHOR:  { label: "Buy After Anchor",    color: T.purple, bg: T.purpleBg, bd: T.purpleBd, icon: "⚪", emoji: "🔓" },
  BUY_PEER:          { label: "Buy Listed Peer",     color: T.amber,  bg: T.amberBg,  bd: T.amberBd,  icon: "🟠", emoji: "🔄" },
  AVOID:             { label: "Avoid",               color: T.red,    bg: T.redBg,    bd: T.redBd,    icon: "🔴", emoji: "🚫" },
} as const

// ── Sub-components ────────────────────────────────────────────────────────────
function KV({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ background: highlight ? T.greenBg : T.grayBg,
      borderRadius: 8, padding: "10px 12px",
      border: `1px solid ${highlight ? T.greenBd : T.border}` }}>
      <div style={{ fontSize: 10, color: highlight ? T.green : T.textMeta,
        fontWeight: 600, textTransform: "uppercase" as const,
        letterSpacing: "0.06em", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700,
        color: highlight ? T.green : T.text }}>{value || "—"}</div>
    </div>
  )
}

function Pill({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px",
      borderRadius: 20, background: bg, color, border: `1px solid ${color}30` }}>
      {label}
    </span>
  )
}

function SectionToggle({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ borderTop: `1px solid ${T.border2}` }}>
      <button onClick={() => setOpen(!open)}
        style={{ width: "100%", display: "flex", justifyContent: "space-between",
          alignItems: "center", padding: "10px 0",
          border: "none", background: "transparent",
          fontSize: 12, fontWeight: 600, color: T.textSub, cursor: "pointer" }}>
        {label}
        {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
      </button>
      {open && <div style={{ paddingBottom: 12 }}>{children}</div>}
    </div>
  )
}

// ── GMP Sparkline ─────────────────────────────────────────────────────────────
function GmpSparkline({ history }: { history: Record<string, number> }) {
  const points = Object.entries(history)
    .sort(([a],[b]) => {
      const order = ['t10','t7','t5','t3','t1']
      return order.indexOf(a) - order.indexOf(b)
    })
  if (points.length < 2) return null
  const vals = points.map(([,v]) => v)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const W = 120, H = 36
  const coords = points.map(([,v], i) =>
    `${(i / (points.length-1)) * W},${H - ((v - min) / range) * (H-4) - 2}`)
  const trend = vals[vals.length-1] > vals[0]
  return (
    <div>
      <svg width={W} height={H} style={{ overflow: "visible" }}>
        <polyline points={coords.join(' ')} fill="none"
          stroke={trend ? T.green : T.red} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        {points.map(([label,v],i) => (
          <circle key={i} cx={(i/(points.length-1))*W}
            cy={H - ((v-min)/range)*(H-4) - 2} r="3"
            fill={trend ? T.green : T.red}/>
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between",
        fontSize: 9, color: T.textMeta, marginTop: 2 }}>
        {points.map(([label]) => <span key={label}>{label.replace('t','T-')}</span>)}
      </div>
    </div>
  )
}

// ── Confidence ring ───────────────────────────────────────────────────────────
function ConfidenceRing({ value, color }: { value: number; color: string }) {
  const r = 28, circ = 2 * Math.PI * r
  const dash = (value / 100) * circ
  return (
    <div style={{ position: "relative", width: 72, height: 72,
      display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width="72" height="72" style={{ position: "absolute", transform: "rotate(-90deg)" }}>
        <circle cx="36" cy="36" r={r} fill="none" stroke={T.border} strokeWidth="4"/>
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"/>
      </svg>
      <div style={{ fontSize: 15, fontWeight: 800, color }}>{value}%</div>
    </div>
  )
}

// ── Main card ─────────────────────────────────────────────────────────────────
function PlaybookCard({ ipo, onClose }: { ipo: any; onClose?: () => void }) {
  const play     = ipo.play_recommendation || ipo.suggested_action?.replace(/\s+/g,'_').toUpperCase() || "AVOID"
  const playCfg  = PLAY_CFG[play as keyof typeof PLAY_CFG] ?? PLAY_CFG.AVOID
  const conf     = n(ipo.play_confidence || ipo.confidence_level || 60)
  const reasons  = (() => { try { return JSON.parse(ipo.play_reasons || '[]') } catch { return [] } })()
  const gmpHist  = (() => { try { return JSON.parse(ipo.gmp_history || '{}') } catch { return {} } })()
  const anchors  = String(ipo.anchor_stalwart_names || ipo.anchor_investors || '')
  const opFlags  = (() => { try { return JSON.parse(ipo.operator_risk_flags || '[]') } catch { return [] } })()

  const isAvoid  = play === "AVOID"
  const isBuy    = play.startsWith("BUY")

  return (
    <div style={{ background: T.surface, borderRadius: 20,
      border: `1px solid ${playCfg.bd}`,
      boxShadow: `0 0 0 4px ${playCfg.bg}`,
      overflow: "hidden", maxWidth: 640, margin: "0 auto" }}>

      {/* ── Header ── */}
      <div style={{ background: playCfg.bg, padding: "16px 20px",
        borderBottom: `1px solid ${playCfg.bd}` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: playCfg.color,
              textTransform: "uppercase" as const, letterSpacing: "0.1em", marginBottom: 4 }}>
              IPO Quick Profit Playbook
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, color: T.text, marginBottom: 2 }}>
              {ipo.company_name}
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" as const }}>
              {ipo.sector && <Pill label={ipo.sector} color={T.textSub} bg={T.grayBg}/>}
              {ipo.is_sme && <Pill label="SME" color={T.red} bg={T.redBg}/>}
              {ipo.listing_date && (
                <span style={{ fontSize: 11, color: T.textMeta }}>
                  Listed {new Date(ipo.listing_date).toLocaleDateString("en-IN")}
                </span>
              )}
            </div>
          </div>
          <ConfidenceRing value={Math.round(conf)} color={playCfg.color}/>
        </div>
      </div>

      {/* ── Play decision ── */}
      <div style={{ padding: "18px 20px", borderBottom: `1px solid ${T.border2}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <div style={{ fontSize: 32 }}>{playCfg.emoji}</div>
          <div>
            <div style={{ fontSize: 11, color: T.textMeta, fontWeight: 600,
              textTransform: "uppercase" as const, letterSpacing: "0.1em" }}>Best play</div>
            <div style={{ fontSize: 26, fontWeight: 900, color: playCfg.color }}>
              {playCfg.label}
            </div>
          </div>
        </div>

        {/* Reasons */}
        {reasons.length > 0 && (
          <div style={{ background: T.grayBg, borderRadius: 10, padding: "12px 14px", marginBottom: 12 }}>
            {reasons.map((r: string, i: number) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: i < reasons.length-1 ? 6 : 0 }}>
                <span style={{ color: playCfg.color, fontWeight: 700, flexShrink: 0 }}>→</span>
                <span style={{ fontSize: 13, color: T.text }}>{r}</span>
              </div>
            ))}
          </div>
        )}

        {/* Trade params (not for AVOID) */}
        {!isAvoid && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
              <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600,
                textTransform: "uppercase" as const, marginBottom: 2 }}>Stop loss</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.red }}>
                -{n(ipo.play_stop_loss_pct).toFixed(1)}%
              </div>
            </div>
            <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
              <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600,
                textTransform: "uppercase" as const, marginBottom: 2 }}>Target</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.green }}>
                +{n(ipo.play_target_pct).toFixed(1)}%
              </div>
            </div>
            <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
              <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600,
                textTransform: "uppercase" as const, marginBottom: 2 }}>Hold window</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.text }}>
                {ipo.play_hold_window || "—"}
              </div>
            </div>
          </div>
        )}

        {/* Timing (for listing day plays) */}
        {(play === "BUY_AT_OPEN" || play === "WAIT_FOR_VWAP") && (
          <div style={{ marginTop: 10, padding: "10px 14px",
            background: T.amberBg, borderRadius: 8,
            border: `1px solid ${T.amberBd}`, fontSize: 12 }}>
            <div style={{ fontWeight: 700, color: T.amber, marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
              <Clock size={13}/> Listing Day Execution
            </div>
            <div style={{ color: T.text, display: "flex", flexDirection: "column" as const, gap: 4 }}>
              <span>⏰ 10:00 AM — Watch OI buy/sell ratio and pre-open demand</span>
              <span>⏰ 10:15 AM — Final decision deadline (no entry after this)</span>
              <span>⏰ 10:25 AM — Price band confirmed — enter or walk away</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Key metrics strip ── */}
      <div style={{ padding: "14px 20px", borderBottom: `1px solid ${T.border2}` }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
          <KV label="Issue size" value={n(ipo.issue_size_cr) > 0 ? `₹${Math.round(n(ipo.issue_size_cr))}Cr` : "—"}
            highlight={n(ipo.issue_size_cr) >= 500}/>
          <KV label="QIB sub" value={n(ipo.qib_subscription_x) > 0 ? `${n(ipo.qib_subscription_x).toFixed(0)}x` : "—"}
            highlight={n(ipo.qib_subscription_x) >= 50}/>
          <KV label="GMP (T-1)" value={n(ipo.gmp_pct_t1) !== 0 ? `${n(ipo.gmp_pct_t1) > 0 ? "+" : ""}${n(ipo.gmp_pct_t1).toFixed(1)}%` : "—"}/>
          <KV label="LQI score" value={n(ipo.lqi_final) > 0 ? `${Math.round(n(ipo.lqi_final))}/100` : "—"}
            highlight={n(ipo.lqi_final) >= 70}/>
        </div>
      </div>

      {/* ── Optional context (collapsible) ── */}
      <div style={{ padding: "0 20px 8px" }}>

        {/* GMP trend */}
        {Object.keys(gmpHist).length >= 2 && (
          <SectionToggle label="📈 GMP trend history">
            <div style={{ display: "flex", alignItems: "flex-end", gap: 16, padding: "4px 0 8px" }}>
              <GmpSparkline history={gmpHist}/>
              <div>
                <div style={{ fontSize: 11, color: T.textSub, marginBottom: 4 }}>
                  Trend: <span style={{ fontWeight: 700, color: n(ipo.gmp_pct_t1) > n(ipo.gmp_pct_t3) ? T.green : T.red }}>
                    {ipo.gmp_momentum || "—"}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: T.textSub }}>
                  Peak: {n(ipo.gmp_max_pct) > 0 ? `+${n(ipo.gmp_max_pct).toFixed(1)}%` : "—"}
                </div>
              </div>
            </div>
          </SectionToggle>
        )}

        {/* Subscription breakdown */}
        {n(ipo.qib_subscription_x) > 0 && (
          <SectionToggle label="📊 Subscription breakdown">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, padding: "4px 0 8px" }}>
              {[
                { label: "QIB", value: ipo.qib_subscription_x },
                { label: "NII/HNI", value: ipo.nii_subscription_x },
                { label: "Retail", value: ipo.rii_subscription_x },
              ].map(s => (
                <div key={s.label} style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>{s.label}</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: n(s.value) >= 20 ? T.green : T.text }}>
                    {n(s.value) > 0 ? `${n(s.value).toFixed(0)}x` : "—"}
                  </div>
                </div>
              ))}
            </div>
            {ipo.qib_backloaded && (
              <div style={{ fontSize: 11, color: T.amber, padding: "4px 0",
                display: "flex", alignItems: "center", gap: 6 }}>
                <AlertTriangle size={12}/> QIB backloaded — institutions waited until Day 3
              </div>
            )}
          </SectionToggle>
        )}

        {/* Anchor analysis */}
        {(n(ipo.anchor_tier1_count) > 0 || anchors) && (
          <SectionToggle label={`⚓ Anchor analysis${n(ipo.anchor_count) > 0 ? ` (${Math.round(n(ipo.anchor_count))} anchors)` : ''}`}>
            <div style={{ padding: "4px 0 8px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
                <div style={{ background: n(ipo.anchor_tier1_count) >= 15 ? T.greenBg : T.grayBg,
                  borderRadius: 8, padding: "8px 10px",
                  border: `1px solid ${n(ipo.anchor_tier1_count) >= 15 ? T.greenBd : T.border}` }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>Tier-1 anchors</div>
                  <div style={{ fontSize: 18, fontWeight: 700,
                    color: n(ipo.anchor_tier1_count) >= 15 ? T.green : T.text }}>
                    {Math.round(n(ipo.anchor_tier1_count))}
                  </div>
                  <div style={{ fontSize: 10, color: T.textMeta }}>LIC/SBI/ICICI/Nippon/ADIA</div>
                </div>
                <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>Lock-in expiry</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>
                    T+30: {ipo.anchor_lock30_date ? new Date(ipo.anchor_lock30_date).toLocaleDateString("en-IN") : "—"}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>
                    T+90: {ipo.anchor_lock90_date ? new Date(ipo.anchor_lock90_date).toLocaleDateString("en-IN") : "—"}
                  </div>
                </div>
              </div>
              {anchors && (
                <div style={{ fontSize: 11, color: T.textSub, lineHeight: 1.6 }}>
                  Quality anchors: {anchors}
                </div>
              )}
            </div>
          </SectionToggle>
        )}

        {/* BRLM */}
        {ipo.brlm_names && (
          <SectionToggle label="🏦 Book manager track record">
            <div style={{ padding: "4px 0 8px" }}>
              <div style={{ fontSize: 12, color: T.text, fontWeight: 600, marginBottom: 8 }}>
                {String(ipo.brlm_names).split(',')[0].trim()}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>BRLM score</div>
                  <div style={{ fontSize: 16, fontWeight: 700,
                    color: n(ipo.brlm_score) >= 70 ? T.green : n(ipo.brlm_score) >= 50 ? T.amber : T.red }}>
                    {n(ipo.brlm_score) > 0 ? `${Math.round(n(ipo.brlm_score))}/100` : "—"}
                  </div>
                </div>
                <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>Avg listing gain</div>
                  <div style={{ fontSize: 16, fontWeight: 700,
                    color: n(ipo.brlm_avg_listing_gain) >= 10 ? T.green : T.amber }}>
                    {n(ipo.brlm_avg_listing_gain) > 0 ? `+${n(ipo.brlm_avg_listing_gain).toFixed(1)}%` : "—"}
                  </div>
                </div>
                <div style={{ background: T.grayBg, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>% negative listing</div>
                  <div style={{ fontSize: 16, fontWeight: 700,
                    color: n(ipo.brlm_pct_negative) <= 20 ? T.green : T.red }}>
                    {n(ipo.brlm_pct_negative) > 0 ? `${n(ipo.brlm_pct_negative).toFixed(0)}%` : "—"}
                  </div>
                </div>
              </div>
            </div>
          </SectionToggle>
        )}

        {/* Operator risk */}
        {n(ipo.operator_risk_score) > 30 && (
          <SectionToggle label={`⚠️ Operator risk — ${Math.round(n(ipo.operator_risk_score))}/100`}>
            <div style={{ padding: "4px 0 8px" }}>
              {opFlags.map((f: any, i: number) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between",
                  padding: "5px 0", borderBottom: `1px solid ${T.border2}`,
                  fontSize: 12, color: T.text }}>
                  <span>{f.flag}</span>
                  <span style={{ color: T.red, fontWeight: 600 }}>+{f.weight}</span>
                </div>
              ))}
            </div>
          </SectionToggle>
        )}

        {/* Post-listing results (if listed) */}
        {n(ipo.return_listing_open) !== 0 && (
          <SectionToggle label="📈 Actual results (post-listing)">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, padding: "4px 0 8px" }}>
              {[
                { label: "Open", value: ipo.return_listing_open },
                { label: "Day 7", value: ipo.return_day7 },
                { label: "Month 1", value: ipo.return_day30 },
                { label: "Month 3", value: ipo.return_day90 },
              ].map(r => (
                <div key={r.label} style={{ background: n(r.value) > 0 ? T.greenBg : T.redBg,
                  borderRadius: 8, padding: "8px 10px",
                  border: `1px solid ${n(r.value) > 0 ? T.greenBd : T.redBd}` }}>
                  <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600, marginBottom: 2 }}>{r.label}</div>
                  <div style={{ fontSize: 15, fontWeight: 700,
                    color: n(r.value) > 0 ? T.green : T.red }}>
                    {r.value != null ? pct(n(r.value)) : "—"}
                  </div>
                </div>
              ))}
            </div>
          </SectionToggle>
        )}

        {/* Similar IPOs */}
        {ipo.similar_ipos && (
          <SectionToggle label="🔍 Similar historical IPOs">
            <div style={{ padding: "4px 0 8px" }}>
              {(() => {
                try {
                  const sims = typeof ipo.similar_ipos === 'string' ? JSON.parse(ipo.similar_ipos) : ipo.similar_ipos
                  return sims.slice(0,4).map((s: string, i: number) => (
                    <div key={i} style={{ fontSize: 12, color: T.textSub,
                      padding: "4px 0", borderBottom: `1px solid ${T.border2}` }}>
                      {i+1}. {s}
                    </div>
                  ))
                } catch { return null }
              })()}
            </div>
          </SectionToggle>
        )}
      </div>
    </div>
  )
}

// ── Filter bar ────────────────────────────────────────────────────────────────
const PLAY_FILTERS = [
  { id: "all",             label: "All IPOs" },
  { id: "BUY_AT_OPEN",    label: "🟢 Buy at Open" },
  { id: "WAIT_FOR_VWAP",  label: "🔵 Wait VWAP" },
  { id: "BUY_PANIC_DIP",  label: "🔵 Panic Dip" },
  { id: "BUY_AFTER_DAY3", label: "⚪ Day 3+" },
  { id: "BUY_PEER",       label: "🟠 Buy Peer" },
  { id: "AVOID",          label: "🔴 Avoid" },
]

// ── Main screen ───────────────────────────────────────────────────────────────
export function IpoPlaybookScreen() {
  const [ipos,    setIpos]    = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState("all")
  const [search,  setSearch]  = useState("")
  const [selected,setSelected]= useState<any | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch("/api/ipo/intelligence?limit=50")
      const d = await r.json()
      setIpos(d.ipos ?? [])
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  if (selected) return (
    <div style={{ background: T.bg, minHeight: "100vh", padding: "16px" }}>
      <button onClick={() => setSelected(null)}
        style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 16,
          padding: "8px 14px", borderRadius: 8, border: `1px solid ${T.border}`,
          background: T.surface, fontSize: 13, cursor: "pointer", color: T.textSub }}>
        ← Back to all IPOs
      </button>
      <PlaybookCard ipo={selected} onClose={() => setSelected(null)}/>
    </div>
  )

  const filtered = ipos.filter(i => {
    const play = i.play_recommendation || i.suggested_action?.replace(/\s+/g,'_').toUpperCase() || "AVOID"
    if (filter !== "all" && play !== filter) return false
    if (search && !i.company_name?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ background: T.bg, minHeight: "100vh", paddingBottom: 80 }}>

      {/* Header */}
      <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "14px 20px", position: "sticky", top: 52, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: T.text }}>IPO Playbook</div>
            <div style={{ fontSize: 12, color: T.textSub }}>
              Can I make money from this IPO in 1–5 sessions?
            </div>
          </div>
          <button onClick={load} style={{ display: "flex", alignItems: "center", gap: 5,
            padding: "7px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
            background: T.surface, fontSize: 12, color: T.textSub, cursor: "pointer" }}>
            <RefreshCw size={12}/> Refresh
          </button>
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search IPOs…"
          style={{ width: "100%", padding: "8px 12px", borderRadius: 8,
            border: `1px solid ${T.border}`, fontSize: 13,
            fontFamily: "inherit", outline: "none", boxSizing: "border-box" as const,
            marginBottom: 10 }}/>
        <div style={{ display: "flex", gap: 6, overflowX: "auto" as const, paddingBottom: 2 }}>
          {PLAY_FILTERS.map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)}
              style={{ padding: "5px 12px", borderRadius: 20, flexShrink: 0,
                border: `1px solid ${filter===f.id ? T.blue : T.border}`,
                background: filter===f.id ? T.blueBg : T.surface,
                color: filter===f.id ? T.blue : T.textSub,
                fontSize: 12, fontWeight: filter===f.id ? 700 : 400, cursor: "pointer" }}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "14px 16px 0" }}>
        {loading ? (
          <div style={{ padding: "60px 0", textAlign: "center" as const, color: T.textMeta }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📊</div>
            <div>Loading IPO playbook…</div>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center" as const, color: T.textMeta }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>🔍</div>
            <div>No IPOs match this filter</div>
          </div>
        ) : filtered.map((ipo: any) => {
          const play    = ipo.play_recommendation || ipo.suggested_action?.replace(/\s+/g,'_').toUpperCase() || "AVOID"
          const playCfg = PLAY_CFG[play as keyof typeof PLAY_CFG] ?? PLAY_CFG.AVOID
          const conf    = n(ipo.play_confidence || ipo.confidence_level || 60)
          const reasons = (() => { try { return JSON.parse(ipo.play_reasons || '[]') } catch { return [] } })()

          return (
            <div key={ipo.id || ipo.company_name}
              onClick={() => setSelected(ipo)}
              style={{ background: T.surface, border: `1px solid ${playCfg.bd}`,
                borderLeft: `4px solid ${playCfg.color}`,
                borderRadius: 14, padding: "14px 16px", marginBottom: 10,
                cursor: "pointer", transition: "box-shadow 0.15s" }}
              onMouseEnter={e => (e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.08)")}
              onMouseLeave={e => (e.currentTarget.style.boxShadow = "none")}>

              {/* Row 1 */}
              <div style={{ display: "flex", justifyContent: "space-between",
                alignItems: "flex-start", marginBottom: 8 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: T.text }}>
                      {ipo.company_name}
                    </span>
                    {ipo.is_sme && <Pill label="SME" color={T.red} bg={T.redBg}/>}
                    {ipo.sector && <Pill label={ipo.sector} color={T.textSub} bg={T.grayBg}/>}
                  </div>
                  <div style={{ fontSize: 12, color: T.textSub }}>
                    {ipo.listing_date ? `Listed ${new Date(ipo.listing_date).toLocaleDateString("en-IN")}` : "Upcoming"}
                    {n(ipo.issue_size_cr) > 0 && ` · ₹${Math.round(n(ipo.issue_size_cr))}Cr`}
                  </div>
                </div>
                <div style={{ textAlign: "right" as const }}>
                  <div style={{ fontSize: 13, fontWeight: 800, color: playCfg.color,
                    background: playCfg.bg, padding: "3px 10px", borderRadius: 20,
                    border: `1px solid ${playCfg.bd}`, marginBottom: 3 }}>
                    {playCfg.emoji} {playCfg.label}
                  </div>
                  <div style={{ fontSize: 11, color: T.textMeta }}>
                    {Math.round(conf)}% confidence
                  </div>
                </div>
              </div>

              {/* Row 2 — key metrics */}
              <div style={{ display: "flex", gap: 12, marginBottom: 8, fontSize: 12 }}>
                {n(ipo.qib_subscription_x) > 0 && (
                  <span style={{ color: n(ipo.qib_subscription_x) >= 20 ? T.green : T.textSub }}>
                    QIB {n(ipo.qib_subscription_x).toFixed(0)}x
                  </span>
                )}
                {n(ipo.gmp_pct_t1) !== 0 && (
                  <span style={{ color: n(ipo.gmp_pct_t1) > 0 ? T.green : T.red }}>
                    GMP {n(ipo.gmp_pct_t1) > 0 ? "+" : ""}{n(ipo.gmp_pct_t1).toFixed(1)}%
                  </span>
                )}
                {n(ipo.lqi_final) > 0 && (
                  <span style={{ color: n(ipo.lqi_final) >= 70 ? T.green : T.textSub }}>
                    LQI {Math.round(n(ipo.lqi_final))}
                  </span>
                )}
                {n(ipo.anchor_tier1_count) > 0 && (
                  <span style={{ color: T.textSub }}>
                    {Math.round(n(ipo.anchor_tier1_count))} T1 anchors
                  </span>
                )}
                {n(ipo.return_listing_open) !== 0 && (
                  <span style={{ color: n(ipo.return_listing_open) > 0 ? T.green : T.red,
                    fontWeight: 600 }}>
                    Listed {pct(n(ipo.return_listing_open))}
                  </span>
                )}
              </div>

              {/* Top reason */}
              {reasons[0] && (
                <div style={{ fontSize: 11, color: T.textSub,
                  display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <span style={{ color: playCfg.color, fontWeight: 700, flexShrink: 0 }}>→</span>
                  <span>{reasons[0]}</span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
