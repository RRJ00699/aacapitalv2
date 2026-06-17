"use client"
// components/ipo/IpoCommandCenter.tsx
// IPO ALPHA TERMINAL — Premium institutional IPO OS
// Beats Chittorgarh + InvestorGain + IPO Central combined
// Mobile-first, live data from /api/ipo + /api/ipo/intelligence

import { useState, useEffect, useCallback, useRef } from "react"
import { RefreshCw, ChevronDown, ChevronUp, Zap, TrendingUp, Eye, 
         Shield, AlertTriangle, Activity, Target, Clock, BarChart2 } from "lucide-react"

// ── Design system ─────────────────────────────────────────────────────────────
const C = {
  green:    "#15803D", greenBg:  "#F0FDF4", greenBd: "#86EFAC",
  blue:     "#1D4ED8", blueBg:   "#EFF6FF", blueBd:  "#93C5FD",
  cyan:     "#0891B2", cyanBg:   "#ECFEFF", cyanBd:  "#67E8F9",
  amber:    "#B45309", amberBg:  "#FFFBEB", amberBd: "#FCD34D",
  red:      "#B91C1C", redBg:    "#FEF2F2", redBd:   "#FCA5A5",
  purple:   "#7C3AED", purpleBg: "#F5F3FF", purpleBd:"#C4B5FD",
  gray:     "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:     "#111827", textSub:  "#6B7280",
  surface:  "#FFFFFF", bg:       "#F7F9FC", border:  "#E5E7EB",
}

const n = (v: unknown, fb = 0) => { const x = Number(v); return isFinite(x) ? x : fb }
const pct = (v: unknown) => isFinite(n(v)) ? `${n(v) >= 0 ? "+" : ""}${n(v).toFixed(1)}%` : "—"

// ── Action config from LQI + GMP ──────────────────────────────────────────────
function getActionCfg(lqi: number, gmpPct: number | null, action?: string) {
  if (action === "MOMENTUM CHASE" || (lqi >= 80 && (gmpPct ?? 0) >= 20))
    return { label: "STRONG APPLY", icon: "🟢", color: C.green, bg: C.greenBg, bd: C.greenBd }
  if (action === "VALUE DIP BUY" || (lqi >= 70 && (gmpPct ?? 0) >= 5))
    return { label: "APPLY",        icon: "🔵", color: C.blue,  bg: C.blueBg,  bd: C.blueBd  }
  if (lqi >= 60)
    return { label: "WATCH",        icon: "🟡", color: C.amber, bg: C.amberBg, bd: C.amberBd }
  if (action === "AVOID" || (gmpPct ?? 0) < -5)
    return { label: "AVOID",        icon: "🔴", color: C.red,   bg: C.redBg,   bd: C.redBd   }
  return   { label: "SKIP",         icon: "⚪", color: C.gray,  bg: C.grayBg,  bd: C.grayBd  }
}

// Also handle legacy recommendation strings from /api/ipo
function getRecCfg(rec: string, lqi?: number, gmpPct?: number | null) {
  if (!rec && lqi !== undefined) return getActionCfg(lqi, gmpPct ?? null)
  const r = rec || ""
  if (r.includes("Aggressively") || r.includes("MOMENTUM"))
    return { label: "STRONG APPLY", icon: "🟢", color: C.green,  bg: C.greenBg,  bd: C.greenBd  }
  if (r.includes("Long-Term") || r.includes("Apply") || r.includes("VALUE"))
    return { label: "APPLY",        icon: "🔵", color: C.blue,   bg: C.blueBg,   bd: C.blueBd   }
  if (r.includes("Listing Trade"))
    return { label: "LISTING ONLY", icon: "💧", color: C.cyan,   bg: C.cyanBg,   bd: C.cyanBd   }
  if (r.includes("Listing Dip"))
    return { label: "BUY AT OPEN",  icon: "👀", color: C.purple, bg: C.purpleBg, bd: C.purpleBd }
  if (r.includes("Watch") || r.includes("Selective"))
    return { label: "WATCH",        icon: "🟡", color: C.amber,  bg: C.amberBg,  bd: C.amberBd  }
  if (r.includes("Avoid") || r === "AVOID")
    return { label: "AVOID",        icon: "🔴", color: C.red,    bg: C.redBg,    bd: C.redBd    }
  return   { label: "WATCH",        icon: "🟡", color: C.amber,  bg: C.amberBg,  bd: C.amberBd  }
}

