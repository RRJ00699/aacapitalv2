"use client"
// Stock Research Workspace — full redesign
// Clean light theme, consistent with Today screen
// Key data above the fold: price, conviction, scores
// Technical / Fundamentals / Commentary tabs

import { useState, useEffect } from "react"
import { PriceChart } from "./price-chart"
import { OrderBookPanel } from "./order-book-panel"
import { ManagementCommentaryPanel } from "./management-commentary-panel"
import { HistoricalSimilarityPanel } from "@/components/intelligence/HistoricalSimilarityPanel"
import VerdictHeader from "@/components/features/VerdictHeader"
import Phase1WorkspacePanels from "@/components/workspace/Phase1WorkspacePanels"

// ── Design tokens (same as Today screen) ─────────────────────────────────────
const T = {
  bg:       "#F7F9FC",
  surface:  "#FFFFFF",
  border:   "#E5E7EB",
  border2:  "#F1F5F9",
  text:     "#0F172A",
  textSub:  "#64748B",
  textMeta: "#94A3B8",
  green:    "#16A34A", greenBg:  "#F0FDF4", greenBd: "#BBF7D0",
  blue:     "#2563EB", blueBg:   "#EFF6FF", blueBd:  "#BFDBFE",
  amber:    "#D97706", amberBg:  "#FFFBEB", amberBd: "#FDE68A",
  red:      "#DC2626", redBg:    "#FEF2F2", redBd:   "#FECACA",
  purple:   "#7C3AED", purpleBg: "#F5F3FF", purpleBd:"#E9D5FF",
  teal:     "#0D9488", tealBg:   "#F0FDFA",
}

const n = (v: unknown) => parseFloat(String(v ?? 0)) || 0
const fmt = (v: unknown, d = 1) => Number.isFinite(n(v)) && n(v) !== 0 ? n(v).toFixed(d) : "—"
const pct = (v: unknown) => n(v) !== 0 ? `${n(v) >= 0 ? "+" : ""}${n(v).toFixed(1)}%` : "—"
const inr = (v: unknown) => n(v) > 0 ? `₹${n(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"

// ── Score ring ────────────────────────────────────────────────────────────────
function Ring({ score, size = 44, color = T.blue }: { score: number; size?: number; color?: string }) {
  const r = size / 2 - 5
  const circ = 2 * Math.PI * r
  const fill = (score / 100) * circ
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={T.border} strokeWidth={4} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${fill} ${circ - fill}`} strokeLinecap="round" />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
        style={{ transform: "rotate(90deg)", transformOrigin: "center",
                 fontSize: size < 40 ? 9 : 11, fontWeight: 700, fill: color }}>
        {Math.round(score)}
      </text>
    </svg>
  )
}

// ── Key-value row ─────────────────────────────────────────────────────────────
function KV({ label, value, highlight, color }: { label: string; value: string; highlight?: boolean; color?: string }) {
  return (
    <div style={{ background: highlight ? T.greenBg : T.surface,
      border: `1px solid ${highlight ? T.greenBd : T.border2}`,
      borderRadius: 10, padding: "10px 14px" }}>
      <div style={{ fontSize: 10, color: T.textMeta, fontWeight: 600,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: color ?? T.text }}>{value}</div>
    </div>
  )
}

// ── Section card ─────────────────────────────────────────────────────────────
function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 16, padding: "14px 16px", marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: `1px solid ${T.border2}`, paddingBottom: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 800, color: T.textSub,
          textTransform: "uppercase", letterSpacing: "0.1em" }}>{title}</span>
        {action}
      </div>
      {children}
    </div>
  )
}

// ── Holding bar ───────────────────────────────────────────────────────────────
function HoldingBar({ label, pct: p, color }: { label: string; pct: number; color: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: T.textSub }}>{label}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color }}>{p > 0 ? `${p.toFixed(1)}%` : "—"}</span>
      </div>
      <div style={{ height: 5, background: T.border2, borderRadius: 3 }}>
        <div style={{ height: 5, width: `${Math.min(100, p)}%`, background: color, borderRadius: 3 }} />
      </div>
    </div>
  )
}

function MFOwnershipPanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let on = true
    setLoading(true)
    fetch(`/api/stock/mf-holders?sym=${encodeURIComponent(symbol)}`, { cache: "no-store" })
      .then(r => r.json()).then(d => { if (on) { setData(d); setLoading(false) } })
      .catch(() => { if (on) setLoading(false) })
    return () => { on = false }
  }, [symbol])

  const holders = data?.holders ?? []
  const fmtMon = (v: any) => { if (!v) return "—"; const d = new Date(v); return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" }) }

  return (
    <Section title={`Mutual Fund Ownership${holders.length ? ` · ${holders.length} fund${holders.length>1?"s":""}` : ""}`}>
      {loading ? (
        <div style={{ fontSize: 11, color: T.textMeta, padding: "8px 0" }}>Loading fund holdings…</div>
      ) : holders.length === 0 ? (
        <div style={{ fontSize: 11, color: T.textMeta, padding: "8px 0" }}>
          No tracked conviction fund holds this stock.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {data?.is_new_conviction && (
            <div style={{ fontSize: 10, fontWeight: 700, color: T.purple, marginBottom: 2 }}>
              💎 Fresh conviction buy — a fund initiated within ~3 months
            </div>
          )}
          {holders.map((h: any) => (
            <div key={h.fund} style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "6px 8px", background: h.new_conviction ? T.greenBg : T.surface,
              border: `1px solid ${h.new_conviction ? T.greenBd : T.border2}`, borderRadius: 8 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.text, whiteSpace: "nowrap",
                  overflow: "hidden", textOverflow: "ellipsis", maxWidth: 200 }}>
                  {h.new_conviction ? "💎 " : ""}{h.fund}
                </div>
                <div style={{ fontSize: 9, color: T.textMeta }}>
                  {h.new_conviction ? "initiated" : "since"} {fmtMon(h.since)} · latest {fmtMon(h.as_of)}
                </div>
              </div>
              <div style={{ fontSize: 13, fontWeight: 800, color: T.text, marginLeft: 8 }}>
                {h.weight_pct != null ? `${h.weight_pct.toFixed(1)}%` : "—"}
              </div>
            </div>
          ))}
          <div style={{ fontSize: 9, color: T.textMeta, marginTop: 2 }}>
            From tracked conviction funds (Nippon/Quant/Canara/PPFAS/SBI/HDFC small-mid-flexi). Weight = % of fund's portfolio. Research signal, not a buy call.
          </div>
        </div>
      )}
    </Section>
  )
}

