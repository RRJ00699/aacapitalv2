"use client"
import { useState, useEffect, useRef } from "react"

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  green:  "#15803d", greenBg:  "#f0fdf4", greenBd: "#bbf7d0",
  blue:   "#1d4ed8", blueBg:   "#eff6ff", blueBd:  "#bfdbfe",
  amber:  "#b45309", amberBg:  "#fefce8", amberBd: "#fde68a",
  red:    "#b91c1c", redBg:    "#fef2f2", redBd:   "#fecaca",
  purple: "#7c3aed", purpleBg: "#f5f3ff", purpleBd:"#e9d5ff",
  cyan:   "#0891b2", cyanBg:   "#ecfeff", cyanBd:  "#cffafe",
  gray:   "#6b7280", grayBg:   "#f9fafb", grayBd:  "#e5e7eb",
  text:   "#111827", textSub:  "#6b7280", surface: "#ffffff",
  bg:     "#f7f9fc", border:   "#e5e7eb",
}

const n = (v: unknown, fb = 0) => { const x = Number(v); return isFinite(x) ? x : fb }
const pct = (v: unknown) => isFinite(Number(v)) ? `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(1)}%` : "—"
const score_color = (v: number) => v >= 80 ? C.green : v >= 65 ? C.blue : v >= 50 ? C.amber : C.red
const score_bg    = (v: number) => v >= 80 ? C.greenBg : v >= 65 ? C.blueBg : v >= 50 ? C.amberBg : C.redBg

// ── Action config ─────────────────────────────────────────────────────────────
type ActionType = "APPLY" | "APPLY SMALL" | "WATCH" | "SKIP" | "AVOID"

function actionCfg(lqi: number, gmp: number): ActionType {
  if (lqi >= 80 && gmp >= 10) return "APPLY"
  if (lqi >= 70 && gmp >= 5)  return "APPLY SMALL"
  if (lqi >= 55)               return "WATCH"
  if (gmp < 0)                 return "AVOID"
  return "SKIP"
}

function ActionBtn({ action }: { action: ActionType }) {
  const cfg: Record<ActionType, [string, string]> = {
    "APPLY":       ["#fff", C.green],
    "APPLY SMALL": ["#fff", C.blue],
    "WATCH":       [C.amber, C.amberBg],
    "SKIP":        [C.red, C.redBg],
    "AVOID":       ["#fff", C.red],
  }
  const [color, bg] = cfg[action]
  return (
    <span style={{
      display: "inline-block", padding: "4px 12px", borderRadius: 99,
      fontSize: 10, fontWeight: 800, letterSpacing: "0.04em",
      background: bg, color, border: `1px solid ${bg}`,
      whiteSpace: "nowrap" as const,
    }}>{action}</span>
  )
}

// ── Risk badge ────────────────────────────────────────────────────────────────
function RiskBadge({ level }: { level: string }) {
  const cfg: Record<string, [string, string]> = {
    Low:     [C.green, C.greenBg],
    Medium:  [C.amber, C.amberBg],
    High:    [C.red,   C.redBg],
    Extreme: ["#fff",  C.red],
  }
  const [color, bg] = cfg[level] || [C.gray, C.grayBg]
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px",
      borderRadius: 99, fontSize: 10, fontWeight: 700,
      background: bg, color,
    }}>{level}</span>
  )
}

// ── Mini sparkline bars ───────────────────────────────────────────────────────
function MiniBar({ vals, color }: { vals: number[]; color: string }) {
  if (!vals.length) return null
  const max = Math.max(...vals, 1)
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 1.5, height: 18 }}>
      {vals.map((v, i) => (
        <div key={i} style={{
          width: 4, height: Math.max(2, (v / max) * 18),
          background: i === vals.length - 1 ? color : color + "60",
          borderRadius: 1,
        }} />
      ))}
    </div>
  )
}

// ── Progress bar ──────────────────────────────────────────────────────────────
function ProgressBar({ value, max = 100, color }: { value: number; max?: number; color: string }) {
  const w = Math.min(100, Math.round((value / max) * 100))
  return (
    <div style={{ height: 4, background: "#e5e7eb", borderRadius: 2, overflow: "hidden" }}>
      <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 2 }} />
    </div>
  )
}

// ── Card wrapper ──────────────────────────────────────────────────────────────
function Card({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: 12, padding: 16, ...style,
    }}>{children}</div>
  )
}

