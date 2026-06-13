"use client";
import React, { useState, useEffect, useCallback } from "react";
import {
  RefreshCw, ChevronDown, ChevronUp, Droplets,
  AlertTriangle, TrendingUp, TrendingDown, Minus,
  Star, Eye, ShieldAlert, Zap, BarChart2
} from "lucide-react";

/* ═══════════════════════════════════════════════════════════════
   AACapital Intelligence Dashboard — V10
   Philosophy: Tell users WHAT TO DO, not just what the data says.
   Every card answers: Buy? Avoid? Watch? Add more? Exit?

   Guru filters: Buffett · Lynch · QGLP · Mayer · Turnaround · Avoid
   Modes: Simple (beginners) · Advanced (pros)
   ═══════════════════════════════════════════════════════════════ */

// ─── Types ───────────────────────────────────────────────────────

interface EarningsRow {
  symbol: string;
  company_name: string;
  fiscal_year: number;
  fiscal_quarter: string;
  revenue_acceleration_score: string | number;
  pat_acceleration_score: string | number;
  margin_expansion_score: string | number;
  consistency_score: string | number;
  total_score: string | number;
  acceleration_status: "ACCELERATING" | "STABLE" | "DECELERATING" | "TURNAROUND" | "WARNING";
  updated_at: string;
}

interface CommentaryRow {
  symbol: string;
  company_name: string;
  fiscal_quarter: string;
  fiscal_year?: number;
  demand_score: string | number;
  margin_score: string | number;
  order_book_score: string | number;
  guidance_score: string | number;
  risk_score: string | number;
  confidence_score: string | number;
  total_score: string | number;
  commentary_status: "BULLISH" | "IMPROVING" | "NEUTRAL" | "CAUTIOUS" | "DETERIORATING";
  score_reason: string;
  management_tone?: string;
  guidance_direction?: string;
  order_book_cr?: string | number;
  confidence?: string;
}

interface AmfiScore {
  report_month: number;
  report_year: number;
  equity_flow_score: string | number;
  sip_strength_score: string | number;
  smallcap_heat_score: string | number;
  midcap_heat_score: string | number;
  total_score: string | number;
  liquidity_status: "RISK_ON" | "SELECTIVE_RISK_ON" | "NEUTRAL" | "RISK_OFF" | "OVERHEATED";
  score_reason: string;
}

interface DashboardData {
  top_earnings: EarningsRow[];
  top_commentary: CommentaryRow[];
  amfi_liquidity: AmfiScore | null;
  warning_earnings: EarningsRow[];
  cautious_commentary: CommentaryRow[];
}

interface MergedStock {
  symbol: string;
  company_name: string;
  earnings?: EarningsRow;
  commentary?: CommentaryRow;
  combinedScore: number;
  earningsStatus: string;
  commentaryStatus: string;
  action: "ACCUMULATE" | "WATCH" | "AVOID" | "TURNAROUND" | "TRIM";
  conviction: number;
  whyBuy: string[];
  whyAvoid: string[];
}

// ─── Helpers ─────────────────────────────────────────────────────

const n = (v: string | number | undefined | null) =>
  parseFloat(String(v || 0)) || 0;

const MONTH_NAMES = ["","Jan","Feb","Mar","Apr","May","Jun",
  "Jul","Aug","Sep","Oct","Nov","Dec"];

function deriveAction(earningsStatus: string, commentaryStatus: string, combinedScore: number): MergedStock["action"] {
  if (["DECELERATING","WARNING"].includes(earningsStatus) || commentaryStatus === "DETERIORATING") return "AVOID";
  if (earningsStatus === "TURNAROUND") return "TURNAROUND";
  if (earningsStatus === "ACCELERATING" && ["BULLISH","IMPROVING"].includes(commentaryStatus)) return "ACCUMULATE";
  if (commentaryStatus === "CAUTIOUS" || earningsStatus === "WARNING") return "TRIM";
  return "WATCH";
}

