"use client";
// components/ipo/IPOIntelligenceCard.tsx
// Task 6: IPO Intelligence Card — LQI score + Bayesian probability display

import { useState } from "react";

export interface IPOIntelligence {
  id: number;
  company_name: string;
  issue_price: number | null;
  issue_size_cr: number | null;
  issue_open_date: string | null;
  issue_close_date: string | null;
  listing_date: string | null;
  ipo_status: string | null;

  // LQI dimensions
  lqi_score: number | null;
  conviction: string | null;

  // Bayesian probabilities
  p_profit_10pct: number | null;
  p_loss: number | null;
  expected_return_pct: number | null;

  // Subscription
  qib_subscription: number | null;
  nii_subscription: number | null;
  retail_subscription: number | null;
  total_subscription: number | null;

  // GMP
  gmp_percentage: number | null;
  gmp_value: number | null;

  // Fundamentals
  revenue_growth_3yr: number | null;
  pat_growth_3yr: number | null;
  pe_ratio: number | null;
  sector_pe_median: number | null;

  // Anchor
  anchor_classification: string | null;
  anchor_investor_count: number | null;

  // Structure
  ofs_percentage: number | null;
  promoter_holding_post: number | null;
  is_sme: boolean | null;
  listing_exchange: string | null;

  // Cosine similar IPOs
  similar_ipos?: string[];
}

// ── sub-components ─────────────────────────────────────────────────────────────

function LQIGauge({ score }: { score: number | null }) {
  const s = score ?? 0;
  const pct = Math.min(s, 100);

  let color = "#e5e7eb";
  let label = "N/A";
  if (s >= 75)      { color = "#059669"; label = "Strong Buy"; }
  else if (s >= 60) { color = "#2563eb"; label = "Buy"; }
  else if (s >= 45) { color = "#f59e0b"; label = "Neutral"; }
  else if (s >= 30) { color = "#f97316"; label = "Avoid"; }
  else if (s > 0)   { color = "#dc2626"; label = "Strong Avoid"; }

  // SVG arc
  const r   = 54;
  const cx  = 70;
  const cy  = 70;
  const circ = Math.PI * r; // half circle
  const dash = (pct / 100) * circ;

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="80" viewBox="0 0 140 80">
        {/* Track */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke="#f3f4f6"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
        />
        {/* Score text */}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="22" fontWeight="700" fill={color}>
          {score !== null ? Math.round(score) : "—"}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="10" fill="#9ca3af">
          / 100
        </text>
      </svg>
      <span
        className="text-xs font-semibold px-3 py-0.5 rounded-full mt-1"
        style={{ backgroundColor: `${color}20`, color }}
      >
        {label}
      </span>
    </div>
  );
}

function ProbBar({
  label, value, color,
}: { label: string; value: number | null; color: string }) {
  const pct = value !== null ? Math.round(value * 100) : null;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-500">{label}</span>
        <span className="font-semibold" style={{ color }}>{pct !== null ? `${pct}%` : "—"}</span>
      </div>
      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct ?? 0}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function MetricRow({ label, value, suffix = "" }: {
  label: string; value: number | string | null | undefined; suffix?: string;
}) {
  const display = value !== null && value !== undefined
    ? `${value}${suffix}`
    : "—";
  return (
    <div className="flex justify-between py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-xs text-gray-400">{label}</span>
      <span className="text-xs font-medium text-gray-700">{display}</span>
    </div>
  );
}

function DimensionPill({ label, value, goodThreshold, isGood }: {
  label: string;
  value: string | number | null;
  goodThreshold?: string;
  isGood?: boolean;
}) {
  const good = isGood !== undefined ? isGood : true;
  return (
    <div className={`rounded-lg p-2.5 border ${
      good ? "border-emerald-100 bg-emerald-50" : "border-gray-100 bg-gray-50"
    }`}>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className={`text-sm font-semibold ${good ? "text-emerald-700" : "text-gray-600"}`}>
        {value !== null && value !== undefined ? String(value) : "—"}
      </p>
      {goodThreshold && (
        <p className="text-[10px] text-gray-400 mt-0.5">{goodThreshold}</p>
      )}
    </div>
  );
}

// ── main card ──────────────────────────────────────────────────────────────────

