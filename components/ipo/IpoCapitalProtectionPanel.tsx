"use client"
// components/ipo/IpoCapitalProtectionPanel.tsx
// POST-LISTING CAPITAL PROTECTION — the panel for an IPO you already hold.
//
// Built on a backtest of 84 ₹200cr+ IPOs that listed soft (open ≤ +2%) and were
// underwater at day 7:  only 12% recovered to +15% within 30 days, 67% were still
// negative at BOTH day 30 and day 90, average best-case peak just +3.4% against an
// average −21.5% dip. Conclusion: a soft-listing dip is a CAPITAL-PROTECTION signal
// (hold/reduce, protect the floor), NOT a buy-the-dip opportunity. This panel says so.
//
// Drop-in: matches IpoCommandCenter's light theme + inline-style C tokens.
// Prop-driven; pass live values from ipo_live_feed / ipo_intelligence.

import { Shield, AlertTriangle, TrendingDown, TrendingUp, Lock, Clock, Wallet } from "lucide-react"

const C = {
  green:  "#15803D", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  amber:  "#B45309", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:    "#B91C1C", redBg:    "#FEF2F2", redBd:   "#FECACA",
  gray:   "#6B7280", grayBg:   "#F9FAFB", grayBd:  "#E5E7EB",
  text:   "#111827", textSub:  "#6B7280", surface: "#FFFFFF", border: "#E5E7EB",
}

// Historical base rates from backtest_dip_defense.py (84 soft-listing ₹200cr+ IPOs).
const BACKTEST = { n: 84, failPct: 67, recoverPct: 12, avgDip: -21.5, avgPeak: 3.4 }

const n = (v: unknown) => (Number.isFinite(parseFloat(String(v))) ? parseFloat(String(v)) : 0)
const inr = (v: number) => "₹" + v.toLocaleString("en-IN", { maximumFractionDigits: 2 })

type RecoverySignal = { tier: string; tone: string; label: string; detail: string }
type Props = {
  company?: string
  issuePrice?: number
  currentPrice?: number          // live; from ipo_live_feed
  openPrice?: number             // listing-day open
  listingDate?: string           // ISO; for anchor-unlock calendar
  positionValue?: number         // your allotment value at current price (optional)
  reserveCapital?: number        // un-deployed reserve you were tempted to "buy the dip" with
  signal?: RecoverySignal        // recovery-engine signal from the post-listing route
}

function daysBetween(a: Date, b: Date) {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000)
}