function deriveWhyBuy(e?: EarningsRow, c?: CommentaryRow): string[] {
  const reasons: string[] = [];
  if (e) {
    if (n(e.revenue_acceleration_score) > 20) reasons.push("Revenue accelerating");
    if (n(e.pat_acceleration_score) > 20) reasons.push("Profit momentum strong");
    if (n(e.margin_expansion_score) > 10) reasons.push("Margins expanding");
    if (n(e.consistency_score) > 20) reasons.push("Consistent execution");
  }
  if (c) {
    if (["BULLISH","IMPROVING"].includes(c.commentary_status)) reasons.push("Management confident");
    if (n(c.order_book_score) > 20) reasons.push("Strong order book");
    if (n(c.guidance_score) > 15) reasons.push("Guidance positive");
  }
  return reasons.slice(0, 4);
}

function deriveWhyAvoid(e?: EarningsRow, c?: CommentaryRow): string[] {
  const reasons: string[] = [];
  if (e) {
    if (n(e.pat_acceleration_score) < 0) reasons.push("Profit declining");
    if (n(e.revenue_acceleration_score) < 0) reasons.push("Revenue slowing");
    if (e.acceleration_status === "WARNING") reasons.push("Earnings deteriorating");
  }
  if (c) {
    if (["CAUTIOUS","DETERIORATING"].includes(c.commentary_status)) reasons.push("Mgmt tone cautious");
    if (n(c.risk_score) < -10) reasons.push("High risk signals");
  }
  return reasons.slice(0, 3);
}

// ─── Color maps ───────────────────────────────────────────────────

const ACTION_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  ACCUMULATE: { bg: "#EAF3DE", text: "#27500A", label: "Accumulate" },
  TURNAROUND: { bg: "#E6F1FB", text: "#0C447C", label: "Turnaround" },
  WATCH:      { bg: "#F1EFE8", text: "#5F5E5A", label: "Watch" },
  TRIM:       { bg: "#FAEEDA", text: "#633806", label: "Trim" },
  AVOID:      { bg: "#FCEBEB", text: "#791F1F", label: "Avoid" },
};

const AMFI_STYLE: Record<string, { bg: string; text: string; label: string; deploy: string }> = {
  RISK_ON:           { bg: "#EAF3DE", text: "#27500A", label: "Risk On",    deploy: "Deploy fully — market conditions supportive" },
  SELECTIVE_RISK_ON: { bg: "#E6F1FB", text: "#0C447C", label: "Selective",  deploy: "Deploy selectively — pick only high-conviction ideas" },
  NEUTRAL:           { bg: "#F1EFE8", text: "#5F5E5A", label: "Neutral",    deploy: "Hold current positions — wait for clarity" },
  RISK_OFF:          { bg: "#FAEEDA", text: "#633806", label: "Risk Off",   deploy: "Reduce exposure — protect capital" },
  OVERHEATED:        { bg: "#FCEBEB", text: "#791F1F", label: "Overheated", deploy: "Caution — markets may be frothy, book partial profits" },
};

// ─── Guru Filter Definitions ─────────────────────────────────────

