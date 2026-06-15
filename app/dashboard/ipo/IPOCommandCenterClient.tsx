"use client";
// app/dashboard/ipo/IPOCommandCenterClient.tsx

import { useState, useMemo } from "react";
import IPOIntelligenceCard from "@/components/ipo/IPOIntelligenceCard";
import type { IPOIntelligence } from "@/components/ipo/IPOIntelligenceCard";

interface Props {
  ipos: IPOIntelligence[];
  stats: Record<string, unknown>;
}

const STATUS_OPTIONS = [
  { value: "ALL",              label: "All" },
  { value: "OPEN",             label: "Open" },
  { value: "LISTING_PENDING",  label: "Listing Soon" },
  { value: "ALLOTMENT_PENDING",label: "Allotment" },
  { value: "CLOSED",           label: "Closed" },
  { value: "LISTED",           label: "Listed" },
];

const CONVICTION_OPTIONS = [
  { value: "ALL",          label: "All" },
  { value: "STRONG_BUY",  label: "Strong Buy" },
  { value: "BUY",         label: "Buy" },
  { value: "NEUTRAL",     label: "Neutral" },
  { value: "AVOID",       label: "Avoid" },
  { value: "STRONG_AVOID",label: "Strong Avoid" },
];

const CONVICTION_COLOR: Record<string, string> = {
  STRONG_BUY:  "bg-emerald-600 text-white",
  BUY:         "bg-blue-600 text-white",
  NEUTRAL:     "bg-amber-50 text-amber-800 border border-amber-200",
  AVOID:       "bg-orange-50 text-orange-800 border border-orange-200",
  STRONG_AVOID:"bg-red-50 text-red-800 border border-red-200",
};

type ViewMode = "grid" | "list";
type SortKey  = "lqi_score" | "total_subscription" | "gmp_percentage" | "listing_date";

