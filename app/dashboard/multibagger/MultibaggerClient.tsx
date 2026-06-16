"use client";
// app/dashboard/multibagger/MultibaggerClient.tsx

import { useState, useMemo } from "react";
import type { TechnicalSignal } from "./page";

interface Props {
  signals: TechnicalSignal[];
  stats: {
    total: number;
    strong: number;
    uniqueStocks: number;
    latestDate: string;
  };
}

const CONVICTION_ORDER: Record<string, number> = {
  ACCUMULATE: 0,
  WATCH: 1,
  AVOID: 2,
};

const CONVICTION_STYLE: Record<string, string> = {
  ACCUMULATE: "bg-emerald-50 text-emerald-800 border border-emerald-200",
  WATCH:      "bg-amber-50 text-amber-800 border border-amber-200",
  AVOID:      "bg-red-50 text-red-700 border border-red-200",
};

function CriteriaBar({ met, total = 5 }: { met: number | null; total?: number }) {
  const filled = met ?? 0;
  return (
    <div className="flex gap-[3px] items-center">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={`inline-block w-[10px] h-[10px] rounded-full ${
            i < filled ? "bg-blue-500" : "bg-gray-200"
          }`}
        />
      ))}
      <span className="ml-1 text-xs text-gray-500">{filled}/{total}</span>
    </div>
  );
}

function Tick({ ok }: { ok: boolean | null }) {
  if (ok === null || ok === undefined)
    return <span className="text-gray-300 text-xs">—</span>;
  return ok ? (
    <span className="text-emerald-600 font-bold">✓</span>
  ) : (
    <span className="text-gray-300">✗</span>
  );
}

export default function MultibaggerClient({ signals, stats }: Props) {
  const [filterConviction, setFilterConviction] = useState<string>("ALL");
  const [filterAllMet,     setFilterAllMet]     = useState<boolean>(false);
  const [search,           setSearch]            = useState<string>("");
  const [sortKey,          setSortKey]           = useState<"mb_score" | "criteria_met" | "signal_date">("mb_score");

  const filtered = useMemo(() => {
    return signals
      .filter((s) => {
        if (filterAllMet && !s.all_criteria_met) return false;
        if (filterConviction !== "ALL" && s.conviction !== filterConviction) return false;
        if (search && !s.symbol.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => {
        if (sortKey === "mb_score")
          return (b.mb_score ?? -1) - (a.mb_score ?? -1);
        if (sortKey === "criteria_met")
          return (b.criteria_met ?? -1) - (a.criteria_met ?? -1);
        // signal_date
        return new Date(b.signal_date).getTime() - new Date(a.signal_date).getTime();
      });
  }, [signals, filterConviction, filterAllMet, search, sortKey]);

  return (
    <div className="px-6 py-4 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Multibagger Discovery</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            All 5 criteria must align simultaneously — Monthly RSI, Weekly EMA30,
            Weekly Heikin Ashi, Daily NR7, Daily Inside Bar
          </p>
        </div>
        <span className="text-xs text-gray-400 pt-1">
          Updated: {stats.latestDate ? String(stats.latestDate).substring(0, 10) : "—"}
        </span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total Signals",   value: stats.total },
          { label: "All 5 Criteria",  value: stats.strong, highlight: true },
          { label: "Unique Stocks",   value: stats.uniqueStocks },
          { label: "Showing",         value: filtered.length },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm"
          >
            <p className="text-xs text-gray-400 mb-0.5">{s.label}</p>
            <p className={`text-2xl font-semibold ${s.highlight ? "text-blue-600" : "text-gray-800"}`}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center bg-white border border-gray-100 rounded-xl px-4 py-3 shadow-sm">
        <input
          type="text"
          placeholder="Search symbol…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-40"
        />

        <div className="flex gap-1">
          {["ALL", "ACCUMULATE", "WATCH", "AVOID"].map((c) => (
            <button
              key={c}
              onClick={() => setFilterConviction(c)}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                filterConviction === c
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-600 border-gray-200 hover:border-blue-300"
              }`}
            >
              {c}
            </button>
          ))}
        </div>

        <button
          onClick={() => setFilterAllMet(!filterAllMet)}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
            filterAllMet
              ? "bg-emerald-600 text-white border-emerald-600"
              : "bg-white text-gray-600 border-gray-200 hover:border-emerald-300"
          }`}
        >
          All 5 criteria only
        </button>

        <div className="ml-auto flex gap-1 items-center">
          <span className="text-xs text-gray-400">Sort:</span>
          {(["mb_score", "criteria_met", "signal_date"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setSortKey(k)}
              className={`px-2 py-1 text-xs rounded-md border ${
                sortKey === k
                  ? "bg-gray-800 text-white border-gray-800"
                  : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"
              }`}
            >
              {k === "mb_score" ? "Score" : k === "criteria_met" ? "Criteria" : "Date"}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Symbol</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Score</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Criteria</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide w-10" title="Monthly RSI">RSI</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide w-10" title="Above Weekly EMA30">EMA</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide w-10" title="Weekly Heikin Ashi Bullish">HA</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide w-10" title="Daily NR7">NR7</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide w-10" title="Daily Inside Bar">IB</th>
                <th className="text-center px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Conviction</th>
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">DTW Match</th>
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={11} className="text-center py-12 text-gray-400 text-sm">
                    No signals match your filters
                  </td>
                </tr>
              ) : (
                filtered.map((s) => (
                  <tr
                    key={s.id}
                    className={`hover:bg-gray-50 transition-colors ${
                      s.all_criteria_met ? "bg-emerald-50/30" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {s.all_criteria_met && (
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        )}
                        <span className="font-semibold text-gray-900">{s.symbol}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span
                        className={`inline-block font-bold text-base tabular-nums ${
                          (s.mb_score ?? 0) >= 80
                            ? "text-blue-600"
                            : (s.mb_score ?? 0) >= 60
                            ? "text-gray-700"
                            : "text-gray-400"
                        }`}
                      >
                        {s.mb_score ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <CriteriaBar met={s.criteria_met} />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <Tick ok={s.monthly_rsi_ok} />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <Tick ok={s.price_above_ema30} />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <Tick ok={s.weekly_ha_bullish} />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <Tick ok={s.daily_nr7} />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <Tick ok={s.daily_inside_bar} />
                    </td>
                    <td className="px-3 py-3 text-center">
                      {s.conviction ? (
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            CONVICTION_STYLE[s.conviction] ?? "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {s.conviction}
                        </span>
                      ) : (
                        <span className="text-gray-300 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-xs text-gray-500">
                      {s.dtw_pattern_match
                        ? `${s.dtw_pattern_match} (${s.dtw_similarity_pct?.toFixed(0)}%)`
                        : "—"}
                    </td>
                    <td className="px-3 py-3 text-xs text-gray-400">
                      {s.signal_date ? String(s.signal_date).substring(0, 10) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {filtered.length > 0 && (
          <div className="border-t border-gray-100 px-4 py-2 text-xs text-gray-400 flex justify-between">
            <span>Showing {filtered.length} of {signals.length} signals</span>
            <span>🟢 Green row = all 5 criteria met</span>
          </div>
        )}
      </div>
    </div>
  );
}
