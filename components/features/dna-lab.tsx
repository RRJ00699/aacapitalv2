"use client"
// components/features/dna-lab.tsx
// Multibagger DNA Lab — Sprint 7
// Shows Top 20 DNA stocks, winner breakdown by year/tier, bull/bear regime analysis
// Data from: /api/dna-lab (multibagger_events + price_monthly in Neon)

import { useState, useEffect, useCallback } from "react"
import { colors } from "@/lib/design/tokens"

// ── Types ─────────────────────────────────────────────────────────────────────
interface Top20Row {
  tradingsymbol: string
  peak_tier: number
  peak_return: number
  total_entry_points: number
  avg_base_months: number
  avg_base_depth: number
  had_nr7: boolean
  avg_vol_compression: number
  avg_momentum: number
  latest_base_date: string
  typical_regime: string
  typical_class: string
  dna_score: number
}

interface RegimeRow {
  classification: string
  regime_at_base: string
  stocks: number
  entry_points: number
  avg_max_return: number
  avg_12m: number
  avg_24m: number
  avg_base_months: number
}

interface SectorRow {
  classification: string
  year: number
  stocks: number
  entry_points: number
  avg_max_return: number
  avg_12m_return: number
  avg_base_months: number
  avg_vol_compression: number
}

interface Summary {
  total_stocks: number
  total_events: number
  stocks_10x: number
  stocks_5x: number
  stocks_3x: number
  stocks_2x: number
  stocks_1x: number
  highest_ever_return: number
}

interface DnaStats {
  classification: string
  avg_base_months: number
  avg_base_depth_pct: number
  avg_vol_compression: number
  avg_momentum_6m: number
  pct_had_nr7: number
  n: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const TIER_LABEL: Record<number, string> = { 5: "10x", 4: "5x", 3: "3x", 2: "2x", 1: "1x" }
const TIER_COLOR: Record<string, string> = {
  "10x": "#7c3aed",
  "5x":  "#2563EB",
  "3x":  "#16A34A",
  "2x":  "#D97706",
  "1x":  "#6b7280",
}
const CLASS_ORDER = ["10x", "5x", "3x", "2x", "1x"]

function classColor(cls: string) { return TIER_COLOR[cls] ?? "#6b7280" }

function regimeBadge(regime: string) {
  return regime === "bull"
    ? { bg: "#dcfce7", color: "#16A34A", label: "BULL" }
    : regime === "bear"
    ? { bg: "#fef2f2", color: "#DC2626", label: "BEAR" }
    : { bg: "#f3f4f6", color: "#6b7280", label: "—" }
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round(score))
  let bg = "#16A34A"
  if (pct < 40) bg = "#6b7280"
  else if (pct < 60) bg = "#D97706"
  else if (pct < 80) bg = "#2563EB"
  else bg = "#7c3aed"
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "#F3F4F6", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: bg, borderRadius: 3,
          transition: "width 0.6s ease" }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color: bg, minWidth: 28 }}>{pct}</span>
    </div>
  )
}

function StatPill({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
      background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: 10,
      padding: "8px 14px", minWidth: 64 }}>
      <span style={{ fontSize: 15, fontWeight: 700, color: color ?? colors.textPrimary }}>{value}</span>
      <span style={{ fontSize: 10, color: "#6b7280", marginTop: 1, whiteSpace: "nowrap" }}>{label}</span>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────