interface Props {
  ipo: IPOIntelligence;
  compact?: boolean;
}

const TABS = ["Overview", "Subscription", "Financials", "Anchor", "Structure"] as const;
type Tab = typeof TABS[number];

export default function IPOIntelligenceCard({ ipo, compact = false }: Props) {
  const [tab, setTab] = useState<Tab>("Overview");

  const statusBadge: Record<string, string> = {
    OPEN:               "bg-green-100 text-green-800",
    CLOSED:             "bg-gray-100 text-gray-600",
    ALLOTMENT_PENDING:  "bg-blue-100 text-blue-800",
    LISTING_PENDING:    "bg-purple-100 text-purple-800",
    LISTED:             "bg-emerald-100 text-emerald-800",
    WITHDRAWN:          "bg-red-100 text-red-700",
  };

  const peVsPeers =
    ipo.pe_ratio && ipo.sector_pe_median
      ? ((Number(ipo.pe_ratio) / Number(ipo.sector_pe_median)) * 100 - 100).toFixed(1)
      : null;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-gray-900 truncate">
                {ipo.company_name}
              </h2>
              {ipo.is_sme && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                  SME
                </span>
              )}
              {ipo.ipo_status && (
                <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                  statusBadge[ipo.ipo_status] ?? "bg-gray-100 text-gray-600"
                }`}>
                  {ipo.ipo_status.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 flex-wrap">
              {ipo.issue_price && <span>₹{ipo.issue_price}</span>}
              {ipo.issue_size_cr && <span>₹{ipo.issue_size_cr.toLocaleString("en-IN")} Cr</span>}
              {ipo.listing_exchange && <span>{ipo.listing_exchange}</span>}
              {ipo.listing_date && (
                <span>Lists: {String(ipo.listing_date).substring(0, 10)}</span>
              )}
            </div>
          </div>

          {/* LQI gauge */}
          {!compact && <LQIGauge score={ipo.lqi_score} />}
          {compact && ipo.lqi_score !== null && (
            <div className="text-right">
              <p className="text-2xl font-bold text-blue-600">{Math.round(ipo.lqi_score)}</p>
              <p className="text-[10px] text-gray-400">LQI</p>
            </div>
          )}
        </div>
      </div>

      {/* Probability bars — always visible */}
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 grid grid-cols-2 gap-4">
        <ProbBar
          label="P(>10% profit)"
          value={ipo.p_profit_10pct}
          color="#2563eb"
        />
        <ProbBar
          label="P(loss)"
          value={ipo.p_loss}
          color="#dc2626"
        />
        <div className="col-span-2 flex items-center justify-between">
          <span className="text-xs text-gray-400">Expected return</span>
          <span className={`text-sm font-bold ${
            (ipo.expected_return_pct ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
          }`}>
            {ipo.expected_return_pct !== null
              ? `${ipo.expected_return_pct > 0 ? "+" : ""}${Number(ipo.expected_return_pct ?? 0).toFixed(1)}%`
              : "—"}
          </span>
        </div>
      </div>

      {/* GMP banner */}
      {ipo.gmp_percentage !== null && (
        <div className={`px-5 py-2 text-xs font-medium flex items-center justify-between ${
          ipo.gmp_percentage >= 20
            ? "bg-emerald-600 text-white"
            : ipo.gmp_percentage >= 5
            ? "bg-blue-50 text-blue-800"
            : "bg-gray-50 text-gray-600"
        }`}>
          <span>GMP</span>
          <span>
            ₹{ipo.gmp_value ?? "—"} &nbsp;|&nbsp; +{Number(ipo.gmp_percentage).toFixed(1)}%
          </span>
        </div>
      )}

      {/* Tabs */}
      {!compact && (
        <>
          <div className="flex border-b border-gray-100 px-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                  tab === t
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-400 hover:text-gray-600"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="px-5 py-4">
            {tab === "Overview" && (
              <div className="grid grid-cols-2 gap-2">
                <DimensionPill
                  label="Total Subscription"
                  value={ipo.total_subscription !== null ? `${Number(ipo.total_subscription ?? 0).toFixed(1)}x` : null}
                  isGood={(ipo.total_subscription ?? 0) >= 10}
                />
                <DimensionPill
                  label="GMP"
                  value={ipo.gmp_percentage !== null ? `+${Number(ipo.gmp_percentage ?? 0).toFixed(1)}%` : null}
                  isGood={(ipo.gmp_percentage ?? 0) >= 10}
                />
                <DimensionPill
                  label="Anchor"
                  value={ipo.anchor_classification}
                  isGood={ipo.anchor_classification === "STRONG"}
                />
                <DimensionPill
                  label="P/E vs Peers"
                  value={peVsPeers !== null ? `${Number(peVsPeers) > 0 ? "+" : ""}${peVsPeers}%` : null}
                  isGood={peVsPeers !== null && Number(peVsPeers) <= 0}
                  goodThreshold={peVsPeers !== null && Number(peVsPeers) <= 0 ? "Below sector avg" : "Above sector avg"}
                />
              </div>
            )}

            {tab === "Subscription" && (
              <div className="space-y-2">
                <MetricRow label="QIB"    value={Number(ipo.qib_subscription ?? 0).toFixed(2)}    suffix="x" />
                <MetricRow label="NII"    value={Number(ipo.nii_subscription ?? 0).toFixed(2)}    suffix="x" />
                <MetricRow label="Retail" value={Number(ipo.retail_subscription ?? 0).toFixed(2)} suffix="x" />
                <MetricRow label="Total"  value={Number(ipo.total_subscription ?? 0).toFixed(2)}  suffix="x" />
              </div>
            )}

            {tab === "Financials" && (
              <div className="space-y-2">
                <MetricRow label="Revenue Growth (3yr)" value={Number(ipo.revenue_growth_3yr ?? 0).toFixed(1)} suffix="%" />
                <MetricRow label="PAT Growth (3yr)"     value={Number(ipo.pat_growth_3yr ?? 0).toFixed(1)}     suffix="%" />
                <MetricRow label="P/E Ratio (issue)"    value={Number(ipo.pe_ratio ?? 0).toFixed(1)}           suffix="x" />
                <MetricRow label="Sector P/E (median)"  value={Number(ipo.sector_pe_median ?? 0).toFixed(1)}   suffix="x" />
                {peVsPeers && (
                  <div className={`text-xs py-1.5 px-2 rounded-lg ${
                    Number(peVsPeers) <= 0 ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
                  }`}>
                    Priced {Number(peVsPeers) <= 0 ? "below" : "above"} sector by{" "}
                    {Math.abs(Number(peVsPeers)).toFixed(1)}%
                  </div>
                )}
              </div>
            )}

            {tab === "Anchor" && (
              <div className="space-y-2">
                <MetricRow label="Classification" value={ipo.anchor_classification} />
                <MetricRow label="Anchor Count"   value={ipo.anchor_investor_count} />
                <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                  STRONG = 3+ Tier-1 institutions (FIIs / large domestic MFs). 
                  MEDIUM = 1-2 Tier-1 or 10+ anchors. WEAK = below threshold.
                </p>
              </div>
            )}

            {tab === "Structure" && (
              <div className="space-y-2">
                <MetricRow label="Issue Size"           value={ipo.issue_size_cr ? `₹${ipo.issue_size_cr.toLocaleString("en-IN")} Cr` : null} />
                <MetricRow label="OFS %"                value={Number(ipo.ofs_percentage ?? 0).toFixed(1)} suffix="%" />
                <MetricRow label="Promoter Post-IPO"    value={Number(ipo.promoter_holding_post ?? 0).toFixed(1)} suffix="%" />
                <MetricRow label="Exchange"             value={ipo.listing_exchange} />
                <MetricRow label="Open"  value={ipo.issue_open_date?.substring(0,10)} />
                <MetricRow label="Close" value={ipo.issue_close_date?.substring(0,10)} />
                <MetricRow label="Listing" value={ipo.listing_date?.substring(0,10)} />
              </div>
            )}
          </div>
        </>
      )}

      {/* Similar IPOs */}
      {ipo.similar_ipos && ipo.similar_ipos.length > 0 && (
        <div className="px-5 pb-4 border-t border-gray-50">
          <p className="text-xs text-gray-400 mt-3 mb-1.5">Similar past IPOs (cosine match):</p>
          <div className="flex flex-wrap gap-1.5">
            {ipo.similar_ipos.map((name) => (
              <span
                key={name}
                className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full border border-blue-100"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