// ── Reusable primitives ───────────────────────────────────────────────────────
function Bar({ val, max = 100, color, h = 4 }: { val: number; max?: number; color: string; h?: number }) {
  return (
    <div style={{ height: h, background: C.grayBd, borderRadius: h }}>
      <div style={{ height: "100%", width: `${Math.min(100, (val / max) * 100)}%`, background: color, borderRadius: h, transition: "width .4s" }} />
    </div>
  )
}

function Badge({ label, color, bg, bd }: { label: string; color: string; bg: string; bd: string }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 20, background: bg, color, border: `1px solid ${bd}`, whiteSpace: "nowrap" as const }}>
      {label}
    </span>
  )
}

function Divider() {
  return <div style={{ height: 1, background: C.border, margin: "10px 0" }} />
}

function StatBox({ label, val, color = C.text, sub }: { label: string; val: string; color?: string; sub?: string }) {
  return (
    <div>
      <div style={{ fontSize: 9, color: C.gray, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 800, color, lineHeight: 1 }}>{val}</div>
      {sub && <div style={{ fontSize: 9, color: C.gray, marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

// ── Score ring ────────────────────────────────────────────────────────────────
function ScoreRing({ score }: { score: number }) {
  const color = score >= 80 ? C.green : score >= 65 ? C.blue : score >= 50 ? C.amber : C.red
  const bg    = score >= 80 ? C.greenBg : score >= 65 ? C.blueBg : score >= 50 ? C.amberBg : C.redBg
  return (
    <div style={{
      width: 44, height: 44, borderRadius: "50%",
      background: bg, border: `2px solid ${color}`,
      display: "flex", flexDirection: "column" as const,
      alignItems: "center", justifyContent: "center", flexShrink: 0,
    }}>
      <div style={{ fontSize: 16, fontWeight: 900, color, lineHeight: 1 }}>{score || "—"}</div>
      <div style={{ fontSize: 7, color: C.gray, lineHeight: 1 }}>LQI</div>
    </div>
  )
}

// ── Probability gauge ─────────────────────────────────────────────────────────
function ProbGauge({ p10, pFlat, pLoss }: { p10: number; pFlat: number; pLoss: number }) {
  return (
    <div>
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", marginBottom: 5 }}>
        <div style={{ flex: p10,    background: C.green }} />
        <div style={{ flex: pFlat,  background: C.amber }} />
        <div style={{ flex: pLoss,  background: C.red   }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontSize: 9, color: C.green,  fontWeight: 700 }}>+10% {Math.round(p10)}%</span>
        <span style={{ fontSize: 9, color: C.amber,  fontWeight: 700 }}>Flat {Math.round(pFlat)}%</span>
        <span style={{ fontSize: 9, color: C.red,    fontWeight: 700 }}>Loss {Math.round(pLoss)}%</span>
      </div>
    </div>
  )
}

// ── Similar IPOs ──────────────────────────────────────────────────────────────
function SimilarIpos({ similar }: { similar: any[] }) {
  if (!similar?.length) return null
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: C.gray, textTransform: "uppercase" as const, letterSpacing: ".06em", marginBottom: 6 }}>
        Similar IPOs
      </div>
      <div style={{ display: "flex", flexWrap: "wrap" as const, gap: 4 }}>
        {similar.slice(0, 5).map((s: any, i: number) => {
          const ret = n(s.listing_gain ?? s.return_d30 ?? s.actual_return ?? 0)
          return (
            <div key={i} style={{
              background: C.grayBg, border: `1px solid ${C.border}`,
              borderRadius: 8, padding: "5px 8px", fontSize: 11,
            }}>
              <span style={{ fontWeight: 700, color: C.text }}>{s.company_name || s.name}</span>
              <span style={{ color: ret >= 0 ? C.green : C.red, fontWeight: 600, marginLeft: 4 }}>
                {ret >= 0 ? "+" : ""}{ret.toFixed(0)}%
              </span>
              {s.similarity_pct && (
                <span style={{ color: C.gray, fontSize: 9, marginLeft: 4 }}>({s.similarity_pct}% match)</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Subscription heatmap ──────────────────────────────────────────────────────
function SubHeatmap({ qib, nii, retail, total }: { qib: number | null; nii: number | null; retail: number | null; total: number | null }) {
  if (!qib && !nii && !retail && !total) return null
  const max = Math.max(n(qib), n(nii), n(retail), 1)
  const bars = [
    { label: "QIB",    val: n(qib),    color: C.blue   },
    { label: "NII",    val: n(nii),    color: C.purple  },
    { label: "Retail", val: n(retail), color: C.green   },
  ]
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <div style={{ fontSize: 9, color: C.gray, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: ".05em" }}>Subscription</div>
        {total && <div style={{ fontSize: 12, fontWeight: 800, color: C.text }}>{n(total).toFixed(1)}x total</div>}
      </div>
      {bars.filter(b => b.val > 0).map(b => (
        <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
          <div style={{ fontSize: 9, color: C.gray, width: 32, flexShrink: 0 }}>{b.label}</div>
          <div style={{ flex: 1 }}><Bar val={b.val} max={max} color={b.color} /></div>
          <div style={{ fontSize: 10, fontWeight: 700, color: b.color, minWidth: 36, textAlign: "right" as const }}>{b.val.toFixed(0)}x</div>
        </div>
      ))}
    </div>
  )
}

// ── Listing day panel ─────────────────────────────────────────────────────────
function ListingDayPanel({ ipo }: { ipo: any }) {
  const gmpPct = n(ipo.gmp_pct ?? ipo.gmpPercent ?? 0)
  const lqi    = n(ipo.lqi ?? ipo.score?.listingScore ?? 0)
  const issue  = n(ipo.issue_price ?? ipo.priceBandHigh ?? 0)
  const gmpAbs = issue > 0 ? issue * gmpPct / 100 : n(ipo.gmpPrice ?? 0)

  const signal930 = gmpPct >= 20 && lqi >= 70 ? "HOLD — Strong momentum expected" :
                    gmpPct >= 10              ? "HOLD — Watch OI buy%" :
                    gmpPct >= 0               ? "WATCH — Exit if OI buy% < 50%" :
                                               "EXIT — Negative GMP, exit immediately"
  const signal1015 = gmpPct >= 15 && lqi >= 70 ? "HOLD — Momentum likely continues" :
                     gmpPct >= 5               ? "PARTIAL TRAIL — Book 50%, trail rest" :
                                                "EXIT — Take whatever is available"
  const signal1025 = lqi >= 80 ? "TRAIL STOP — 5% below VWAP" :
                     lqi >= 65 ? "PARTIAL EXIT — Book 50% if up >15%" :
                                 "EXIT — Full exit unless exceptional"

  return (
    <div style={{ background: "#0F172A", borderRadius: 10, padding: 12, marginTop: 10 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" as const, letterSpacing: ".08em", marginBottom: 10 }}>
        ⚡ Listing Day Execution Panel
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 10 }}>
        {issue > 0 && <div>
          <div style={{ fontSize: 9, color: "#64748B" }}>Issue price</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: "#F1F5F9" }}>₹{issue}</div>
        </div>}
        {gmpAbs > 0 && <div>
          <div style={{ fontSize: 9, color: "#64748B" }}>GMP (indicative)</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: "#34D399" }}>+₹{gmpAbs.toFixed(0)} (+{gmpPct.toFixed(0)}%)</div>
        </div>}
        <div>
          <div style={{ fontSize: 9, color: "#64748B" }}>LQI signal</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: lqi >= 70 ? "#34D399" : lqi >= 50 ? "#FBBF24" : "#F87171" }}>{lqi}/100</div>
        </div>
      </div>
      {[
        { time: "9:30 AM", label: "Call auction opens", signal: signal930, icon: "🔔" },
        { time: "10:15 AM", label: "Listing price locks", signal: signal1015, icon: "🔒" },
        { time: "10:25 AM", label: "Execution decision", signal: signal1025, icon: "⚡" },
      ].map(row => (
        <div key={row.time} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8 }}>
          <div style={{ fontSize: 9, color: "#64748B", fontFamily: "monospace", minWidth: 52, paddingTop: 1 }}>{row.time}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 9, color: "#64748B" }}>{row.label}</div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#F1F5F9", lineHeight: 1.4 }}>{row.icon} {row.signal}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Score breakdown ───────────────────────────────────────────────────────────
function ScoreBreakdown({ ipo }: { ipo: any }) {
  const lqi    = n(ipo.lqi ?? ipo.score?.listingScore ?? 0)
  const biz    = n(ipo.score?.businessScore ?? 0)
  const anchor = n(ipo.score?.anchorScore ?? 0)
  const rows = [
    { label: "LQI / Listing potential", val: lqi,    color: lqi >= 70 ? C.green : lqi >= 50 ? C.amber : C.red },
    biz    > 0 ? { label: "Business quality",        val: biz,    color: C.blue   } : null,
    anchor > 0 ? { label: "Anchor quality",           val: anchor, color: C.purple } : null,
  ].filter(Boolean) as Array<{ label: string; val: number; color: string }>

  return (
    <div>
      {rows.map(r => (
        <div key={r.label} style={{ marginBottom: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
            <span style={{ fontSize: 11, color: C.textSub }}>{r.label}</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: r.color }}>{Math.round(r.val)}</span>
          </div>
          <Bar val={r.val} color={r.color} />
        </div>
      ))}
    </div>
  )
}

// ── Main IPO card ─────────────────────────────────────────────────────────────
function IpoCard({ ipo, simple, expanded, onToggle }: {
  ipo: any; simple: boolean; expanded: boolean; onToggle: () => void
}) {
  // Normalize fields — works for both /api/ipo and /api/ipo/intelligence
  const lqi      = n(ipo.lqi ?? ipo.score?.listingScore ?? 0)
  const gmpPct   = ipo.gmp_pct ?? (ipo.gmpPrice && ipo.priceBandHigh ? (n(ipo.gmpPrice) / n(ipo.priceBandHigh) * 100) : null)
  const gmpAbs   = ipo.gmpPrice ?? 0
  const rec      = ipo.score?.recommendation || ipo.action || ""
  const cfg      = getRecCfg(rec, lqi, gmpPct)
  const issue    = n(ipo.issue_price ?? ipo.priceBandHigh ?? 0)
  const issueSize = n(ipo.issue_size ?? ipo.issueSize ?? ipo.issue_size_cr ?? 0)
  const name     = ipo.company_name ?? ipo.name ?? "—"
  const sector   = ipo.sector ?? "—"
  const p10      = n(ipo.p_above_10 ?? ipo.score?.p10 ?? 0)
  const pLoss    = n(ipo.p_loss ?? ipo.score?.pLoss ?? 0)
  const pFlat    = Math.max(0, 100 - p10 - pLoss)
  const expRet   = n(ipo.exp_return ?? ipo.expected_return ?? gmpPct ?? 0)
  const similar  = ipo.similar_ipos ?? []
  const anchor   = ipo.anchor ?? ipo.anchor_quality ?? ""
  const confidence = ipo.confidence ?? ipo.score?.confidence ?? ""

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${cfg.bd}`,
      borderLeft: `4px solid ${cfg.color}`,
      borderRadius: 14, marginBottom: 10, overflow: "hidden",
      boxShadow: "0 1px 4px rgba(0,0,0,.04)",
      transition: "box-shadow .2s",
    }}>
      {/* ── Card header ── */}
      <div onClick={onToggle} style={{ padding: "14px 16px", cursor: "pointer" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <ScoreRing score={lqi} />
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Action badge */}
            <div style={{ marginBottom: 5 }}>
              <Badge label={`${cfg.icon} ${cfg.label}`} color={cfg.color} bg={cfg.bg} bd={cfg.bd} />
            </div>
            {/* Name + sector */}
            <div style={{ fontSize: 17, fontWeight: 800, color: C.text, marginBottom: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>
              {name}
            </div>
            <div style={{ fontSize: 11, color: C.textSub }}>
              {sector}{issue > 0 ? ` · ₹${issue}` : ""}{issueSize > 0 ? ` · ₹${issueSize.toFixed(0)}Cr` : ""}
              {ipo.lotSize ? ` · Lot ${ipo.lotSize}` : ""}
            </div>
          </div>
          {expanded ? <ChevronUp size={14} color={C.gray} /> : <ChevronDown size={14} color={C.gray} />}
        </div>

        {/* Key metrics row */}
        <div style={{ display: "flex", gap: 12, marginTop: 10, flexWrap: "wrap" as const }}>
          {gmpPct != null && (
            <StatBox label="GMP" val={`${n(gmpPct) >= 0 ? "+" : ""}${n(gmpPct).toFixed(0)}%`}
              color={n(gmpPct) >= 0 ? C.green : C.red}
              sub={gmpAbs > 0 ? `₹${n(gmpAbs).toFixed(0)}` : undefined} />
          )}
          {p10 > 0 && <StatBox label="P(>10%)" val={`${Math.round(p10)}%`} color={p10 >= 70 ? C.green : p10 >= 50 ? C.amber : C.red} />}
          {expRet !== 0 && <StatBox label="Exp. return" val={pct(expRet)} color={expRet >= 0 ? C.green : C.red} />}
          {ipo.total_x && <StatBox label="Sub total" val={`${n(ipo.total_x).toFixed(1)}x`} color={C.text} />}
          {confidence && <StatBox label="Confidence" val={confidence} color={C.text} />}
        </div>

        {/* Open/close dates */}
        {(ipo.openDate || ipo.open_date || ipo.closeDate || ipo.close_date) && (
          <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
            {(ipo.openDate || ipo.open_date) && (
              <span style={{ fontSize: 10, color: C.gray }}>
                <span style={{ fontWeight: 600, color: C.text }}>Opens:</span> {ipo.openDate || ipo.open_date}
              </span>
            )}
            {(ipo.closeDate || ipo.close_date) && (
              <span style={{ fontSize: 10, color: C.gray }}>
                <span style={{ fontWeight: 600, color: C.text }}>Closes:</span> {ipo.closeDate || ipo.close_date}
              </span>
            )}
            {(ipo.listingDate || ipo.listing_date) && (
              <span style={{ fontSize: 10, color: C.gray }}>
                <span style={{ fontWeight: 600, color: C.text }}>Lists:</span> {ipo.listingDate || ipo.listing_date}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Expanded content ── */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}`, background: C.bg, padding: "14px 16px" }}>

          {/* Probability gauge */}
          {p10 > 0 && (
            <>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.gray, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 6 }}>
                Listing probability
              </div>
              <ProbGauge p10={p10} pFlat={pFlat} pLoss={pLoss} />
              <Divider />
            </>
          )}

          {/* Score breakdown */}
          {!simple && lqi > 0 && (
            <>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.gray, textTransform: "uppercase" as const, letterSpacing: ".05em", marginBottom: 8 }}>Score breakdown</div>
              <ScoreBreakdown ipo={ipo} />
              <Divider />
            </>
          )}

          {/* Subscription heatmap */}
          {(ipo.qib_x || ipo.nii_x || ipo.retail_x) && (
            <>
              <SubHeatmap qib={ipo.qib_x} nii={ipo.nii_x} retail={ipo.retail_x} total={ipo.total_x} />
              <Divider />
            </>
          )}

          {/* Deal metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
            {ipo.ofs_pct != null && (
              <StatBox label="OFS %" val={`${n(ipo.ofs_pct).toFixed(0)}%`}
                color={n(ipo.ofs_pct) < 30 ? C.green : n(ipo.ofs_pct) < 60 ? C.amber : C.red} />
            )}
            {anchor && <StatBox label="Anchor quality" val={anchor} color={anchor.includes("STRONG") || anchor.includes("Tier-1") ? C.green : C.amber} />}
            {ipo.ipo_pe && <StatBox label="IPO P/E" val={`${n(ipo.ipo_pe).toFixed(0)}x`} />}
          </div>

          {/* BRLM */}
          {ipo.brlm && (
            <div style={{ marginBottom: 10, fontSize: 11, color: C.textSub }}>
              <span style={{ fontWeight: 600, color: C.text }}>Lead manager: </span>{ipo.brlm}
            </div>
          )}

          {/* Broker note for /api/ipo data */}
          {ipo.brokerNote && (
            <>
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", marginBottom: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.gray, marginBottom: 3 }}>
                  {ipo.brokerReco ? `Broker: ${ipo.brokerReco}` : "Broker view"}
                </div>
                <div style={{ fontSize: 12, color: C.text, lineHeight: 1.5 }}>{ipo.brokerNote}</div>
              </div>
              <Divider />
            </>
          )}

          {/* Historical return (scored IPOs) */}
          {(ipo.return_d30 || ipo.return_d90) && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
                {ipo.return_d7  != null && <StatBox label="7d return"  val={pct(ipo.return_d7)}  color={n(ipo.return_d7)  >= 0 ? C.green : C.red} />}
                {ipo.return_d30 != null && <StatBox label="30d return" val={pct(ipo.return_d30)} color={n(ipo.return_d30) >= 0 ? C.green : C.red} />}
                {ipo.return_d90 != null && <StatBox label="90d return" val={pct(ipo.return_d90)} color={n(ipo.return_d90) >= 0 ? C.green : C.red} />}
              </div>
              <Divider />
            </>
          )}

          {/* Similar IPOs */}
          {similar.length > 0 && (
            <>
              <SimilarIpos similar={similar} />
              <Divider />
            </>
          )}

          {/* Listing day panel (only for open/upcoming IPOs) */}
          {!simple && (ipo.status === "OPEN" || ipo.status === "UPCOMING" || !ipo.listing_date || new Date(ipo.listing_date) > new Date()) && (
            <ListingDayPanel ipo={ipo} />
          )}

          {/* Action summary */}
          <div style={{ background: cfg.bg, border: `1px solid ${cfg.bd}`, borderRadius: 10, padding: "12px 14px", marginTop: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: cfg.color, marginBottom: 4 }}>
              {simple ? "What to do:" : "Recommended action"}
            </div>
            <div style={{ fontSize: 12, color: cfg.color, lineHeight: 1.5 }}>
              {cfg.label === "STRONG APPLY" && "Apply in all categories (QIB/NII/Retail). Listing momentum strongly expected."}
              {cfg.label === "APPLY"        && "Apply. Good listing probability with acceptable risk. Hold for 30 days minimum."}
              {cfg.label === "LISTING ONLY" && "Apply for listing gains only. Exit on listing day if GMP holds at open."}
              {cfg.label === "BUY AT OPEN"  && "Skip IPO. Buy on listing dip if fundamentals confirm."}
              {cfg.label === "WATCH"        && "Watch GMP trend. Apply only if subscription stays strong."}
              {cfg.label === "AVOID"        && "Skip this IPO. Risk/reward not favourable at current valuation."}
              {cfg.label === "SKIP"         && "Not enough data. Watchlist only."}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Market regime banner ──────────────────────────────────────────────────────