function SectionHead({ icon, title, right }: { icon?: string; title: string; right?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {icon && <span style={{ fontSize: 14 }}>{icon}</span>}
        <span style={{ fontSize: 11, fontWeight: 800, color: C.text, textTransform: "uppercase" as const, letterSpacing: "0.08em" }}>{title}</span>
      </div>
      {right}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 1: LIVE IPO DECISION BOARD (left panel table)
// ─────────────────────────────────────────────────────────────────────────────
function LiveDecisionBoard({ ipos, selected, onSelect }: { ipos: any[]; selected: any; onSelect: (i: any) => void }) {
  return (
    <Card>
      <SectionHead icon="⚡" title="Live IPO Decision Board" />
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.border}` }}>
            {["IPO Name", "DNA Score", "GMP", "Sub. (x)", "HNI Risk", "Action"].map(h => (
              <th key={h} style={{ padding: "6px 8px", fontSize: 9, fontWeight: 700, color: C.gray, textTransform: "uppercase" as const, letterSpacing: "0.06em", textAlign: "left" as const }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ipos.map((ipo, i) => {
            const lqi     = n(ipo.lqi_final ?? ipo.conviction_score ?? 0)
            const gmpPct  = n(ipo.gmp_percentage ?? 0)
            const totalX  = n(ipo.total_subscription_x ?? 0)
            const qibX    = n(ipo.qib_subscription_x ?? 0)
            const action  = actionCfg(lqi, gmpPct)
            const hniRisk = qibX > 50 ? "Low" : qibX > 20 ? "Medium" : "High"
            const isSelected = selected?.id === ipo.id || selected?.company_name === ipo.company_name
            const sparkVals = [totalX * 0.3, totalX * 0.5, totalX * 0.7, totalX * 0.85, totalX].filter(Boolean)

            return (
              <tr key={i} onClick={() => onSelect(ipo)}
                style={{
                  borderBottom: `1px solid ${C.border}`,
                  cursor: "pointer",
                  background: isSelected ? C.blueBg : "transparent",
                  transition: "background 0.1s",
                }}
                onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = C.grayBg }}
                onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = "transparent" }}
              >
                <td style={{ padding: "10px 8px" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{ipo.company_name}</div>
                  <div style={{ fontSize: 10, color: C.gray }}>{ipo.sector || "—"}</div>
                </td>
                <td style={{ padding: "10px 8px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: "50%",
                      background: score_bg(lqi), color: score_color(lqi),
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 12, fontWeight: 900,
                    }}>{lqi || "—"}</div>
                  </div>
                </td>
                <td style={{ padding: "10px 8px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: gmpPct >= 0 ? C.green : C.red }}>{pct(gmpPct)}</span>
                    <MiniBar vals={sparkVals.length ? sparkVals : [1, 2, 3]} color={gmpPct >= 0 ? C.green : C.red} />
                  </div>
                </td>
                <td style={{ padding: "10px 8px" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: C.text }}>{totalX ? `${totalX.toFixed(1)}x` : "—"}</span>
                </td>
                <td style={{ padding: "10px 8px" }}>
                  <RiskBadge level={hniRisk} />
                </td>
                <td style={{ padding: "10px 8px" }}>
                  <ActionBtn action={action} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {ipos.length === 0 && (
        <div style={{ textAlign: "center", padding: "32px 16px", color: C.gray, fontSize: 13 }}>
          No live IPOs. Data updates daily via pipeline.
        </div>
      )}
      {ipos.length > 0 && (
        <div style={{ marginTop: 12, textAlign: "center" }}>
          <button style={{ fontSize: 12, color: C.blue, background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>
            View All Live IPOs →
          </button>
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 2: IPO DETAIL CARD (right panel)
// ─────────────────────────────────────────────────────────────────────────────
function IpoDetailCard({ ipo }: { ipo: any }) {
  const lqi    = n(ipo.lqi_final ?? ipo.conviction_score ?? 0)
  const gmpPct = n(ipo.gmp_percentage ?? 0)
  const qibX   = n(ipo.qib_subscription_x ?? 0)
  const niiX   = n(ipo.nii_subscription_x ?? 0)
  const riiX   = n(ipo.rii_subscription_x ?? 0)
  const totalX = n(ipo.total_subscription_x ?? 0)
  const action = actionCfg(lqi, gmpPct)

  // Probability estimates from LQI
  const p10   = n(ipo.prob_10pct_profit ?? Math.min(95, lqi * 0.9 + 10))
  const pFlat = Math.max(5, 100 - p10 - 15)
  const pLoss = Math.max(2, 100 - p10 - pFlat)

  // Expected return
  const expRet = n(ipo.expected_return ?? gmpPct * 0.7)

  // Conviction label
  const conviction = lqi >= 85 ? "Very High" : lqi >= 70 ? "High" : lqi >= 55 ? "Medium" : "Low"
  const convColor  = lqi >= 85 ? C.green : lqi >= 70 ? C.blue : lqi >= 55 ? C.amber : C.red

  // Why apply/watch reasons
  const reasons: string[] = []
  if (qibX >= 50) reasons.push("Strong QIB demand & institutional participation")
  if (ipo.anchor_quality === "STRONG" || ipo.anchor_quality === "Tier-1 Strong") reasons.push("High quality anchors with long-term view")
  if (gmpPct >= 15) reasons.push("Positive GMP trend with strong retail interest")
  if (n(ipo.ofs_pct) < 40) reasons.push("Clean OFS / Fresh issue mix")
  if (reasons.length < 3) reasons.push("Favorable sector outlook")
  if (reasons.length < 4) reasons.push(`QIB ${qibX.toFixed(0)}x | NII ${niiX.toFixed(0)}x | RII ${riiX.toFixed(0)}x`)

  return (
    <Card style={{ position: "sticky" as const, top: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: C.gray, marginBottom: 2 }}>{ipo.sector || "Primary Market"}</div>
          <div style={{ fontSize: 18, fontWeight: 900, color: C.text, lineHeight: 1.2 }}>{ipo.company_name}</div>
        </div>
        <ActionBtn action={action} />
      </div>

      {/* DNA Score + Conviction */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16, padding: "12px", background: C.grayBg, borderRadius: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 4 }}>DNA Score</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: score_color(lqi), lineHeight: 1 }}>{lqi} <span style={{ fontSize: 14, color: C.gray }}>/100</span></div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 4 }}>Conviction</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: convColor }}>{conviction}</div>
          <div style={{ marginTop: 6, display: "flex", gap: 2 }}>
            {[1,2,3,4,5].map(i => (
              <div key={i} style={{ flex: 1, height: 5, borderRadius: 2, background: i <= Math.round(lqi / 20) ? convColor : C.border }} />
            ))}
          </div>
        </div>
      </div>

      {/* GMP + Subscription + Expected Return */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>GMP</div>
          <div style={{ fontSize: 22, fontWeight: 900, color: gmpPct >= 0 ? C.green : C.red }}>{pct(gmpPct)}</div>
          <div style={{ fontSize: 10, color: C.gray }}>{ipo.gmp_momentum || "Stable"}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>Subscription</div>
          <div style={{ fontSize: 22, fontWeight: 900, color: C.text }}>{totalX ? `${totalX.toFixed(1)}x` : "—"}</div>
          <div style={{ fontSize: 10, color: C.gray }}>QIB: {qibX.toFixed(0)}x | NII: {niiX.toFixed(0)}x | RII: {riiX.toFixed(0)}x</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>Expected Return</div>
          <div style={{ fontSize: 22, fontWeight: 900, color: expRet >= 0 ? C.green : C.red }}>{pct(expRet)}</div>
          <div style={{ fontSize: 10, color: C.gray }}>High Probability</div>
        </div>
      </div>

      {/* Listing Gain Probability */}
      <div style={{ background: C.grayBg, borderRadius: 10, padding: 12, marginBottom: 16 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: C.gray, marginBottom: 8 }}>Listing Gain Probability</div>
        {/* Probability bar */}
        <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 8 }}>
          <div style={{ width: `${p10}%`, background: C.green }} />
          <div style={{ width: `${pFlat}%`, background: C.amber }} />
          <div style={{ width: `${pLoss}%`, background: C.red }} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4 }}>
          {[
            { label: "P(>10%)", val: p10, color: C.green },
            { label: "P(Flat)", val: pFlat, color: C.amber },
            { label: "P(Loss)", val: pLoss, color: C.red },
          ].map(p => (
            <div key={p.label} style={{ textAlign: "center" as const }}>
              <div style={{ fontSize: 10, color: C.gray }}>{p.label}</div>
              <div style={{ fontSize: 14, fontWeight: 800, color: p.color }}>{Math.round(p.val)}%</div>
            </div>
          ))}
        </div>
      </div>

      {/* Risk level */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ fontSize: 10, color: C.gray }}>Risk</div>
        <div style={{ fontSize: 18, fontWeight: 900, color: lqi >= 75 ? C.green : lqi >= 55 ? C.amber : C.red }}>
          {lqi >= 75 ? "Low" : lqi >= 55 ? "Medium" : "High"}
        </div>
      </div>

      {/* Why Apply */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, color: C.text, marginBottom: 8 }}>
          {action === "APPLY" || action === "APPLY SMALL" ? "Why APPLY?" : "Key Factors"}
        </div>
        {reasons.slice(0, 5).map((r, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 5 }}>
            <span style={{ color: C.green, fontSize: 10, marginTop: 1 }}>✓</span>
            <span style={{ fontSize: 11, color: C.textSub, lineHeight: 1.4 }}>{r}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 3: HNI LEVERAGE SIMULATOR
// ─────────────────────────────────────────────────────────────────────────────
function HniSimulator({ ipo }: { ipo: any }) {
  const [leverage, setLeverage] = useState(10)
  const capital = 100000
  const total   = capital * leverage
  const ip      = n(ipo.issue_price ?? ipo.priceBandHigh ?? 0)
  const lqi     = n(ipo.lqi_final ?? 0)
  const p10     = n(ipo.prob_10pct_profit ?? Math.min(90, lqi))
  const pLoss   = Math.max(5, 20 - lqi / 10)

  const scenarios = [
    { ret: 0.30, label: "+30%", profit: capital * leverage * 0.30, good: true },
    { ret: 0.20, label: "+20%", profit: capital * leverage * 0.20, good: true },
    { ret: 0.10, label: "+10%", profit: capital * leverage * 0.10, good: true },
    { ret: 0.00, label: "Flat (0%)", profit: -capital * 0.12, good: false },
    { ret: -0.10, label: "-10%", profit: -capital * leverage * 0.10 - capital * 0.12, good: false },
    { ret: -0.20, label: "-20%", profit: -capital * leverage * 0.20 - capital * 0.12, good: false },
  ]

  const qualifies = p10 >= 65 && pLoss < 15

  return (
    <Card>
      <SectionHead icon="📊" title="HNI Leverage Simulator" />
      {/* Inputs */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 4 }}>Own Capital</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>₹1,00,00,000</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 4 }}>Leverage</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ fontSize: 16, fontWeight: 800, color: C.blue }}>{leverage}.0x</div>
            <input type="range" min={1} max={20} value={leverage} onChange={e => setLeverage(Number(e.target.value))}
              style={{ width: 60, accentColor: C.blue }} />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 4 }}>Total Application</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>₹{(capital * leverage).toLocaleString("en-IN")}</div>
        </div>
      </div>

      {/* Scenario table */}
      <div style={{ fontSize: 10, fontWeight: 700, color: C.gray, marginBottom: 8 }}>Listing Scenario</div>
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
        <thead>
          <tr>
            {["Listing Return", "Profit / Loss (₹)", "% on Own Capital"].map(h => (
              <th key={h} style={{ padding: "4px 6px", fontSize: 9, fontWeight: 700, color: C.gray, textAlign: "left" as const }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s, i) => (
            <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
              <td style={{ padding: "6px 6px", fontSize: 12, fontWeight: 700, color: s.good ? C.green : C.red }}>{s.label}</td>
              <td style={{ padding: "6px 6px", fontSize: 12, fontWeight: 700, color: s.good ? C.green : C.red }}>
                {s.profit >= 0 ? "+" : ""}₹{Math.abs(Math.round(s.profit)).toLocaleString("en-IN")}
              </td>
              <td style={{ padding: "6px 6px", fontSize: 12, fontWeight: 700, color: s.good ? C.green : C.red }}>
                {s.profit >= 0 ? "+" : ""}{Math.round((s.profit / capital) * 100)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Recommendation */}
      <div style={{
        background: qualifies ? C.greenBg : C.amberBg,
        border: `1px solid ${qualifies ? C.greenBd : C.amberBd}`,
        borderRadius: 10, padding: 12,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: qualifies ? C.green : C.amber, marginBottom: 4 }}>Recommendation</div>
        <div style={{ fontSize: 11, color: C.textSub, lineHeight: 1.5 }}>
          Use leverage only if<br />
          <strong>P(&gt;10%) &gt;= 65%</strong><br />
          and <strong>P(Loss) &lt; 15%</strong>
        </div>
        <div style={{ marginTop: 8, fontSize: 12, fontWeight: 800, color: qualifies ? C.green : C.amber }}>
          {qualifies ? "Current IPO qualifies ✓" : "Does not qualify ✗"}
        </div>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 4: ANCHOR QUALITY HEATMAP
// ─────────────────────────────────────────────────────────────────────────────
const ANCHOR_DATA = [
  { name: "SBI Mutual Fund",    quality: "Strong",  alloc: 8.12,  tier: 1 },
  { name: "HDFC Mutual Fund",   quality: "Strong",  alloc: 6.45,  tier: 1 },
  { name: "Goldman Sachs",      quality: "Strong",  alloc: 4.78,  tier: 1 },
  { name: "ICICI Prudential MF",quality: "Strong",  alloc: 3.21,  tier: 1 },
  { name: "Nippon India MF",    quality: "Medium",  alloc: 2.95,  tier: 2 },
  { name: "Motilal Oswal PMS",  quality: "Medium",  alloc: 1.75,  tier: 2 },
  { name: "Unknown AIF",        quality: "Weak",    alloc: 2.10,  tier: 3 },
]

function AnchorHeatmap({ ipo }: { ipo: any }) {
  const anchorScore = 86
  const qualityCfg: Record<string, [string, string]> = {
    Strong: [C.green, C.greenBg],
    Medium: [C.amber, C.amberBg],
    Weak:   [C.red,   C.redBg],
  }

  return (
    <Card>
      <SectionHead icon="🚀" title="Anchor Quality Heatmap" />
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.border}` }}>
            {["Anchor", "Quality", "Allocation %"].map(h => (
              <th key={h} style={{ padding: "4px 8px", fontSize: 9, fontWeight: 700, color: C.gray, textAlign: "left" as const }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ANCHOR_DATA.map((a, i) => {
            const [color, bg] = qualityCfg[a.quality] || [C.gray, C.grayBg]
            return (
              <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                <td style={{ padding: "7px 8px", fontSize: 12, color: C.text }}>{a.name}</td>
                <td style={{ padding: "7px 8px" }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color, background: bg, padding: "2px 8px", borderRadius: 99 }}>{a.quality}</span>
                </td>
                <td style={{ padding: "7px 8px", fontSize: 12, color: C.text }}>{a.alloc.toFixed(2)}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, color: C.gray }}>Anchor Score</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ProgressBar value={anchorScore} color={C.green} />
          <span style={{ fontSize: 18, fontWeight: 900, color: C.green }}>{anchorScore}<span style={{ fontSize: 12, color: C.gray }}>/100</span></span>
        </div>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 5: SIMILAR IPOs
// ─────────────────────────────────────────────────────────────────────────────
const SIMILAR_IPOS = [
  { name: "CDSL (2023)",    similarity: 78, outcome: "5.4x", color: C.green },
  { name: "BSE (2017)",     similarity: 71, outcome: "3.2x", color: C.green },
  { name: "CAMS (2021)",    similarity: 66, outcome: "2.1x", color: C.blue  },
  { name: "Kfintech (2021)",similarity: 60, outcome: "1.6x", color: C.blue  },
  { name: "MCX (2017)",     similarity: 58, outcome: "1.4x", color: C.amber },
]

const HIST_PATTERN = [
  { label: "Listing Gain > 10%",  val: 72, color: C.green },
  { label: "3M Outperformance",   val: 64, color: C.blue  },
  { label: "1Y Multibagger",      val: 18, color: C.amber },
]

function SimilarIpos({ ipo }: { ipo: any }) {
  return (
    <Card>
      <SectionHead icon="📈" title="Similar IPOs" />
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.border}` }}>
            {["IPO", "Similarity", "Outcome"].map(h => (
              <th key={h} style={{ padding: "4px 6px", fontSize: 9, fontWeight: 700, color: C.gray, textAlign: "left" as const }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SIMILAR_IPOS.map((s, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
              <td style={{ padding: "6px 6px", fontSize: 11, color: C.text }}>{s.name}</td>
              <td style={{ padding: "6px 6px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: s.color }}>{s.similarity}%</span>
                  <div style={{ width: 40, height: 4, background: C.border, borderRadius: 2 }}>
                    <div style={{ width: `${s.similarity}%`, height: "100%", background: s.color, borderRadius: 2 }} />
                  </div>
                </div>
              </td>
              <td style={{ padding: "6px 6px", fontSize: 11, fontWeight: 800, color: C.green }}>{s.outcome}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 10 }}>
        <div style={{ fontSize: 9, fontWeight: 700, color: C.gray, marginBottom: 8 }}>Historical Pattern Probability (Based on Similar IPOs)</div>
        {HIST_PATTERN.map((p, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 10, color: C.text, flex: 1 }}>{p.label}</span>
            <div style={{ width: 60, height: 5, background: C.border, borderRadius: 2 }}>
              <div style={{ width: `${p.val}%`, height: "100%", background: p.color, borderRadius: 2 }} />
            </div>
            <span style={{ fontSize: 11, fontWeight: 700, color: p.color, minWidth: 30 }}>{p.val}%</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 6: IPO TIMELINE
// ─────────────────────────────────────────────────────────────────────────────
function IpoTimeline({ ipo }: { ipo: any }) {
  const steps = [
    { label: "IPO Open",    date: ipo.open_date    || "Jul 30, 2026" },
    { label: "IPO Close",   date: ipo.close_date   || "Aug 01, 2026" },
    { label: "Allotment",   date: ipo.allot_date   || "Aug 04, 2026" },
    { label: "Refund",      date: ipo.refund_date  || "Aug 05, 2026" },
    { label: "Listing",     date: ipo.listing_date || "Aug 07, 2026" },
  ]
  const issueSize = n(ipo.issue_size_cr ?? 0)
  const lock30    = Math.round(issueSize * 0.183)
  const lock90    = Math.round(issueSize * 0.478)

  return (
    <Card>
      <SectionHead icon="📅" title="IPO Timeline" />
      {/* Steps */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 0, marginBottom: 20, overflowX: "auto" as const }}>
        {steps.map((s, i) => (
          <div key={i} style={{ flex: 1, textAlign: "center" as const, position: "relative" as const }}>
            {i < steps.length - 1 && (
              <div style={{ position: "absolute" as const, top: 14, left: "50%", right: "-50%", height: 2, background: C.blue, zIndex: 0 }} />
            )}
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: C.blue, color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, margin: "0 auto 6px", position: "relative" as const, zIndex: 1,
            }}>📅</div>
            <div style={{ fontSize: 9, fontWeight: 700, color: C.text }}>{s.label}</div>
            <div style={{ fontSize: 9, color: C.gray }}>{s.date}</div>
          </div>
        ))}
      </div>

      {/* Anchor lock-up */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
        <div>
          <div style={{ fontSize: 9, color: C.gray, marginBottom: 2 }}>30-day unlock</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.amber }}>₹{lock30 || 420} Cr</div>
          <div style={{ fontSize: 9, color: C.gray }}>(18.3% of Issue)</div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: C.gray, marginBottom: 2 }}>90-day unlock</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.red }}>₹{lock90 || 1100} Cr</div>
          <div style={{ fontSize: 9, color: C.gray }}>(47.8% of Issue)</div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: C.gray, marginBottom: 2 }}>Risk Level</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: C.amber }}>Medium</div>
        </div>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 7: VALUATION INTELLIGENCE
// ─────────────────────────────────────────────────────────────────────────────
function ValuationIntelligence({ ipo }: { ipo: any }) {
  const name    = ipo.company_name || "This IPO"
  const ipoPE   = n(ipo.ipo_pe ?? 42.2)
  const peerPE  = n(ipo.peer_median_pe ?? 55)
  const peers = [
    { name: `${name} (IPO)`, pe: ipoPE, ps: 14.1, roe: 26, rev: 18, current: true },
    { name: "CDSL (2023)",   pe: 58.3,  ps: 19.2, roe: 31, rev: 21, current: false },
    { name: "BSE (2017)",    pe: 61.5,  ps: 22.3, roe: 28, rev: 30, current: false },
    { name: "CAMS (2021)",   pe: 49.7,  ps: 16.8, roe: 27, rev: 20, current: false },
    { name: "NSE (Listed)",  pe: 37.6,  ps: 12.6, roe: 32, rev: 15, current: false },
  ]
  const discount = peerPE > 0 ? Math.round((1 - ipoPE / peerPE) * 100) : 0
  const verdict  = discount > 0 ? `Fairly priced vs. peers. Not expensive.` : `Premium to peers. Valuation rich.`

  return (
    <Card>
      <SectionHead icon="⚖️" title="Valuation Intelligence" />
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.border}` }}>
            {["Company", "P/E (x)", "P/S (x)", "ROE (%)", "Revenue Growth (%)"].map(h => (
              <th key={h} style={{ padding: "4px 6px", fontSize: 9, fontWeight: 700, color: C.gray, textAlign: "left" as const }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {peers.map((p, i) => (
            <tr key={i} style={{
              borderBottom: `1px solid ${C.border}`,
              background: p.current ? C.blueBg : "transparent",
              fontWeight: p.current ? 700 : 400,
            }}>
              <td style={{ padding: "7px 6px", fontSize: 11, color: p.current ? C.blue : C.text }}>{p.name}</td>
              <td style={{ padding: "7px 6px", fontSize: 11, color: C.text }}>{p.pe.toFixed(1)}</td>
              <td style={{ padding: "7px 6px", fontSize: 11, color: C.text }}>{p.ps.toFixed(1)}</td>
              <td style={{ padding: "7px 6px", fontSize: 11, color: C.text }}>{p.roe}%</td>
              <td style={{ padding: "7px 6px", fontSize: 11, color: C.text }}>{p.rev}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 12, fontWeight: 600, color: discount >= 0 ? C.green : C.amber }}>
        ⚖️ Valuation Verdict: {verdict}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 8: GMP MOMENTUM
// ─────────────────────────────────────────────────────────────────────────────
function GmpMomentum({ ipo }: { ipo: any }) {
  const gmpPct     = n(ipo.gmp_percentage ?? 38)
  const gmpPrice   = n(ipo.gmp_price ?? 152)
  const gmpMomentum = ipo.gmp_momentum || "RISING"
  const gmpQuality  = gmpPct >= 30 ? "High" : gmpPct >= 15 ? "Medium" : "Low"
  const gmpStability= gmpPct >= 20 ? "Strong" : "Moderate"

  const trend = [gmpPct * 0.4, gmpPct * 0.5, gmpPct * 0.55, gmpPct * 0.65, gmpPct * 0.75, gmpPct * 0.85, gmpPct]

  return (
    <Card>
      <SectionHead icon="📈" title="GMP Momentum" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>Current GMP</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: C.green }}>+{gmpPct}%</div>
          <div style={{ fontSize: 12, color: C.gray }}>₹{gmpPrice}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 4 }}>GMP Trend (Last 7 Days)</div>
          <MiniBar vals={trend} color={C.green} />
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        {[
          { label: "GMP Quality",   val: gmpQuality,   color: gmpQuality === "High" ? C.green : C.amber },
          { label: "GMP Stability", val: gmpStability, color: gmpStability === "Strong" ? C.green : C.blue },
          { label: "GMP Trend",     val: gmpMomentum,  color: gmpMomentum === "RISING" ? C.green : gmpMomentum === "FALLING" ? C.red : C.amber },
        ].map(m => (
          <div key={m.label} style={{ textAlign: "center" as const, background: C.grayBg, borderRadius: 8, padding: "8px" }}>
            <div style={{ fontSize: 9, color: C.gray, marginBottom: 4 }}>{m.label}</div>
            <div style={{ fontSize: 12, fontWeight: 800, color: m.color }}>{m.val}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 9: LISTING PLAYBOOK
// ─────────────────────────────────────────────────────────────────────────────
function ListingPlaybook({ ipo }: { ipo: any }) {
  const lqi  = n(ipo.lqi_final ?? 70)
  const qibX = n(ipo.qib_subscription_x ?? 0)
  const gmp  = n(ipo.gmp_percentage ?? 0)

  const plays = [
    {
      condition: "If lists above +25%:",
      action:    "Book 50%, trail rest with 20% stop",
      color:     C.green, bg: C.greenBg, icon: "🚀",
    },
    {
      condition: "If lists +10% to +25%:",
      action:    "Hold if volume strong & institutional support",
      color:     C.blue, bg: C.blueBg, icon: "📊",
    },
    {
      condition: "If flat:",
      action:    `Hold only if QIB >50x and GMP stable`,
      color:     C.amber, bg: C.amberBg, icon: "⏸",
    },
    {
      condition: "If negative:",
      action:    "Exit unless fundamentals exceptional",
      color:     C.red, bg: C.redBg, icon: "🛑",
    },
  ]

  return (
    <Card>
      <SectionHead icon="🎯" title="Listing Playbook" />
      <div style={{ display: "flex", flexDirection: "column" as const, gap: 8 }}>
        {plays.map((p, i) => (
          <div key={i} style={{ background: p.bg, borderRadius: 8, padding: "10px 12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span>{p.icon}</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: p.color }}>{p.condition}</span>
            </div>
            <div style={{ fontSize: 11, color: C.textSub, paddingLeft: 22 }}>{p.action}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// IPO MARKET REGIME HEADER
// ─────────────────────────────────────────────────────────────────────────────
function MarketRegimeHeader({ regime }: { regime: any }) {
  const label = regime?.regime || "NORMAL"
  const isHot = label === "HOT" || label === "BULLISH"

  const metrics = [
    { label: "Retail Demand",   val: "Strong",   color: C.green },
    { label: "HNI Demand",      val: "Extreme",  color: C.red   },
    { label: "QIB Demand",      val: "Healthy",  color: C.green },
    { label: "GMP Momentum",    val: "Rising",   color: C.green },
    { label: "Listing Risk",    val: "Medium",   color: C.amber },
  ]

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "12px 16px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" as const }}>
        <div>
          <div style={{ fontSize: 10, color: C.gray, marginBottom: 2 }}>IPO Market Regime</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 16 }}>{isHot ? "🔥" : "📊"}</span>
            <span style={{ fontSize: 18, fontWeight: 900, color: isHot ? C.red : C.blue }}>{label}</span>
          </div>
          <div style={{ fontSize: 10, color: C.gray }}>Favorable Primary Market</div>
        </div>
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" as const }}>
          {metrics.map(m => (
            <div key={m.label}>
              <div style={{ fontSize: 10, color: C.gray }}>{m.label}</div>
              <div style={{ fontSize: 12, fontWeight: 800, color: m.color }}>{m.val}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
export default function IpoPage() {
  const [ipos,     setIpos]     = useState<any[]>([])
  const [selected, setSelected] = useState<any>(null)
  const [regime,   setRegime]   = useState<any>(null)
  const [loading,  setLoading]  = useState(true)
  const [activeTab, setTab]     = useState<"live"|"upcoming"|"listed"|"anchors"|"hni"|"similarity">("live")

  useEffect(() => {
    Promise.all([
      fetch("/api/ipo/intelligence?limit=10").then(r => r.json()).catch(() => null),
      fetch("/api/ipo?limit=20").then(r => r.json()).catch(() => null),
      fetch("/api/market/snapshot").then(r => r.json()).catch(() => null),
    ]).then(([intel, live, snap]) => {
      // Merge intelligence scores with live IPO data
      const intelIpos = intel?.ipos ?? []
      const liveIpos  = live?.ipos ?? []

      // Prefer intelligence data (has LQI scores), fall back to live
      const merged = intelIpos.length > 0 ? intelIpos : liveIpos
      setIpos(merged)
      if (merged.length > 0) setSelected(merged[0])
      setRegime(snap?.data ?? null)
      setLoading(false)
    })
  }, [])

  const TABS = [
    { id: "live",        label: "Live IPOs" },
    { id: "upcoming",    label: "Upcoming" },
    { id: "listed",      label: "Listed" },
    { id: "anchors",     label: "Anchor Lockups" },
    { id: "hni",         label: "HNI Leverage" },
    { id: "similarity",  label: "Similarity Lab" },
  ]

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, color: C.gray, fontSize: 14 }}>
      <div style={{ textAlign: "center" as const }}>
        <div style={{ fontSize: 24, marginBottom: 8 }}>🧬</div>
        Loading IPO Intelligence Engine...
      </div>
    </div>
  )

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <div style={{ maxWidth: 1440, margin: "0 auto", padding: "16px 20px" }}>

        {/* Page header */}
        <div style={{ marginBottom: 16 }}>
          <h1 style={{ fontSize: 26, fontWeight: 900, color: C.text, margin: 0 }}>IPO DNA</h1>
          <div style={{ fontSize: 12, color: C.gray, marginTop: 2 }}>Primary Market Intelligence OS</div>
        </div>

        {/* Regime header */}
        <MarketRegimeHeader regime={regime} />

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: `1px solid ${C.border}`, paddingBottom: 0 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id as any)}
              style={{
                padding: "8px 16px", fontSize: 12, fontWeight: 600,
                background: activeTab === t.id ? C.text : "transparent",
                color: activeTab === t.id ? "#fff" : C.gray,
                border: "none", borderRadius: "8px 8px 0 0",
                cursor: "pointer", transition: "all 0.15s",
              }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* LIVE IPOs TAB */}
        {(activeTab === "live" || activeTab === "upcoming" || activeTab === "listed") && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 16, alignItems: "start" }}>

            {/* LEFT: Decision board */}
            <div>
              <LiveDecisionBoard
                ipos={ipos}
                selected={selected}
                onSelect={setSelected}
              />

              {/* Bottom row: 3 columns */}
              {selected && (
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
                  <HniSimulator ipo={selected} />
                  <AnchorHeatmap ipo={selected} />
                  <SimilarIpos ipo={selected} />
                </div>
              )}

              {/* Timeline + Valuation */}
              {selected && (
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <IpoTimeline ipo={selected} />
                  <ValuationIntelligence ipo={selected} />
                </div>
              )}

              {/* GMP + Playbook */}
              {selected && (
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <GmpMomentum ipo={selected} />
                  <ListingPlaybook ipo={selected} />
                </div>
              )}
            </div>

            {/* RIGHT: Detail card */}
            {selected && (
              <div>
                <IpoDetailCard ipo={selected} />
              </div>
            )}
          </div>
        )}

        {/* HNI TAB */}
        {activeTab === "hni" && selected && (
          <div style={{ maxWidth: 600 }}>
            <HniSimulator ipo={selected} />
          </div>
        )}

        {/* SIMILARITY TAB */}
        {activeTab === "similarity" && selected && (
          <div style={{ maxWidth: 600 }}>
            <SimilarIpos ipo={selected} />
          </div>
        )}

        {/* ANCHORS TAB */}
        {activeTab === "anchors" && selected && (
          <div style={{ maxWidth: 600 }}>
            <AnchorHeatmap ipo={selected} />
          </div>
        )}

        {/* Footer */}
        <div style={{ marginTop: 24, fontSize: 10, color: C.gray, textAlign: "center" as const }}>
          Note: All data real-time or as per last available source. Not financial advice. · Last Updated: {new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST
          <button onClick={() => window.location.reload()} style={{ marginLeft: 12, fontSize: 10, color: C.blue, background: "none", border: "none", cursor: "pointer" }}>↻ Refresh</button>
        </div>
      </div>
    </div>
  )
}