const GURU_FILTERS = [
  {
    id: "all", name: "All stocks", icon: "🌐",
    simple: "Show everything",
    desc: "All stocks with intelligence scores",
    criteria: (_: MergedStock) => true,
  },
  {
    id: "accumulate", name: "Best ideas", icon: "⭐",
    simple: "Best stocks to buy now",
    desc: "High conviction — accelerating earnings + bullish management. Strong buy candidates.",
    criteria: (s: MergedStock) => s.action === "ACCUMULATE",
  },
  {
    id: "buffett", name: "Buffett quality", icon: "🏦",
    simple: "Quality businesses",
    desc: "Consistent earnings growth + confident management. Quality moat businesses.",
    criteria: (s: MergedStock) =>
      s.earningsStatus === "ACCELERATING" &&
      ["BULLISH","IMPROVING"].includes(s.commentaryStatus) &&
      n(s.earnings?.consistency_score) >= 15,
  },
  {
    id: "lynch", name: "Lynch growth", icon: "📈",
    simple: "Fast growing companies",
    desc: "High earnings acceleration + bullish commentary. Strong growth momentum.",
    criteria: (s: MergedStock) =>
      n(s.earnings?.total_score) >= 60 &&
      ["BULLISH","IMPROVING"].includes(s.commentaryStatus),
  },
  {
    id: "qglp", name: "QGLP", icon: "🇮🇳",
    simple: "Quality + Growth (Indian style)",
    desc: "Raamdeo QGLP: Quality + Growth + Longevity + Price. Accelerating earnings + positive guidance + consistency.",
    criteria: (s: MergedStock) =>
      s.earningsStatus === "ACCELERATING" &&
      n(s.commentary?.guidance_score) >= 15 &&
      n(s.earnings?.consistency_score) >= 15,
  },
  {
    id: "mayer", name: "Mayer 100x", icon: "🚀",
    simple: "Potential multibaggers",
    desc: "Explosive earnings score + bullish order book. Potential multibagger setup.",
    criteria: (s: MergedStock) =>
      n(s.earnings?.total_score) >= 70 &&
      s.commentaryStatus === "BULLISH" &&
      n(s.commentary?.order_book_score) >= 20,
  },
  {
    id: "turnaround", name: "Turnarounds", icon: "🔄",
    simple: "Recovering companies",
    desc: "Earnings turning around or commentary improving after weakness. Early recovery plays.",
    criteria: (s: MergedStock) =>
      s.action === "TURNAROUND" ||
      (s.earningsStatus === "STABLE" && s.commentaryStatus === "IMPROVING"),
  },
  {
    id: "avoid", name: "Avoid / risk", icon: "⚠️",
    simple: "Stocks to stay away from",
    desc: "Decelerating earnings or cautious/deteriorating commentary. Reduce or exit exposure.",
    criteria: (s: MergedStock) => s.action === "AVOID" || s.action === "TRIM",
  },
];

// ─── Sub-components ───────────────────────────────────────────────

function ScoreBar({ score, max = 100, color }: { score: number; max?: number; color?: string }) {
  const pct = Math.max(0, Math.min(100, (score / max) * 100));
  const c = color || (score >= 60 ? "#3B6D11" : score >= 30 ? "#BA7517" : score >= 0 ? "#888780" : "#A32D2D");
  return (
    <div style={{ height: 3, background: "var(--color-border-tertiary)", borderRadius: 2, overflow: "hidden", width: "100%" }}>
      <div style={{ height: "100%", width: `${Math.max(0, pct)}%`, background: c, borderRadius: 2 }} />
    </div>
  );
}

function Tag({ label, bg, text, size = 12 }: { label: string; bg: string; text: string; size?: number }) {
  return (
    <span style={{ fontSize: size, fontWeight: 500, padding: "2px 8px", borderRadius: 4, background: bg, color: text, whiteSpace: "nowrap", display: "inline-block" }}>
      {label}
    </span>
  );
}

// ─── AMFI Regime Banner ───────────────────────────────────────────

function AmfiBanner({ amfi, simple }: { amfi: AmfiScore | null; simple: boolean }) {
  if (!amfi) return null;
  const s = AMFI_STYLE[amfi.liquidity_status] || AMFI_STYLE.NEUTRAL;
  const month = MONTH_NAMES[amfi.report_month] || "";
  return (
    <div style={{
      background: s.bg,
      border: `0.5px solid ${s.text}40`,
      borderRadius: "var(--border-radius-md)",
      padding: "10px 14px",
      marginBottom: 14,
      display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
    }}>
      <Droplets size={15} color={s.text} aria-hidden />
      <div>
        <span style={{ fontSize: 12, fontWeight: 500, color: s.text }}>
          Market liquidity — {s.label}
        </span>
        <span style={{ fontSize: 11, color: s.text, opacity: .7, marginLeft: 8 }}>
          AMFI {month} {amfi.report_year}
        </span>
      </div>
      <div style={{ marginLeft: "auto", fontSize: 12, color: s.text, fontWeight: simple ? 500 : 400 }}>
        {simple ? s.deploy : amfi.score_reason?.split(":")[1]?.trim() || s.deploy}
      </div>
    </div>
  );
}

// ─── Conviction Card (V10 style) ──────────────────────────────────