function RegimeBanner({ summary }: { summary: any }) {
  if (!summary) return null
  const avgLqi = n(summary.avg_lqi)
  const regime = avgLqi >= 75 ? "HOT" : avgLqi >= 60 ? "NORMAL" : "CAUTIOUS"
  const cfg = regime === "HOT"
    ? { color: C.green, bg: C.greenBg, bd: C.greenBd, icon: "🔥", advice: "Favorable primary market. Strong institutional demand." }
    : regime === "NORMAL"
    ? { color: C.blue, bg: C.blueBg, bd: C.blueBd, icon: "✅", advice: "Selective deployment. Apply only high-conviction names." }
    : { color: C.amber, bg: C.amberBg, bd: C.amberBd, icon: "⚠️", advice: "Cautious. Prefer small lots or watchlist." }

  return (
    <div style={{ background: cfg.bg, border: `1px solid ${cfg.bd}`, borderRadius: 12, padding: "10px 14px", marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" as const, gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>{cfg.icon}</span>
          <div>
            <div style={{ fontSize: 12, fontWeight: 800, color: cfg.color }}>IPO Market: {regime}</div>
            <div style={{ fontSize: 11, color: C.textSub }}>{cfg.advice}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          {summary.momentum > 0 && <div style={{ textAlign: "center" as const }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: C.green }}>{summary.momentum}</div>
            <div style={{ fontSize: 9, color: C.gray }}>APPLY</div>
          </div>}
          {summary.value > 0 && <div style={{ textAlign: "center" as const }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: C.blue }}>{summary.value}</div>
            <div style={{ fontSize: 9, color: C.gray }}>WATCH</div>
          </div>}
          {summary.avoid > 0 && <div style={{ textAlign: "center" as const }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: C.red }}>{summary.avoid}</div>
            <div style={{ fontSize: 9, color: C.gray }}>AVOID</div>
          </div>}
        </div>
      </div>
    </div>
  )
}