export default function IpoCapitalProtectionPanel({
  company = "Turtlemint Fintech Solutions",
  issuePrice = 152,
  currentPrice = 143.5,
  openPrice = 150,
  listingDate = "2026-06-29",
  positionValue = 64000,
  reserveCapital = 36000,
  signal = { tier: "WATCH", tone: "amber", label: "Discount + strong QIB — awaiting reclaim",
    detail: "Edge is thin & high-variance (+4% avg to d30, PF 1.72, n=70). Wait for the reclaim." },
}: Props) {
  const issue = n(issuePrice)
  const cur = n(currentPrice)
  const open = n(openPrice)

  const distPct = issue ? (cur / issue - 1) * 100 : 0      // current vs issue
  const openPct = issue ? (open / issue - 1) * 100 : 0     // open vs issue
  const softOpen = openPct <= 2
  const underwater = cur < issue
  const riskFired = softOpen && underwater                  // the backtested danger cohort

  // ── Capital-protection band ──
  const band =
    cur >= issue ? "SAFE" : distPct >= -8 ? "WARNING" : "CRITICAL"
  const bandCfg = {
    SAFE:     { color: C.green, bg: C.greenBg, bd: C.greenBd, label: "Above issue floor", icon: <Shield size={15} /> },
    WARNING:  { color: C.amber, bg: C.amberBg, bd: C.amberBd, label: "Below issue — floor weakening", icon: <AlertTriangle size={15} /> },
    CRITICAL: { color: C.red,   bg: C.redBg,   bd: C.redBd,   label: "Issue price broken", icon: <TrendingDown size={15} /> },
  }[band]

  // ── Single recommendation (never "buy the dip" for this cohort) ──
  let rec: { action: string; color: string; bg: string; bd: string; why: string }
  if (cur >= issue * 1.05) {
    rec = { action: "HOLD", color: C.green, bg: C.greenBg, bd: C.greenBd,
      why: "Holding above issue with a cushion. Capital protected — let it run, trail your stop." }
  } else if (cur >= issue) {
    rec = { action: "HOLD · WATCH", color: C.amber, bg: C.amberBg, bd: C.amberBd,
      why: "Barely above issue. Defend the floor — if it loses issue price on volume, reduce." }
  } else if (band === "CRITICAL") {
    rec = { action: "REDUCE / EXIT", color: C.red, bg: C.redBg, bd: C.redBd,
      why: "Soft listing, broke well below issue. Historically these keep falling — protect capital, don't average down." }
  } else {
    rec = { action: "REDUCE", color: C.amber, bg: C.amberBg, bd: C.amberBd,
      why: "Soft open and underwater — the 67%-failure setup. Trim into any bounce; this is not a dip to add to." }
  }

  // ── Anchor-unlock calendar (30d / 90d reversal-risk windows) ──
  let unlocks: { label: string; date: Date; days: number; near: boolean }[] = []
  let sinceListing: number | null = null
  const ld = listingDate ? new Date(listingDate) : null
  if (ld && !isNaN(ld.getTime())) {
    const today = new Date()
    sinceListing = daysBetween(ld, today)
    for (const [label, d] of [["50% anchor unlock", 30], ["Remaining anchor unlock", 90]] as const) {
      const date = new Date(ld); date.setDate(date.getDate() + d)
      const days = daysBetween(today, date)
      unlocks.push({ label, date, days, near: days >= -2 && days <= 5 })
    }
  }

  // floor-gauge geometry: map -30%..+30% around issue to 0..100%
  const clamp = (x: number) => Math.max(-30, Math.min(30, x))
  const curX = ((clamp(distPct) + 30) / 60) * 100
  const dipX = ((clamp(openPct) + 30) / 60) * 100

  const card: React.CSSProperties = {
    background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14, marginBottom: 10,
  }
  const lbl: React.CSSProperties = { fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: C.textSub, textTransform: "uppercase" }

  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", color: C.text, maxWidth: 520 }}>

      {/* Header */}
      <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700 }}>{company}</div>
          <div style={{ fontSize: 11, color: C.textSub, marginTop: 2 }}>
            Post-listing · capital protection {sinceListing !== null ? `· day ${Math.max(0, sinceListing)}` : ""}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: distPct >= 0 ? C.green : C.red }}>{inr(cur)}</div>
          <div style={{ fontSize: 11, color: distPct >= 0 ? C.green : C.red }}>
            {distPct >= 0 ? "+" : ""}{distPct.toFixed(1)}% vs issue {inr(issue)}
          </div>
        </div>
      </div>

      {/* Recommendation banner */}
      <div style={{ ...card, background: rec.bg, border: `1px solid ${rec.bd}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18, fontWeight: 800, color: rec.color }}>{rec.action}</span>
          <span style={{ fontSize: 10, color: rec.color, border: `1px solid ${rec.bd}`, borderRadius: 999, padding: "2px 7px" }}>
            signal · not a buy call
          </span>
        </div>
        <div style={{ fontSize: 12.5, color: C.text, marginTop: 6, lineHeight: 1.45 }}>{rec.why}</div>
      </div>

      {/* Recovery-engine signal (from the strategy backtest) */}
      {signal && (() => {
        const tone = {
          green: { color: C.green, bg: C.greenBg, bd: C.greenBd },
          amber: { color: C.amber, bg: C.amberBg, bd: C.amberBd },
          red:   { color: C.red,   bg: C.redBg,   bd: C.redBd },
          gray:  { color: C.gray,  bg: C.grayBg,  bd: C.grayBd },
        }[signal.tone] || { color: C.gray, bg: C.grayBg, bd: C.grayBd }
        return (
          <div style={{ ...card, background: tone.bg, border: `1px solid ${tone.bd}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: 0.5, color: "#fff",
                background: tone.color, borderRadius: 5, padding: "3px 7px" }}>
                {signal.tier}
              </span>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: tone.color }}>{signal.label}</span>
            </div>
            <div style={{ fontSize: 11.5, color: C.text, lineHeight: 1.5 }}>{signal.detail}</div>
            <div style={{ fontSize: 9.5, color: C.textSub, marginTop: 6 }}>
              Recovery edge concentrated in 2022–23; compressed in 2024–25. Treat as capital-protection context, not a live buy signal.
            </div>
          </div>
        )
      })()}

      {/* SIGNATURE: capital-protection floor gauge */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <span style={lbl}>Capital protection</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: bandCfg.color }}>
            {bandCfg.icon}{band} — {bandCfg.label}
          </span>
        </div>
        <div style={{ position: "relative", height: 46, marginTop: 18 }}>
          {/* zones */}
          <div style={{ position: "absolute", inset: 0, display: "flex", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ width: "50%", background: C.redBg }} />
            <div style={{ width: "50%", background: C.greenBg }} />
          </div>
          {/* issue-price floor line (center) */}
          <div style={{ position: "absolute", left: "50%", top: -6, bottom: -6, width: 2, background: C.text }} />
          <div style={{ position: "absolute", left: "50%", top: -18, transform: "translateX(-50%)", fontSize: 9, fontWeight: 700, color: C.text, whiteSpace: "nowrap" }}>
            ISSUE {inr(issue)}
          </div>
          {/* open marker */}
          <div title="listing open" style={{ position: "absolute", left: `${dipX}%`, top: 6, transform: "translateX(-50%)", width: 8, height: 8, borderRadius: 999, background: C.gray, border: "2px solid #fff" }} />
          {/* current price marker */}
          <div style={{ position: "absolute", left: `${curX}%`, top: -2, bottom: -2, transform: "translateX(-50%)", width: 3, background: bandCfg.color, borderRadius: 2 }} />
          <div style={{ position: "absolute", left: `${curX}%`, top: 50, transform: "translateX(-50%)", fontSize: 9, fontWeight: 700, color: bandCfg.color, whiteSpace: "nowrap" }}>
            now {inr(cur)}
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: C.textSub, marginTop: 24 }}>
          <span>−30%</span><span>capital at risk ◄ ISSUE ► protected</span><span>+30%</span>
        </div>
      </div>

      {/* Soft-listing risk flag */}
      <div style={{ ...card, background: riskFired ? C.redBg : C.greenBg, border: `1px solid ${riskFired ? C.redBd : C.greenBd}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          {riskFired ? <AlertTriangle size={14} color={C.red} /> : <Shield size={14} color={C.green} />}
          <span style={{ fontSize: 12, fontWeight: 700, color: riskFired ? C.red : C.green }}>
            {riskFired ? "Soft-listing risk — ACTIVE" : "Soft-listing risk — not triggered"}
          </span>
        </div>
        <div style={{ fontSize: 11.5, color: C.text, lineHeight: 1.5 }}>
          {riskFired ? (
            <>Flat/negative open <b>and</b> below issue price. Across {BACKTEST.n} comparable ₹200cr+ IPOs,{" "}
              <b>{BACKTEST.failPct}% were still underwater at day 30 and day 90</b>; only {BACKTEST.recoverPct}% recovered to +15%
              (avg best case +{BACKTEST.avgPeak}% against a −{Math.abs(BACKTEST.avgDip)}% dip). Institutions rarely defend these.</>
          ) : (
            <>Open held above issue, or price is above the floor. The historical soft-listing failure pattern isn’t in play.</>
          )}
        </div>
      </div>

      {/* Reserve-capital guidance — the inverted thesis */}
      {reserveCapital > 0 && (
        <div style={{ ...card, display: "flex", gap: 10, alignItems: "flex-start" }}>
          <Wallet size={15} color={C.textSub} style={{ marginTop: 1 }} />
          <div style={{ fontSize: 11.5, lineHeight: 1.5 }}>
            <div style={{ fontWeight: 700, marginBottom: 2 }}>Reserve {inr(reserveCapital)} — keep in cash{riskFired ? "" : " for now"}</div>
            {riskFired
              ? <>Deploying it into this dip is the move the backtest rejects: a {BACKTEST.failPct}% chance of adding to a falling position. Cash is the correct position here.</>
              : <>No soft-listing signal — but “buy the dip on a weak IPO” isn’t a validated edge. Deploy only on your normal conviction criteria, not on the dip itself.</>}
          </div>
        </div>
      )}

      {/* Anchor-unlock calendar */}
      {unlocks.length > 0 && (
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <Lock size={13} color={C.textSub} /><span style={lbl}>Anchor unlock — added selling risk</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {unlocks.map((u) => (
              <div key={u.label} style={{
                flex: 1, border: `1px solid ${u.near ? C.amberBd : C.grayBd}`,
                background: u.near ? C.amberBg : C.grayBg, borderRadius: 8, padding: "8px 10px",
              }}>
                <div style={{ fontSize: 10, color: C.textSub }}>{u.label}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: u.near ? C.amber : C.text }}>
                  {u.date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" })}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: u.near ? C.amber : C.textSub, marginTop: 2 }}>
                  <Clock size={9} />{u.days < 0 ? "passed" : u.days === 0 ? "today" : `in ${u.days}d`}
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10, color: C.textSub, marginTop: 7 }}>
            When anchor lock-ins expire, supply increases — a soft name can get a fresh leg down. Treat these dates as caution windows, not buy windows.
          </div>
        </div>
      )}

      <div style={{ fontSize: 10, color: C.textSub, padding: "2px 4px 0", lineHeight: 1.5 }}>
        Research signal from listing-day structure and historical base rates (n={BACKTEST.n}). Not investment advice.
        Backtest covers ₹200cr+ mainboard IPOs; thin/operator-driven names can behave differently.
      </div>
    </div>
  )
}