function ConvictionCard({ stock, simple, expanded, onToggle }: {
  stock: MergedStock;
  simple: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const e = stock.earnings;
  const c = stock.commentary;
  const as = ACTION_STYLE[stock.action];
  const conviction = Math.round(stock.conviction);

  return (
    <div style={{
      background: "var(--color-background-primary)",
      border: "0.5px solid var(--color-border-tertiary)",
      borderLeft: `3px solid ${as.text}`,
      borderRadius: "var(--border-radius-lg)",
      marginBottom: 8,
      overflow: "hidden",
    }}>
      {/* ── Header ── */}
      <div onClick={onToggle} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 10 }}>

        {/* Action tag */}
        <Tag label={as.label} bg={as.bg} text={as.text} size={11} />

        {/* Symbol + name */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: "var(--color-text-primary)" }}>
            {stock.symbol}
          </div>
          {!simple && (
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {stock.company_name}
            </div>
          )}
        </div>

        {/* Conviction score */}
        <div style={{ textAlign: "right", minWidth: 60 }}>
          <div style={{ fontSize: 18, fontWeight: 500, color: as.text }}>{conviction}</div>
          <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>conviction</div>
        </div>

        {/* Simple mode: why summary */}
        {simple && stock.whyBuy.length > 0 && (
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)", maxWidth: 140, lineHeight: 1.4, textAlign: "right" }}>
            {stock.whyBuy.slice(0, 2).join(" · ")}
          </div>
        )}

        {/* Quarter label (advanced) */}
        {!simple && e && (
          <div style={{ fontSize: 10, color: "var(--color-text-secondary)", minWidth: 44, textAlign: "right" }}>
            {e.fiscal_quarter} FY{String(e.fiscal_year).slice(-2)}
          </div>
        )}

        <div style={{ color: "var(--color-text-secondary)" }}>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {/* ── Expanded ── */}
      {expanded && (
        <div style={{ borderTop: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-secondary)", padding: "12px 14px" }}>

          {/* Simple mode: plain-English reasons */}
          {simple && (
            <div style={{ marginBottom: stock.whyBuy.length > 0 ? 12 : 0 }}>
              {stock.whyBuy.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 500, color: "#27500A", marginBottom: 4 }}>Why this looks good</div>
                  {stock.whyBuy.map(r => (
                    <div key={r} style={{ fontSize: 12, color: "var(--color-text-secondary)", display: "flex", gap: 6, marginBottom: 2 }}>
                      <span style={{ color: "#3B6D11" }}>✓</span> {r}
                    </div>
                  ))}
                </div>
              )}
              {stock.whyAvoid.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 500, color: "#791F1F", marginBottom: 4 }}>Watch out for</div>
                  {stock.whyAvoid.map(r => (
                    <div key={r} style={{ fontSize: 12, color: "var(--color-text-secondary)", display: "flex", gap: 6, marginBottom: 2 }}>
                      <span style={{ color: "#A32D2D" }}>⚠</span> {r}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Advanced mode: score breakdown */}
          {!simple && (
            <div style={{ display: "grid", gridTemplateColumns: e && c ? "1fr 1fr" : "1fr", gap: 14 }}>
              {e && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
                    Earnings acceleration
                  </div>
                  {[
                    { label: "Revenue momentum", val: n(e.revenue_acceleration_score), max: 50 },
                    { label: "Profit momentum",  val: n(e.pat_acceleration_score),     max: 50 },
                    { label: "Margin expansion", val: n(e.margin_expansion_score),     max: 25 },
                    { label: "Consistency",      val: n(e.consistency_score),          max: 30 },
                  ].map(({ label, val, max }) => (
                    <div key={label} style={{ marginBottom: 7 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                        <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>{label}</span>
                        <span style={{ fontSize: 11, fontWeight: 500, color: "var(--color-text-primary)" }}>{Math.round(val)}</span>
                      </div>
                      <ScoreBar score={val} max={max} />
                    </div>
                  ))}
                  <div style={{ fontSize: 11, fontWeight: 500, color: ACTION_STYLE[stock.action]?.text, marginTop: 4 }}>
                    Total: {Math.round(n(e.total_score))}
                  </div>
                </div>
              )}
              {c && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
                    Management commentary
                  </div>
                  {[
                    { label: "Demand signal",    val: n(c.demand_score),     max: 40 },
                    { label: "Margin outlook",   val: n(c.margin_score),     max: 20 },
                    { label: "Order book",       val: n(c.order_book_score), max: 40 },
                    { label: "Guidance quality", val: n(c.guidance_score),   max: 30 },
                  ].map(({ label, val, max }) => (
                    <div key={label} style={{ marginBottom: 7 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                        <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>{label}</span>
                        <span style={{ fontSize: 11, fontWeight: 500, color: "var(--color-text-primary)" }}>{Math.round(val)}</span>
                      </div>
                      <ScoreBar score={val} max={max} />
                    </div>
                  ))}
                  {c.management_tone && (
                    <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 4 }}>
                      Tone: <span style={{ fontWeight: 500, color: "var(--color-text-primary)" }}>{c.management_tone}</span>
                    </div>
                  )}
                  {c.order_book_cr && n(c.order_book_cr) > 0 && (
                    <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
                      Order book: <span style={{ fontWeight: 500, color: "var(--color-text-primary)" }}>
                        ₹{Math.round(n(c.order_book_cr)).toLocaleString()} Cr
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Advanced: status tags row */}
          {!simple && (
            <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
              {e && <Tag label={stock.earningsStatus} bg={ACTION_STYLE[stock.action]?.bg} text={ACTION_STYLE[stock.action]?.text} size={10} />}
              {c && <Tag label={stock.commentaryStatus} bg={ACTION_STYLE[stock.action]?.bg} text={ACTION_STYLE[stock.action]?.text} size={10} />}
              {c?.confidence && <Tag label={`Confidence: ${c.confidence}`} bg="var(--color-background-primary)" text="var(--color-text-secondary)" size={10} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Summary stat card ────────────────────────────────────────────

function StatCard({ val, label, color }: { val: number; label: string; color: string }) {
  return (
    <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-md)", padding: "10px 12px" }}>
      <div style={{ fontSize: 22, fontWeight: 500, color }}>{val}</div>
      <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 1 }}>{label}</div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────

export function IntelligenceDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeGuru, setActiveGuru] = useState("accumulate");
  const [sortBy, setSortBy] = useState<"conviction" | "earnings" | "commentary">("conviction");
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const [simpleMode, setSimpleMode] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashRes, commRes] = await Promise.all([
        fetch("/api/intelligence/dashboard"),
        fetch("/api/intelligence/commentary?limit=200"),
      ]);
      const dash = await dashRes.json();
      const comm = await commRes.json();
      if (!dash.success) throw new Error(dash.error);

      if (comm.success && Array.isArray(comm.data)) {
        const commMap = new Map<string, CommentaryRow>(
          comm.data.map((c: CommentaryRow) => [c.symbol, c])
        );
        dash.data.top_commentary = dash.data.top_commentary.map((c: CommentaryRow) => {
          const extra = commMap.get(c.symbol);
          return extra ? { ...extra, ...c } : { ...c };
        });
      }

      setData(dash.data);
      setLastRefresh(new Date());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Merge all stocks ──────────────────────────────────────────

  const merged: MergedStock[] = React.useMemo(() => {
    if (!data) return [];
    const map = new Map<string, MergedStock>();

    const allEarnings = [...(data.top_earnings || []), ...(data.warning_earnings || [])];
    const allCommentary = [...(data.top_commentary || []), ...(data.cautious_commentary || [])];

    allEarnings.forEach(e => {
      const action = deriveAction(e.acceleration_status, "NEUTRAL", n(e.total_score));
      map.set(e.symbol, {
        symbol: e.symbol,
        company_name: e.company_name,
        earnings: e,
        combinedScore: n(e.total_score),
        earningsStatus: e.acceleration_status,
        commentaryStatus: "NEUTRAL",
        action,
        conviction: Math.max(0, n(e.total_score)),
        whyBuy: deriveWhyBuy(e, undefined),
        whyAvoid: deriveWhyAvoid(e, undefined),
      });
    });

    allCommentary.forEach(c => {
      const existing = map.get(c.symbol);
      if (existing) {
        existing.commentary = c;
        existing.commentaryStatus = c.commentary_status;
        const combined = (n(existing.earnings?.total_score) + n(c.total_score)) / 2;
        existing.combinedScore = combined;
        existing.action = deriveAction(existing.earningsStatus, c.commentary_status, combined);
        existing.conviction = Math.max(0, combined);
        existing.whyBuy = deriveWhyBuy(existing.earnings, c);
        existing.whyAvoid = deriveWhyAvoid(existing.earnings, c);
      } else {
        const action = deriveAction("STABLE", c.commentary_status, n(c.total_score));
        map.set(c.symbol, {
          symbol: c.symbol,
          company_name: c.company_name,
          commentary: c,
          combinedScore: n(c.total_score),
          earningsStatus: "STABLE",
          commentaryStatus: c.commentary_status,
          action,
          conviction: Math.max(0, n(c.total_score)),
          whyBuy: deriveWhyBuy(undefined, c),
          whyAvoid: deriveWhyAvoid(undefined, c),
        });
      }
    });

    return Array.from(map.values());
  }, [data]);

  // ── Filter + sort ─────────────────────────────────────────────

  const filtered = React.useMemo(() => {
    const guru = GURU_FILTERS.find(g => g.id === activeGuru);
    let list = merged.filter(s => guru ? guru.criteria(s) : true);

    if (searchQ.trim()) {
      const q = searchQ.toUpperCase().trim();
      list = list.filter(s => s.symbol.includes(q) || s.company_name?.toUpperCase().includes(q));
    }

    list.sort((a, b) => {
      if (sortBy === "earnings") return n(b.earnings?.total_score) - n(a.earnings?.total_score);
      if (sortBy === "commentary") return n(b.commentary?.total_score) - n(a.commentary?.total_score);
      return b.conviction - a.conviction;
    });

    return list;
  }, [merged, activeGuru, searchQ, sortBy]);

  // ── Counts ────────────────────────────────────────────────────

  const counts = React.useMemo(() => ({
    accumulate: merged.filter(s => s.action === "ACCUMULATE").length,
    watch: merged.filter(s => s.action === "WATCH").length,
    avoid: merged.filter(s => ["AVOID","TRIM"].includes(s.action)).length,
    total: merged.length,
  }), [merged]);

  const activeGuruDef = GURU_FILTERS.find(g => g.id === activeGuru);

  // ── Loading / error ───────────────────────────────────────────

  if (loading) return (
    <div style={{ padding: 48, textAlign: "center", color: "var(--color-text-secondary)" }}>
      <RefreshCw size={18} style={{ marginBottom: 10, display: "block", margin: "0 auto 10px", animation: "spin 1s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      Loading intelligence...
    </div>
  );

  if (error) return (
    <div style={{ padding: 16, background: "#FCEBEB", borderRadius: "var(--border-radius-md)", color: "#791F1F", fontSize: 13 }}>
      <AlertTriangle size={13} style={{ marginRight: 6, verticalAlign: -2 }} />
      {error}
      <button onClick={load} style={{ marginLeft: 10, fontSize: 12, textDecoration: "underline", background: "none", border: "none", cursor: "pointer", color: "#791F1F" }}>
        Retry
      </button>
    </div>
  );

  return (
    <div style={{ fontFamily: "var(--font-sans, sans-serif)" }}>

      {/* ── Mode toggle ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
          {lastRefresh && `Updated ${lastRefresh.toLocaleTimeString()}`}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {[
            { id: false, label: "Simple", icon: <Star size={11} /> },
            { id: true,  label: "Advanced", icon: <BarChart2 size={11} /> },
          ].map(({ id, label, icon }) => (
            <button
              key={String(id)}
              onClick={() => setSimpleMode(!id)}
              style={{
                display: "flex", alignItems: "center", gap: 4,
                fontSize: 11, padding: "4px 10px", borderRadius: 16,
                border: simpleMode === !id
                  ? "1.5px solid var(--color-text-primary)"
                  : "0.5px solid var(--color-border-tertiary)",
                background: simpleMode === !id ? "var(--color-text-primary)" : "var(--color-background-primary)",
                color: simpleMode === !id ? "var(--color-background-primary)" : "var(--color-text-secondary)",
                cursor: "pointer",
              }}
            >
              {icon} {label}
            </button>
          ))}
          <button onClick={load} style={{ padding: "4px 8px", borderRadius: 16, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", cursor: "pointer", color: "var(--color-text-secondary)" }} title="Refresh">
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      {/* ── AMFI Regime Banner ── */}
      <AmfiBanner amfi={data?.amfi_liquidity || null} simple={simpleMode} />

      {/* ── Summary stats ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginBottom: 14 }}>
        {[
          { val: counts.total,      label: "Stocks tracked",  color: "var(--color-text-primary)", filter: "all"        },
          { val: counts.accumulate, label: "Accumulate",      color: "#3B6D11",                   filter: "accumulate" },
          { val: counts.watch,      label: "Watch",           color: "#5F5E5A",                   filter: "watch"      },
          { val: counts.avoid,      label: "Avoid / trim",    color: "#A32D2D",                   filter: "avoid"      },
        ].map(({ val, label, color, filter }) => (
          <div key={label} onClick={() => setActiveGuru(filter === "watch" ? "all" : filter === "avoid" ? "avoid" : filter === "accumulate" ? "accumulate" : "all")}
            style={{ background: activeGuru === (filter === "accumulate" ? "accumulate" : filter === "avoid" ? "avoid" : "all") && filter !== "all" ? color + "18" : "var(--color-background-secondary)",
              borderRadius: "var(--border-radius-md)", padding: "10px 12px", cursor: "pointer",
              border: `1px solid ${activeGuru === (filter === "accumulate" ? "accumulate" : filter === "avoid" ? "avoid" : "all") && filter !== "all" ? color : "transparent"}` }}>
            <div style={{ fontSize: 22, fontWeight: 500, color }}>{val}</div>
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 1 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* ── Guru filter pills ── */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".07em", marginBottom: 6 }}>
          {simpleMode ? "What am I looking for?" : "Guru filters"}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {GURU_FILTERS.map(g => (
            <button
              key={g.id}
              onClick={() => setActiveGuru(g.id)}
              title={g.desc}
              style={{
                fontSize: 12, padding: "5px 12px", borderRadius: 20,
                border: activeGuru === g.id
                  ? "1.5px solid var(--color-text-primary)"
                  : "0.5px solid var(--color-border-tertiary)",
                background: activeGuru === g.id ? "var(--color-text-primary)" : "var(--color-background-primary)",
                color: activeGuru === g.id ? "var(--color-background-primary)" : "var(--color-text-secondary)",
                cursor: "pointer",
                fontWeight: activeGuru === g.id ? 500 : 400,
              }}
            >
              {g.icon} {simpleMode ? g.simple : g.name}
            </button>
          ))}
        </div>
        {activeGuruDef && !simpleMode && activeGuru !== "all" && (
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 5 }}>
            {activeGuruDef.desc}
          </div>
        )}
      </div>

      {/* ── Search + sort ── */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
        <input
          type="text"
          placeholder={simpleMode ? "Search a company..." : "Search symbol or company..."}
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          style={{ flex: 1, padding: "7px 12px", fontSize: 13, borderRadius: "var(--border-radius-md)", border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)" }}
        />
        {!simpleMode && (
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value as typeof sortBy)}
            style={{ fontSize: 12, padding: "7px 10px", borderRadius: "var(--border-radius-md)", border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)" }}
          >
            <option value="conviction">Sort: conviction</option>
            <option value="earnings">Sort: earnings</option>
            <option value="commentary">Sort: commentary</option>
          </select>
        )}
      </div>

      {/* ── Results count ── */}
      <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginBottom: 8 }}>
        {filtered.length} stock{filtered.length !== 1 ? "s" : ""}
        {activeGuru !== "all" ? ` — ${activeGuruDef?.simple || activeGuruDef?.name}` : ""}
      </div>

      {/* ── Stock list ── */}
      {filtered.length === 0 ? (
        <div style={{ padding: "32px 0", textAlign: "center", color: "var(--color-text-secondary)", fontSize: 14 }}>
          No stocks match this filter.
          <button onClick={() => setActiveGuru("all")} style={{ marginLeft: 8, fontSize: 13, textDecoration: "underline", background: "none", border: "none", cursor: "pointer", color: "var(--color-text-secondary)" }}>
            Show all
          </button>
        </div>
      ) : (
        filtered.map(stock => (
          <ConvictionCard
            key={stock.symbol}
            stock={stock}
            simple={simpleMode}
            expanded={expandedSymbol === stock.symbol}
            onToggle={() => setExpandedSymbol(expandedSymbol === stock.symbol ? null : stock.symbol)}
          />
        ))
      )}
    </div>
  );
}