export function DNALabScreen() {
  const [activeTab, setActiveTab] = useState<"top20" | "regime" | "timeline" | "dna">("top20")
  const [top20, setTop20]         = useState<Top20Row[]>([])
  const [regime, setRegime]       = useState<RegimeRow[]>([])
  const [summary, setSummary]     = useState<Summary | null>(null)
  const [sectors, setSectors]     = useState<SectorRow[]>([])
  const [dnaStats, setDnaStats]   = useState<DnaStats[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        fetch("/api/dna-lab?view=top20").then(r => r.json()),
        fetch("/api/dna-lab?view=regime").then(r => r.json()),
        fetch("/api/dna-lab?view=sectors").then(r => r.json()),
        fetch("/api/dna-lab?view=dna_stats").then(r => r.json()),
      ])
      if (r1.ok) setTop20(r1.data)
      if (r2.ok) { setRegime(r2.data); setSummary(r2.summary) }
      if (r3.ok) setSectors(r3.data)
      if (r4.ok) setDnaStats(r4.data)
      setLastRefresh(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load DNA Lab data")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const tabs = [
    { key: "top20",    label: "Top 20 DNA" },
    { key: "regime",   label: "Bull vs Bear" },
    { key: "timeline", label: "Year Timeline" },
    { key: "dna",      label: "DNA Features" },
  ] as const

  return (
    <div style={{ background: colors.background, minHeight: "100vh", padding: "0 0 80px 0" }}>

      {/* Header */}
      <div style={{ background: "#FFFFFF", borderBottom: "1px solid #E5E7EB",
        padding: "20px 20px 0 20px", position: "sticky", top: 0, zIndex: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start",
          marginBottom: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 22, fontWeight: 800, color: colors.textPrimary,
                letterSpacing: "-0.5px" }}>Multibagger DNA Lab</span>
              <span style={{ background: "#f3e8ff", color: "#7c3aed", fontSize: 10,
                fontWeight: 700, padding: "3px 8px", borderRadius: 6 }}>BETA</span>
            </div>
            <p style={{ fontSize: 12, color: "#6b7280", marginTop: 3 }}>
              10-year NSE historical analysis · {summary?.total_stocks ?? "—"} stocks · {summary?.total_events ?? "—"} winning entry points
            </p>
          </div>
          <button onClick={fetchAll} disabled={loading}
            style={{ background: loading ? "#F3F4F6" : "#EFF6FF",
              color: loading ? "#9CA3AF" : colors.blue,
              border: "1px solid " + (loading ? "#E5E7EB" : "#BFDBFE"),
              borderRadius: 10, padding: "8px 14px", fontSize: 12,
              fontWeight: 600, cursor: loading ? "not-allowed" : "pointer" }}>
            {loading ? "Loading…" : "↻ Refresh"}
          </button>
        </div>

        {/* Summary pills */}
        {summary && (
          <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4,
            scrollbarWidth: "none", marginBottom: 12 }}>
            <StatPill label="10x stocks" value={summary.stocks_10x} color="#7c3aed" />
            <StatPill label="5x stocks"  value={summary.stocks_5x}  color="#2563EB" />
            <StatPill label="3x stocks"  value={summary.stocks_3x}  color="#16A34A" />
            <StatPill label="2x stocks"  value={summary.stocks_2x}  color="#D97706" />
            <StatPill label="1x stocks"  value={summary.stocks_1x}  color="#6b7280" />
            <StatPill label="Best ever"  value={`${Math.round(summary.highest_ever_return)}%`} color="#7c3aed" />
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: "flex", gap: 0, borderTop: "1px solid #E5E7EB", marginTop: 4 }}>
          {tabs.map(t => (
            <button key={t.key} onClick={() => setActiveTab(t.key)}
              style={{ flex: 1, padding: "11px 4px", fontSize: 12, fontWeight: activeTab === t.key ? 700 : 500,
                color: activeTab === t.key ? colors.blue : "#6b7280",
                background: "transparent", border: "none", cursor: "pointer",
                borderBottom: activeTab === t.key ? `2px solid ${colors.blue}` : "2px solid transparent",
                transition: "all 0.15s" }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: "16px 16px 0" }}>

        {error && (
          <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 12,
            padding: "14px 16px", color: "#DC2626", fontSize: 13, marginBottom: 16 }}>
            ⚠ {error}
            {error.includes("does not exist") && (
              <div style={{ marginTop: 6, fontSize: 12, color: "#991B1B" }}>
                Scan not complete yet — run <code>node scripts/multibagger-scan.mjs</code> first.
              </div>
            )}
          </div>
        )}

        {loading && !error && (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#9CA3AF" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🧬</div>
            <div style={{ fontSize: 14 }}>Loading DNA data…</div>
          </div>
        )}

        {!loading && !error && activeTab === "top20" && <Top20View data={top20} />}
        {!loading && !error && activeTab === "regime" && <RegimeView data={regime} summary={summary} />}
        {!loading && !error && activeTab === "timeline" && <TimelineView data={sectors} />}
        {!loading && !error && activeTab === "dna" && <DnaFeaturesView data={dnaStats} />}

        {lastRefresh && (
          <div style={{ textAlign: "center", fontSize: 11, color: "#D1D5DB", marginTop: 24 }}>
            Last refreshed {lastRefresh.toLocaleTimeString()} · Data updates every Saturday
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tab: Top 20 DNA ───────────────────────────────────────────────────────────
function Top20View({ data }: { data: Top20Row[] }) {
  if (!data.length) return <EmptyState msg="No DNA data yet. Complete the scan first." />

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
        Ranked by DNA score — weighted peak classification + base quality + volume compression signals
      </p>
      {data.map((row, i) => {
        const tier = TIER_LABEL[row.peak_tier] ?? "1x"
        const regime = regimeBadge(row.typical_regime)
        return (
          <div key={row.tradingsymbol}
            style={{ background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: 14,
              padding: "14px 16px", boxShadow: "0 1px 6px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#9CA3AF",
                  minWidth: 20 }}>#{i+1}</span>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: colors.textPrimary,
                      letterSpacing: "-0.3px" }}>{row.tradingsymbol}</span>
                    <span style={{ background: classColor(tier) + "18",
                      color: classColor(tier), fontSize: 10, fontWeight: 700,
                      padding: "2px 7px", borderRadius: 5 }}>{tier}</span>
                    <span style={{ background: regime.bg, color: regime.color,
                      fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 5 }}>
                      {regime.label}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 2 }}>
                    {row.total_entry_points} winning entries · latest base {row.latest_base_date?.split("T")[0] ?? "—"}
                  </div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 16, fontWeight: 800,
                  color: classColor(tier) }}>{Math.round(row.peak_return)}%</div>
                <div style={{ fontSize: 10, color: "#9CA3AF" }}>peak return</div>
              </div>
            </div>

            <div style={{ marginTop: 10 }}>
              <ScoreBar score={row.dna_score} />
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: 10, flexWrap: "wrap" }}>
              <DNAFeaturePill label="Base" value={`${Math.round(row.avg_base_months)}M`}
                good={row.avg_base_months > 12} />
              <DNAFeaturePill label="Depth" value={`${Math.round(row.avg_base_depth)}%`}
                good={row.avg_base_depth < 30} />
              <DNAFeaturePill label="Vol compress" value={Number(row.avg_vol_compression).toFixed(2) ?? "—"}
                good={row.avg_vol_compression < 0.85} />
              <DNAFeaturePill label="Momentum" value={`${Math.round(row.avg_momentum)}%`}
                good={row.avg_momentum > 5} />
              {row.had_nr7 && (
                <span style={{ background: "#f3e8ff", color: "#7c3aed",
                  fontSize: 10, fontWeight: 700, padding: "3px 8px",
                  borderRadius: 5 }}>NR7 ✓</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DNAFeaturePill({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column",
      background: good ? "#F0FDF4" : "#F9FAFB",
      border: `1px solid ${good ? "#BBF7D0" : "#E5E7EB"}`,
      borderRadius: 7, padding: "4px 9px" }}>
      <span style={{ fontSize: 10, color: "#9CA3AF" }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 700,
        color: good ? "#16A34A" : colors.textPrimary }}>{value}</span>
    </div>
  )
}