export default function IPOCommandCenterClient({ ipos, stats }: Props) {
  const [status,     setStatus]     = useState("ALL");
  const [conviction, setConviction] = useState("ALL");
  const [search,     setSearch]     = useState("");
  const [sortKey,    setSortKey]    = useState<SortKey>("lqi_score");
  const [view,       setView]       = useState<ViewMode>("grid");
  const [selected,   setSelected]   = useState<IPOIntelligence | null>(null);

  const filtered = useMemo(() => {
    return ipos
      .filter((ipo) => {
        if (status !== "ALL" && ipo.ipo_status !== status) return false;
        if (conviction !== "ALL" && ipo.conviction !== conviction) return false;
        if (search && !ipo.company_name.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => {
        const av = (a[sortKey] as number | null) ?? -Infinity;
        const bv = (b[sortKey] as number | null) ?? -Infinity;
        if (sortKey === "listing_date") {
          return new Date(b.listing_date ?? "").getTime() - new Date(a.listing_date ?? "").getTime();
        }
        return bv - av;
      });
  }, [ipos, status, conviction, search, sortKey]);

  return (
    <div className="px-6 py-4 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">IPO Command Center</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            150-pt LQI · Bayesian probability · Cosine similarity · {ipos.length} IPOs
          </p>
        </div>
        <div className="flex gap-1.5">
          {(["grid","list"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`p-2 rounded-lg border text-xs transition-colors ${
                view === v ? "bg-gray-900 text-white border-gray-900" : "bg-white text-gray-500 border-gray-200"
              }`}
            >
              {v === "grid" ? (
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                  <rect x="1" y="1" width="6" height="6" rx="1"/>
                  <rect x="9" y="1" width="6" height="6" rx="1"/>
                  <rect x="1" y="9" width="6" height="6" rx="1"/>
                  <rect x="9" y="9" width="6" height="6" rx="1"/>
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 16 16">
                  <line x1="1" y1="4"  x2="15" y2="4" />
                  <line x1="1" y1="8"  x2="15" y2="8" />
                  <line x1="1" y1="12" x2="15" y2="12" />
                </svg>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: "Open Now",      value: stats.open_count,      highlight: "emerald" },
          { label: "Listing Soon",  value: stats.listing_pending, highlight: "purple" },
          { label: "Buy Signals",   value: stats.buy_signals,     highlight: "blue" },
          { label: "LQI ≥ 70",      value: stats.high_lqi,        highlight: "blue" },
          { label: "GMP ≥ 20%",     value: stats.high_gmp,        highlight: "green" },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm"
          >
            <p className="text-xs text-gray-400 mb-0.5">{s.label}</p>
            <p className={`text-2xl font-semibold text-${s.highlight}-600`}>
              {String(s.value ?? "—")}
            </p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-white border border-gray-100 rounded-xl px-4 py-3 shadow-sm space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <input
            type="text"
            placeholder="Search company…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-44"
          />

          <div className="flex gap-1 flex-wrap">
            {STATUS_OPTIONS.map((o) => (
              <button
                key={o.value}
                onClick={() => setStatus(o.value)}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                  status === o.value
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-gray-500 border-gray-200 hover:border-blue-300"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-gray-400">Conviction:</span>
          {CONVICTION_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setConviction(o.value)}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                conviction === o.value
                  ? CONVICTION_COLOR[o.value] ?? "bg-gray-700 text-white"
                  : "bg-white text-gray-500 border-gray-200 hover:border-gray-400"
              }`}
            >
              {o.label}
            </button>
          ))}

          <div className="ml-auto flex gap-1 items-center">
            <span className="text-xs text-gray-400">Sort:</span>
            {([
              { k: "lqi_score" as SortKey,         l: "LQI" },
              { k: "total_subscription" as SortKey, l: "Subscription" },
              { k: "gmp_percentage" as SortKey,     l: "GMP" },
              { k: "listing_date" as SortKey,       l: "Listing Date" },
            ]).map(({ k, l }) => (
              <button
                key={k}
                onClick={() => setSortKey(k)}
                className={`px-2 py-1 text-xs rounded-md border ${
                  sortKey === k
                    ? "bg-gray-800 text-white border-gray-800"
                    : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        <p className="text-xs text-gray-400">
          Showing {filtered.length} of {ipos.length} IPOs
        </p>
      </div>

      {/* Content */}
      {view === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((ipo) => (
            <IPOIntelligenceCard key={ipo.id} ipo={ipo} />
          ))}
          {filtered.length === 0 && (
            <div className="col-span-3 text-center py-16 text-gray-400">
              No IPOs match your filters
            </div>
          )}
        </div>
      ) : (
        /* List / table view */
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {["Company", "Status", "LQI", "Conviction", "P(>10%)", "P(Loss)", "Exp. Ret.", "GMP", "Sub.", "Listing"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((ipo) => (
                  <tr
                    key={ipo.id}
                    className="hover:bg-blue-50/30 cursor-pointer transition-colors"
                    onClick={() => setSelected(ipo === selected ? null : ipo)}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 max-w-[180px] truncate">
                      {ipo.company_name}
                      {ipo.is_sme && <span className="ml-1 text-[9px] bg-purple-100 text-purple-700 px-1 rounded">SME</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                        {ipo.ipo_status?.replace(/_/g, " ") ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-bold text-blue-600 tabular-nums">
                      {ipo.lqi_score !== null ? Math.round(ipo.lqi_score) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {ipo.conviction && (
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          CONVICTION_COLOR[ipo.conviction] ?? "bg-gray-100 text-gray-600"
                        }`}>
                          {ipo.conviction.replace(/_/g, " ")}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-blue-600 tabular-nums">
                      {ipo.p_profit_10pct !== null ? `${(ipo.p_profit_10pct * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td className="px-4 py-3 text-red-600 tabular-nums">
                      {ipo.p_loss !== null ? `${(ipo.p_loss * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td className={`px-4 py-3 font-medium tabular-nums ${
                      (ipo.expected_return_pct ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
                    }`}>
                      {ipo.expected_return_pct !== null
                        ? `${ipo.expected_return_pct > 0 ? "+" : ""}${ipo.expected_return_pct.toFixed(1)}%`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {ipo.gmp_percentage !== null ? `+${ipo.gmp_percentage.toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {ipo.total_subscription !== null ? `${ipo.total_subscription.toFixed(1)}x` : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">
                      {ipo.listing_date?.substring(0, 10) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Inline card when row selected */}
          {selected && (
            <div className="border-t border-blue-100 bg-blue-50/30 p-4">
              <IPOIntelligenceCard ipo={selected} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