// ── Tab definitions ───────────────────────────────────────────────────────────
const TABS = [
  { id: "open",     label: "Open now",    icon: <Zap size={11} />          },
  { id: "upcoming", label: "Upcoming",    icon: <TrendingUp size={11} />    },
  { id: "watch",    label: "Watch list",  icon: <Eye size={11} />           },
  { id: "listing",  label: "Listing day", icon: <Activity size={11} />      },
  { id: "scored",   label: "All scored",  icon: <BarChart2 size={11} />     },
]

// ── Main component ────────────────────────────────────────────────────────────
export function IpoCommandCenter({ simple = false }: { simple?: boolean }) {
  const [loading,     setLoading]     = useState(true)
  const [ipos,        setIpos]        = useState<any[]>([])
  const [scored,      setScored]      = useState<any[]>([])
  const [summary,     setSummary]     = useState<any>(null)
  const [activeTab,   setActiveTab]   = useState("open")
  const [expanded,    setExpanded]    = useState<string | null>(null)
  const [lastUpdate,  setLastUpdate]  = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // Fetch live IPOs + intelligence scores in parallel
      const [liveRes, intelRes] = await Promise.allSettled([
        fetch("/api/ipo?limit=30").then(r => r.json()).catch(() => null),
        fetch("/api/ipo/intelligence?limit=50").then(r => r.json()).catch(() => null),
      ])

      const liveIpos  = liveRes.status  === "fulfilled" ? (liveRes.value?.ipos  ?? []) : []
      const intelIpos = intelRes.status === "fulfilled" ? (intelRes.value?.ipos ?? []) : []
      const intelSum  = intelRes.status === "fulfilled" ? intelRes.value?.summary : null

      // Merge: enrich live IPOs with intelligence scores where available
      const merged = liveIpos.map((live: any) => {
        const intel = intelIpos.find((i: any) =>
          i.company_name?.toLowerCase().includes(live.name?.toLowerCase()?.slice(0, 6)) ||
          live.name?.toLowerCase().includes(i.company_name?.toLowerCase()?.slice(0, 6))
        )
        return intel ? { ...live, ...intel, name: live.name, status: live.status } : live
      })

      setIpos(merged.length > 0 ? merged : liveIpos)
      setScored(intelIpos)
      setSummary(intelSum)
      setLastUpdate(new Date())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Filter by tab
  const filtered = (() => {
    if (activeTab === "scored") return scored
    return ipos.filter((ipo: any) => {
      const status = (ipo.status || "").toUpperCase()
      if (activeTab === "open")     return status === "OPEN"
      if (activeTab === "upcoming") return status === "UPCOMING" || status === "COMING_SOON"
      if (activeTab === "watch")    return status === "CLOSED" && !status.includes("LIST")
      if (activeTab === "listing")  return status === "LISTING" || status === "LISTED"
      return true
    })
  })()

  // Sort by conviction score
  const sorted = [...filtered].sort((a: any, b: any) =>
    n(b.lqi ?? b.score?.listingScore) - n(a.lqi ?? a.score?.listingScore)
  )

  const key = (ipo: any) => String(ipo.id ?? ipo.company_name ?? ipo.name ?? Math.random())

  return (
    <div style={{ background: C.bg, minHeight: "100vh", paddingBottom: 80 }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ padding: "16px 16px 0", marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                <Zap size={18} color={C.purple} />
                <div style={{ fontSize: 20, fontWeight: 800, color: C.text }}>
                  {simple ? "IPO decisions" : "IPO Alpha Terminal"}
                </div>
              </div>
              <div style={{ fontSize: 11, color: C.textSub }}>
                {lastUpdate
                  ? `Updated ${lastUpdate.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })} IST`
                  : "Loading…"}
              </div>
            </div>
            <button onClick={load} style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "7px 12px", borderRadius: 8,
              border: `1px solid ${C.border}`, background: C.surface,
              fontSize: 12, color: C.textSub, cursor: "pointer",
            }}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>

        {/* Regime banner */}
        {summary && !simple && (
          <div style={{ padding: "0 16px" }}>
            <RegimeBanner summary={summary} />
          </div>
        )}

        {/* Tabs */}
        <div style={{ borderBottom: `1px solid ${C.border}`, padding: "0 16px", display: "flex", gap: 0, marginBottom: 14, overflowX: "auto" as const }}>
          {TABS.filter(t => simple ? ["open","upcoming"].includes(t.id) : true).map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
              display: "flex", alignItems: "center", gap: 4, padding: "10px 12px",
              border: "none", fontSize: 12, whiteSpace: "nowrap" as const,
              fontWeight: activeTab === t.id ? 700 : 500,
              color: activeTab === t.id ? C.purple : C.textSub,
              background: "transparent", cursor: "pointer",
              borderBottom: activeTab === t.id ? `2px solid ${C.purple}` : "2px solid transparent",
            }}>
              {t.icon} {t.label}
              {t.id === "scored" && scored.length > 0 && (
                <span style={{ fontSize: 9, background: C.purpleBg, color: C.purple, padding: "1px 5px", borderRadius: 10, marginLeft: 2 }}>
                  {scored.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ padding: "0 16px" }}>
          {loading ? (
            [1, 2, 3].map(i => (
              <div key={i} style={{ background: C.surface, borderRadius: 14, height: 100, marginBottom: 10, border: `1px solid ${C.border}`, animation: "pulse 1.5s infinite" }} />
            ))
          ) : sorted.length === 0 ? (
            <div style={{ padding: "48px 0", textAlign: "center" as const, color: C.textSub }}>
              <Zap size={32} color={C.grayBd} style={{ margin: "0 auto 12px", display: "block" }} />
              <div style={{ fontSize: 14, fontWeight: 600 }}>No IPOs in this category right now</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>
                {activeTab === "open" && "No IPOs currently open for subscription"}
                {activeTab === "upcoming" && "No upcoming IPOs in the pipeline"}
                {activeTab === "watch" && "Watchlist is empty"}
                {activeTab === "scored" && "Run the IPO probability engine to populate scores"}
              </div>
            </div>
          ) : (
            sorted.map((ipo: any) => {
              const k = key(ipo)
              return (
                <IpoCard
                  key={k} ipo={ipo} simple={simple}
                  expanded={expanded === k}
                  onToggle={() => setExpanded(expanded === k ? null : k)}
                />
              )
            })
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "8px 16px", fontSize: 10, color: C.gray, textAlign: "center" as const }}>
          All data real-time or as per last available source. Not financial advice.
        </div>
      </div>
    </div>
  )
}