// ── Overlay ───────────────────────────────────────────────────────────────────
function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 999, display: "flex", flexDirection: "column" }}>
      <div style={{ position: "absolute", inset: 0, background: "rgba(15,23,42,0.5)", backdropFilter: "blur(2px)" }}
        onClick={onClose} />
      <div style={{ position: "relative", background: T.bg, borderRadius: "20px 20px 0 0",
        overflowY: "auto", maxHeight: "94vh", marginTop: "auto",
        boxShadow: "0 -8px 40px rgba(0,0,0,0.15)" }}>
        {children}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export function StockResearchWorkspace({ symbol, onClose }:
  { symbol: string; onClose: () => void }) {

  const [detail, setDetail]   = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [wdna, setWdna]       = useState<any>(null)
  const [livePrice, setLivePrice] = useState<number | null>(null)
  const [activeTab,    setActiveTab]    = useState<string>("technical")
  const [inWatchlist,  setInWatchlist]  = useState(false)
  const [addingWatch,  setAddingWatch]  = useState(false)

  useEffect(() => {
    // Check if stock is in watchlist
    fetch("/api/watchlists").then(r => r.json()).then(d => {
      const list = d.stocks ?? []
      setInWatchlist(list.some((s: any) => s.symbol === symbol))
    }).catch(() => {})
  }, [symbol])

  async function toggleWatchlist() {
    setAddingWatch(true)
    try {
      if (inWatchlist) {
        await fetch("/api/watchlists", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol }),
        })
        setInWatchlist(false)
      } else {
        await fetch("/api/watchlists", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol }),
        })
        setInWatchlist(true)
      }
    } catch {}
    finally { setAddingWatch(false) }
  }

  useEffect(() => {
    if (!symbol) return
    setLoading(true); setError(null); setDetail(null)
    Promise.all([
      fetch(`/api/investment-command-center?symbol=${symbol}`, { cache: "no-store" }).then(r => r.json()),
      fetch(`/api/weekly-dna?symbol=${symbol}`).then(r => r.json()).catch(() => null),
      fetch(`/api/broker/quote?sym=${symbol}&exchange=NSE`, { cache: "no-store" }).then(r => r.json()).catch(() => null),
    ]).then(([d, w, q]) => {
      if (d?.ok) {
        if (q?.last_price && q.last_price > 0) d.current_price = q.last_price
        setDetail(d)
        if (q?.last_price) setLivePrice(q.last_price)
      } else {
        setError(d?.error ?? "Stock not found")
      }
      if (w?.ok) setWdna(w.data)
    }).catch(e => setError(e.message))
    .finally(() => setLoading(false))
  }, [symbol])

  // Path A live prices: poll the Kite REST quote every 3s during market hours and
  // update livePrice. price (= livePrice ?? current_price) and the targets derived
  // from it recompute automatically, so the workbook stays near-live without a socket.
  useEffect(() => {
    if (!symbol) return
    const isMarketHours = () => {
      const ist  = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }))
      const mins = ist.getHours() * 60 + ist.getMinutes()
      const day  = ist.getDay()
      return day >= 1 && day <= 5 && mins >= 555 && mins <= 935   // 09:15–15:35 IST
    }
    let stopped = false
    const poll = async () => {
      if (stopped || !isMarketHours()) return
      try {
        const q = await fetch(`/api/broker/quote?sym=${symbol}&exchange=NSE`, { cache: "no-store" }).then(r => r.json())
        if (q?.last_price && q.last_price > 0) setLivePrice(q.last_price)
      } catch {}
    }
    poll()
    const timer = setInterval(poll, 3000)
    return () => { stopped = true; clearInterval(timer) }
  }, [symbol])

  if (loading) return (
    <Overlay onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
        height: "60vh", flexDirection: "column", gap: 12, color: T.textMeta }}>
        <div style={{ fontSize: 36 }}>⚡</div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>Loading {symbol}…</div>
      </div>
    </Overlay>
  )

  if (error || !detail) return (
    <Overlay onClose={onClose}>
      <div style={{ padding: 24 }}>
        <div style={{ color: T.red, fontSize: 14 }}>{error || "Not found"}</div>
        <button onClick={onClose} style={{ marginTop: 12, padding: "8px 16px", borderRadius: 8,
          border: `1px solid ${T.border}`, background: T.surface, cursor: "pointer" }}>Close</button>
      </div>
    </Overlay>
  )

  const price   = livePrice ?? n(detail.current_price)
  const conv    = n(detail.scores?.convergence)
  const convColor = conv >= 75 ? T.purple : conv >= 60 ? T.blue : conv >= 45 ? T.amber : T.textSub
  const f       = detail.fundamentals ?? {}
  const isNR7   = detail.technical?.is_nr7 || wdna?.is_nr7
  const stage   = wdna?.stage_label ?? `Stage ${detail.technical?.stage ?? "—"}`

  // Targets are computed off the LIVE price so they always match their +12/+25/+50%
  // labels and stay above current price. A stored trade_plan only overrides this while
  // it is still live (all targets above price, stop below) — once price runs past it,
  // we fall back to fresh bands off the current price instead of showing stale numbers.
  const plan      = detail.trade_plan ?? {}
  const planValid = Array.isArray(plan.targets) && plan.targets.length >= 3
    && Number(plan.targets[0]) > price
    && (plan.stopLoss == null || Number(plan.stopLoss) < price)
  const sl  = (planValid ? plan.stopLoss   : price * 0.90).toFixed(0)
  const t1  = (planValid ? plan.targets[0] : price * 1.12).toFixed(0)
  const t2  = (planValid ? plan.targets[1] : price * 1.25).toFixed(0)
  const t3  = (planValid ? plan.targets[2] : price * 1.50).toFixed(0)

  return (
    <Overlay onClose={onClose}>
      <div style={{ padding: "0 0 24px" }}>

        {/* ── Hero header ── */}
        <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`,
          padding: "16px 20px 0", position: "sticky", top: 0, zIndex: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 22, fontWeight: 900, color: T.text, letterSpacing: "-0.5px" }}>{symbol}</span>
                <span style={{ background: `${convColor}15`, color: convColor, fontSize: 11,
                  fontWeight: 700, padding: "3px 10px", borderRadius: 20 }}>{detail.conviction?.rating}</span>
                {isNR7 && <span style={{ background: T.purpleBg, color: T.purple,
                  fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20 }}>NR7 🎯</span>}
                {livePrice && <span style={{ background: T.greenBg, color: T.green,
                  fontSize: 9, fontWeight: 600, padding: "2px 7px", borderRadius: 20 }}>● LIVE</span>}
              </div>
              <div style={{ fontSize: 12, color: T.textSub, marginTop: 2 }}>
                {detail.name} · {detail.industry}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 26, fontWeight: 900, color: T.text, letterSpacing: "-0.5px" }}>
                {inr(price)}
              </div>
              <div style={{ fontSize: 11, color: T.textMeta }}>
                MCap ₹{(n(f.market_cap) / 100).toFixed(0)}Cr
              </div>
            </div>
          </div>

          {/* Convergence bar */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 10, color: T.textMeta, fontWeight: 600 }}>CONVERGENCE SCORE</span>
              <span style={{ fontSize: 12, fontWeight: 800, color: convColor }}>{conv}/100</span>
            </div>
            <div style={{ height: 5, background: T.border2, borderRadius: 3 }}>
              <div style={{ height: 5, width: `${conv}%`, background: convColor, borderRadius: 3,
                transition: "width 0.5s ease" }} />
            </div>
          </div>

          {/* Tab nav */}
          <div style={{ display: "flex", gap: 0 }}>
            {[["technical","📈 Technical"],["fundamentals","🏢 Fundamentals"],["commentary","💬 Commentary"]].map(([id,label]) => (
              <button key={id} onClick={() => setActiveTab(id)} style={{
                padding: "9px 18px", border: "none", fontSize: 12, cursor: "pointer",
                fontWeight: activeTab === id ? 700 : 500,
                color: activeTab === id ? T.blue : T.textSub,
                background: "transparent",
                borderBottom: activeTab === id ? `2px solid ${T.blue}` : "2px solid transparent",
              }}>{label}</button>
            ))}
            <button onClick={toggleWatchlist} disabled={addingWatch}
              style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 5,
                background: inWatchlist ? T.amberBg : T.bg,
                border: `1px solid ${inWatchlist ? T.amber : T.border}`,
                borderRadius: 8, padding: "6px 12px", fontSize: 11,
                color: inWatchlist ? T.amber : T.textSub,
                cursor: "pointer", marginBottom: 2, fontWeight: inWatchlist ? 700 : 400 }}>
              {inWatchlist ? "★ Watching" : "☆ Watch"}
            </button>
            <button onClick={onClose} style={{ background: T.bg,
              border: `1px solid ${T.border}`, borderRadius: 8, padding: "6px 14px",
              fontSize: 12, cursor: "pointer", color: T.textSub, marginBottom: 2 }}>✕ Close</button>
          </div>
        </div>

        <div style={{ padding: "16px 20px 0" }}>

          {/* ── Verdict header: decomposed conviction scorecard (glance layer above tabs) ── */}
          <VerdictHeader symbol={symbol} />

          {/* ── TECHNICAL TAB ── */}
          <div style={{ display: activeTab === "technical" ? "block" : "none" }}>

            {/* 6-engine scores */}
            <Section title="6-Engine Convergence">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14, marginBottom: 12 }}>
                {[
                  { label: "Technical DNA",  score: n(detail.scores?.technical_dna), color: T.blue   },
                  { label: "Business DNA",   score: n(detail.scores?.business_dna),  color: T.purple  },
                  { label: "Earnings Intel", score: n(detail.scores?.earnings),      color: T.green   },
                  { label: "Smart Money",    score: n(detail.scores?.smart_money),   color: T.amber   },
                  { label: "Sector Score",   score: 50,                              color: T.textSub },
                  { label: "CONVERGENCE",    score: conv,                             color: convColor },
                ].map(({ label, score, color }) => (
                  <div key={label} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
                    <Ring score={score} color={color} size={52} />
                    <div style={{ fontSize: 9, color: T.textMeta, textAlign: "center", fontWeight: 600 }}>{label}</div>
                  </div>
                ))}
              </div>
            </Section>

            {/* Price chart */}
            <Section title="Price Chart">
              <PriceChart symbol={symbol} height={200} />
            </Section>

            {/* Entry/Exit */}
            <Section title="Entry · Exit · Targets">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div style={{ background: T.redBg, border: `1px solid ${T.redBd}`, borderRadius: 12, padding: 12 }}>
                  <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 4 }}>STOP LOSS</div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: T.red }}>₹{sl}</div>
                  <div style={{ fontSize: 10, color: T.textSub, marginTop: 2 }}>Close below = exit</div>
                </div>
                <div style={{ background: T.greenBg, border: `1px solid ${T.greenBd}`, borderRadius: 12, padding: 12 }}>
                  <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 4 }}>TARGET 1 · +12%</div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: T.green }}>₹{t1}</div>
                  <div style={{ fontSize: 10, color: T.textSub, marginTop: 2 }}>Book partial profit</div>
                </div>
                <div style={{ background: T.blueBg, border: `1px solid ${T.blueBd}`, borderRadius: 12, padding: 12 }}>
                  <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 4 }}>TARGET 2 · +25%</div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: T.blue }}>₹{t2}</div>
                  <div style={{ fontSize: 10, color: T.textSub, marginTop: 2 }}>Trail stop loss up</div>
                </div>
                <div style={{ background: T.purpleBg, border: `1px solid ${T.purpleBd}`, borderRadius: 12, padding: 12 }}>
                  <div style={{ fontSize: 9, color: T.textMeta, fontWeight: 600, marginBottom: 4 }}>TARGET 3 · +50%</div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: T.purple }}>₹{t3}</div>
                  <div style={{ fontSize: 10, color: T.textSub, marginTop: 2 }}>Let winner run</div>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
                <KV label="Position Size" value={detail.conviction?.position_size ?? "1–3%"} />
                <KV label="Hold Period"   value="6–18 months" />
              </div>
            </Section>

            {/* Technical structure */}
            <Section title="Technical Structure">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
                <KV label="Stage"        value={String(stage)} />
                <KV label="Base Length"  value={`${n(detail.technical?.base_months) || 0}M`} />
                <KV label="Momentum 6M"  value={pct(detail.technical?.momentum_6m)}
                  color={n(detail.technical?.momentum_6m) >= 0 ? T.green : T.red} />
                <KV label="Vol Compress" value={`${fmt(detail.technical?.vol_compression, 2)}x`} />
                <KV label="Below 52W Hi" value={`${fmt(detail.technical?.pct_below_high)}%`} />
                <KV label="NR7 Signal"   value={isNR7 ? "✓ Coiling" : "—"}
                  highlight={isNR7} color={isNR7 ? T.green : T.textSub} />
              </div>
            </Section>

            {/* Expected returns */}
            <Section title="Expected Returns">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                <div style={{ background: `${T.green}10`, border: `1px solid ${T.green}30`,
                  borderRadius: 10, padding: 12, textAlign: "center" as const }}>
                  <div style={{ fontSize: 22, fontWeight: 800, color: T.green }}>
                    {conv >= 70 ? "70%" : conv >= 55 ? "55%" : "40%"}
                  </div>
                  <div style={{ fontSize: 9, color: T.textMeta, marginTop: 4 }}>P(+20% in 6M)</div>
                </div>
                <div style={{ background: `${T.blue}10`, border: `1px solid ${T.blue}30`,
                  borderRadius: 10, padding: 12, textAlign: "center" as const }}>
                  <div style={{ fontSize: 22, fontWeight: 800, color: T.blue }}>
                    {conv >= 70 ? "53%" : conv >= 55 ? "40%" : "28%"}
                  </div>
                  <div style={{ fontSize: 9, color: T.textMeta, marginTop: 4 }}>P(+50% in 12M)</div>
                </div>
                <div style={{ background: `${T.purple}10`, border: `1px solid ${T.purple}30`,
                  borderRadius: 10, padding: 12, textAlign: "center" as const }}>
                  <div style={{ fontSize: 22, fontWeight: 800, color: T.purple }}>
                    {conv >= 70 ? "40%" : conv >= 55 ? "28%" : "15%"}
                  </div>
                  <div style={{ fontSize: 9, color: T.textMeta, marginTop: 4 }}>P(+100% in 24M)</div>
                </div>
              </div>
            </Section>

            <Section title="Historical Similarity">
              <HistoricalSimilarityPanel symbol={symbol} />
            </Section>
          </div>

          {/* ── FUNDAMENTALS TAB ── */}
          <div style={{ display: activeTab === "fundamentals" ? "block" : "none" }}>

            {/* Shareholding */}
            <Section title="Shareholding Pattern">
              <HoldingBar label="Promoter" pct={n(f.promoter_holding)} color={T.blue} />
              {n(f.promoter_pledge) > 0 && (
                <HoldingBar label="Promoter Pledge ⚠️" pct={n(f.promoter_pledge)} color={T.red} />
              )}
              <HoldingBar label="FII / Foreign" pct={n(f.fii_holding)} color={T.green} />
              <HoldingBar label="DII / Domestic Inst" pct={n(f.dii_holding)} color={T.purple} />
              <HoldingBar label="Public / Retail"
                pct={Math.max(0, 100 - n(f.promoter_holding) - n(f.fii_holding) - n(f.dii_holding))}
                color={T.amber} />
            </Section>

            {/* Valuation */}
            <Section title="Valuation">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
                <KV label="P/E Ratio"   value={n(f.pe_ratio) > 0 ? `${fmt(f.pe_ratio)}x` : "—"} />
                <KV label="P/B Ratio"   value={n(f.pb_ratio) > 0 ? `${fmt(f.pb_ratio)}x` : "—"} />
                <KV label="Div Yield"   value={n(f.dividend_yield) > 0 ? `${fmt(f.dividend_yield)}%` : "—"} />
              </div>
            </Section>

            {/* Business DNA */}
            <Section title={`Business DNA [${detail.scores?.business_grade ?? "—"}]`}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
                <KV label="ROCE"         value={n(f.roce) > 0 ? `${fmt(f.roce)}%` : "—"}
                  highlight={n(f.roce) >= 15} color={n(f.roce) >= 15 ? T.green : T.text} />
                <KV label="ROE"          value={n(f.roe) > 0 ? `${fmt(f.roe)}%` : "—"}
                  highlight={n(f.roe) >= 15} />
                <KV label="Op Margin"    value={n(f.operating_margin) > 0 ? `${fmt(f.operating_margin)}%` : "—"} />
                <KV label="Rev CAGR 3Y"  value={n(f.sales_cagr_3y) !== 0 ? pct(f.sales_cagr_3y) : "—"}
                  color={n(f.sales_cagr_3y) >= 0 ? T.green : T.red} />
                <KV label="EPS CAGR 3Y"  value={n(f.eps_cagr_3y) !== 0 ? pct(f.eps_cagr_3y) : "—"}
                  color={n(f.eps_cagr_3y) >= 0 ? T.green : T.red} />
                <KV label="PAT Growth"   value={n(f.pat_growth) !== 0 ? pct(f.pat_growth) : "—"}
                  color={n(f.pat_growth) >= 0 ? T.green : T.red} />
                <KV label="D/E Ratio"    value={n(f.debt_equity) >= 0 ? fmt(f.debt_equity) : "—"}
                  highlight={n(f.debt_equity) < 0.5} color={n(f.debt_equity) < 0.5 ? T.green : n(f.debt_equity) > 1 ? T.red : T.amber} />
                <KV label="Int. Cover"   value={n(f.interest_cover) > 0 ? `${fmt(f.interest_cover)}x` : "—"} />
                <KV label="MCap"         value={n(f.market_cap) > 0 ? `₹${(n(f.market_cap)/100).toFixed(0)}Cr` : "—"} />
              </div>
            </Section>

            {/* Smart Money */}
            <Section title="Smart Money">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                <KV label="Signal" value={detail.scores?.smart_money_signal ?? "—"} />
                <KV label="Score"  value={`${n(detail.scores?.smart_money)}/100`} />
              </div>
            </Section>

            {/* Mutual Fund Ownership — which conviction funds hold / just initiated */}
            <MFOwnershipPanel symbol={symbol} />

            {/* Order Book + MF + Ownership */}
            <Section title="Order Book">
              <OrderBookPanel symbol={symbol} />
            </Section>

            <Phase1WorkspacePanels symbol={symbol} />
          </div>

          {/* ── COMMENTARY TAB ── */}
          <div style={{ display: activeTab === "commentary" ? "block" : "none" }}>
            <ManagementCommentaryPanel symbol={symbol} />
          </div>

        </div>
      </div>
    </Overlay>
  )
}