// ── Tab: Bull vs Bear ─────────────────────────────────────────────────────────
function RegimeView({ data, summary }: { data: RegimeRow[]; summary: Summary | null }) {
  if (!data.length) return <EmptyState msg="No regime data yet." />

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "#FFF7ED", border: "1px solid #FED7AA",
        borderRadius: 12, padding: "12px 16px", fontSize: 12, color: "#92400E" }}>
        💡 <strong>Key insight:</strong> 50-60% of 10x winners built their base during a BEAR market.
        Corrections are accumulation windows, not exit signals.
      </div>

      {CLASS_ORDER.map(cls => {
        const bull = data.find(r => r.classification === cls && r.regime_at_base === "bull")
        const bear = data.find(r => r.classification === cls && r.regime_at_base === "bear")
        if (!bull && !bear) return null
        const total = (bull?.entry_points ?? 0) + (bear?.entry_points ?? 0)
        const bearPct = total > 0 ? Math.round((bear?.entry_points ?? 0) / total * 100) : 0
        const bullPct = 100 - bearPct

        return (
          <div key={cls} style={{ background: "#FFFFFF", border: "1px solid #E5E7EB",
            borderRadius: 14, padding: "16px", boxShadow: "0 1px 6px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between",
              alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 16, fontWeight: 800,
                color: classColor(cls) }}>{cls} Winners</span>
              <span style={{ fontSize: 12, color: "#6b7280" }}>
                {total} entry points across {((bull?.stocks ?? 0) + (bear?.stocks ?? 0))} stocks
              </span>
            </div>

            {/* Bull/Bear bar */}
            <div style={{ height: 10, borderRadius: 5, overflow: "hidden",
              display: "flex", marginBottom: 12 }}>
              <div style={{ width: `${bullPct}%`, background: "#16A34A", transition: "width 0.6s" }} />
              <div style={{ width: `${bearPct}%`, background: "#DC2626", transition: "width 0.6s" }} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                { label: "BULL market", data: bull, color: "#16A34A", bg: "#F0FDF4", pct: bullPct },
                { label: "BEAR market", data: bear, color: "#DC2626", bg: "#FEF2F2", pct: bearPct },
              ].map(({ label, data: d, color, bg, pct }) => (
                <div key={label} style={{ background: bg, borderRadius: 10, padding: "12px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color, marginBottom: 6 }}>
                    {label} · {pct}%
                  </div>
                  <div style={{ fontSize: 12, color: "#374151" }}>
                    <div>{d?.stocks ?? 0} stocks</div>
                    <div style={{ fontWeight: 700, fontSize: 14, color, marginTop: 2 }}>
                      avg {d?.avg_max_return ?? "—"}% peak
                    </div>
                    <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                      12m: {d?.avg_12m ?? "—"}% · 24m: {d?.avg_24m ?? "—"}%
                    </div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>
                      avg base {d?.avg_base_months ?? "—"} months
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Tab: Year Timeline ────────────────────────────────────────────────────────
function TimelineView({ data }: { data: SectorRow[] }) {
  if (!data.length) return <EmptyState msg="No timeline data yet." />

  const years = [...new Set(data.map(r => r.year))].sort((a, b) => b - a)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
        Winner entry points by year — shows which years produced the most multibaggers
      </p>
      {years.map(year => {
        const yearRows = data.filter(r => r.year === year)
        return (
          <div key={year} style={{ background: "#FFFFFF", border: "1px solid #E5E7EB",
            borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 6px rgba(0,0,0,0.04)" }}>
            <div style={{ fontSize: 15, fontWeight: 800, color: colors.textPrimary,
              marginBottom: 10 }}>{year}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {CLASS_ORDER.map(cls => {
                const r = yearRows.find(r => r.classification === cls)
                if (!r) return null
                return (
                  <div key={cls} style={{ background: classColor(cls) + "12",
                    border: `1px solid ${classColor(cls)}40`,
                    borderRadius: 8, padding: "6px 12px", minWidth: 80 }}>
                    <div style={{ fontSize: 10, fontWeight: 700,
                      color: classColor(cls) }}>{cls}</div>
                    <div style={{ fontSize: 13, fontWeight: 800,
                      color: colors.textPrimary }}>{r.stocks} stocks</div>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>
                      avg {r.avg_max_return}% peak
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Tab: DNA Features ─────────────────────────────────────────────────────────
function DnaFeaturesView({ data }: { data: DnaStats[] }) {
  if (!data.length) return <EmptyState msg="No DNA feature data yet." />

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE",
        borderRadius: 12, padding: "12px 16px", fontSize: 12, color: "#1E40AF" }}>
        📊 <strong>DNA Feature Analysis</strong> — average pre-breakout characteristics
        of each winner tier. Use these to identify current stocks in accumulation.
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E5E7EB",
        borderRadius: 14, overflow: "hidden", boxShadow: "0 1px 6px rgba(0,0,0,0.04)" }}>
        {/* Header */}
        <div style={{ display: "grid",
          gridTemplateColumns: "60px 1fr 1fr 1fr 1fr 1fr",
          gap: 0, background: "#F9FAFB", padding: "10px 16px",
          borderBottom: "1px solid #E5E7EB" }}>
          {["Tier", "Base", "Depth", "Vol Comp", "Momentum", "NR7 %"].map(h => (
            <div key={h} style={{ fontSize: 10, fontWeight: 700,
              color: "#6b7280", textAlign: "center" }}>{h}</div>
          ))}
        </div>

        {CLASS_ORDER.map(cls => {
          const r = data.find(d => d.classification === cls)
          if (!r) return null
          return (
            <div key={cls} style={{ display: "grid",
              gridTemplateColumns: "60px 1fr 1fr 1fr 1fr 1fr",
              padding: "12px 16px", borderBottom: "1px solid #F3F4F6",
              alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 800,
                color: classColor(cls) }}>{cls}</span>
              <Cell value={`${r.avg_base_months}M`}
                good={r.avg_base_months > 12} note=">12M ideal" />
              <Cell value={`${r.avg_base_depth_pct}%`}
                good={r.avg_base_depth_pct < 35} note="<35% ideal" />
              <Cell value={Number(r.avg_vol_compression).toFixed(2)}
                good={r.avg_vol_compression < 0.85} note="<0.85 ideal" />
              <Cell value={`${r.avg_momentum_6m}%`}
                good={r.avg_momentum_6m > 0} note=">0 ideal" />
              <Cell value={`${Math.round(r.pct_had_nr7 ?? 0)}%`}
                good={(r.pct_had_nr7 ?? 0) > 30} note=">30% ideal" />
            </div>
          )
        })}
      </div>

      <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB",
        borderRadius: 12, padding: "14px 16px", fontSize: 12, color: "#374151" }}>
        <div style={{ fontWeight: 700, marginBottom: 8, color: colors.textPrimary }}>
          Reading the DNA features:
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div><strong>Base length</strong> — months price stayed in a tight range before breakout. Longer = stronger accumulation.</div>
          <div><strong>Base depth</strong> — % range during base. Tighter = cleaner institutional accumulation.</div>
          <div><strong>Vol compression</strong> — recent 3M volume vs prior 3M. Below 1.0 = drying up before explosion.</div>
          <div><strong>Momentum 6M</strong> — RS slope into the base. Positive = stock already leading Nifty.</div>
          <div><strong>NR7 flag</strong> — narrowest range of 7 months = coiled spring. Classic pre-breakout signal.</div>
        </div>
      </div>
    </div>
  )
}

function Cell({ value, good, note }: { value: string | number; good: boolean; note: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 13, fontWeight: 700,
        color: good ? "#16A34A" : "#DC2626" }}>{value ?? "—"}</div>
      <div style={{ fontSize: 9, color: "#D1D5DB" }}>{note}</div>
    </div>
  )
}

function EmptyState({ msg }: { msg: string }) {
  return (
    <div style={{ textAlign: "center", padding: "60px 20px", color: "#9CA3AF" }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>🧬</div>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{msg}</div>
      <div style={{ fontSize: 12 }}>
        Run <code style={{ background: "#F3F4F6", padding: "2px 6px",
          borderRadius: 4 }}>node scripts/multibagger-scan.mjs</code> to populate data.
      </div>
    </div>
  )
}

