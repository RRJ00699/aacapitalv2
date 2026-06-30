"use client";
// app/dashboard/ipo/IPOCommandCenterClient.tsx
// Command center shell — honest signal model. Filters/sorts on the VALIDATED edge
// (gap_bucket) and real backfilled columns, not the disproven LQI verdict.

import { useState, useMemo } from "react";
import IpoSignalCard, { signalFor } from "@/components/ipo/IpoSignalCard";
import type { IPORow, Signal } from "@/components/ipo/IpoSignalCard";

interface Props {
  ipos: IPORow[];
  stats: Record<string, unknown>;
}

const STATUS_OPTIONS = [
  { value: "ALL", label: "All" },
  { value: "OPEN", label: "Open" },
  { value: "LISTING_PENDING", label: "Listing Soon" },
  { value: "ALLOTMENT_PENDING", label: "Allotment" },
  { value: "CLOSED", label: "Closed" },
  { value: "LISTED", label: "Listed" },
];

// The validated edge, surfaced as the primary filter (replaces disproven conviction).
const GAP_OPTIONS = [
  { value: "ALL", label: "All" },
  { value: "MID", label: "Playable (MID)", css: "bg-emerald-600 text-white" },
  { value: "LOW", label: "Flat/Discount (LOW)", css: "bg-amber-50 text-amber-800 border border-amber-200" },
  { value: "HIGH", label: "Trap risk (HIGH)", css: "bg-red-50 text-red-800 border border-red-200" },
  { value: "PRE", label: "Pre-listing", css: "bg-blue-50 text-blue-800 border border-blue-200" },
];

const TONE_CSS: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
  blue: "bg-blue-50 text-blue-700",
  gray: "bg-gray-100 text-gray-600",
};

type ViewMode = "grid" | "list";
type SortKey = "lqi_score" | "total_subscription" | "listing_gap_pct" | "listing_date";

const num = (v: unknown): number | null => {
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};

export default function IPOCommandCenterClient({ ipos, stats }: Props) {
  const [status, setStatus] = useState("ALL");
  const [gap, setGap] = useState("ALL");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("listing_date");
  const [view, setView] = useState<ViewMode>("grid");
  const [selected, setSelected] = useState<IPORow | null>(null);

  const filtered = useMemo(() => {
    return ipos
      .filter((ipo) => {
        if (status !== "ALL" && ipo.ipo_status !== status) return false;
        if (gap !== "ALL") {
          const listed = ipo.listing_open != null;
          if (gap === "PRE" && listed) return false;
          if (gap !== "PRE" && (!listed || (ipo.gap_bucket ?? "").toUpperCase() !== gap)) return false;
        }
        if (search && !ipo.company_name.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => {
        if (sortKey === "listing_date") {
          return new Date(b.listing_date ?? "").getTime() - new Date(a.listing_date ?? "").getTime();
        }
        return (num(b[sortKey]) ?? -Infinity) - (num(a[sortKey]) ?? -Infinity);
      });
  }, [ipos, status, gap, search, sortKey]);

  const tiles = [
    { label: "Open Now", value: stats.open_count, color: "emerald" },
    { label: "Listing Soon", value: stats.listing_pending, color: "purple" },
    { label: "Playable (MID)", value: stats.playable_mid, color: "emerald" },
    { label: "At Floor", value: stats.at_floor, color: "amber" },
    { label: "Subscribed ≥10x", value: stats.subscribed_10x, color: "blue" },
  ];

  return (
    <div className="px-6 py-4 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">IPO Command Center</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Validated gap-bucket edge · floor/ceiling levels · {ipos.length} IPOs · research signal, not a buy call
          </p>
        </div>
        <div className="flex gap-1.5">
          {(["grid", "list"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3 py-2 rounded-lg border text-xs transition-colors ${
                view === v ? "bg-gray-900 text-white border-gray-900" : "bg-white text-gray-500 border-gray-200"
              }`}>
              {v === "grid" ? "Grid" : "List"}
            </button>
          ))}
        </div>
      </div>

      {/* Honest summary tiles */}
      <div className="grid grid-cols-5 gap-3">
        {tiles.map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
            <p className="text-xs text-gray-400 mb-0.5">{s.label}</p>
            <p className={`text-2xl font-semibold text-${s.color}-600`}>{String(s.value ?? "—")}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-white border border-gray-100 rounded-xl px-4 py-3 shadow-sm space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <input type="text" placeholder="Search company…" value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-44" />
          <div className="flex gap-1 flex-wrap">
            {STATUS_OPTIONS.map((o) => (
              <button key={o.value} onClick={() => setStatus(o.value)}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                  status === o.value ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-500 border-gray-200 hover:border-blue-300"
                }`}>
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-gray-400">Signal:</span>
          {GAP_OPTIONS.map((o) => (
            <button key={o.value} onClick={() => setGap(o.value)}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                gap === o.value ? (o.css ?? "bg-gray-700 text-white") : "bg-white text-gray-500 border-gray-200 hover:border-gray-400"
              }`}>
              {o.label}
            </button>
          ))}

          <div className="ml-auto flex gap-1 items-center">
            <span className="text-xs text-gray-400">Sort:</span>
            {([
              { k: "listing_date" as SortKey, l: "Listing Date" },
              { k: "listing_gap_pct" as SortKey, l: "Gap %" },
              { k: "total_subscription" as SortKey, l: "Subscription" },
              { k: "lqi_score" as SortKey, l: "LQI" },
            ]).map(({ k, l }) => (
              <button key={k} onClick={() => setSortKey(k)}
                className={`px-2 py-1 text-xs rounded-md border ${
                  sortKey === k ? "bg-gray-800 text-white border-gray-800" : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"
                }`}>
                {l}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-gray-400">Showing {filtered.length} of {ipos.length} IPOs</p>
      </div>

      {/* Content */}
      {view === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((ipo) => <IpoSignalCard key={ipo.id} ipo={ipo} />)}
          {filtered.length === 0 && <div className="col-span-3 text-center py-16 text-gray-400">No IPOs match your filters</div>}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {["Company", "Status", "Signal", "Gap %", "Sub.", "P/E vs Peer", "RoE", "Level", "Listing"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((ipo) => {
                  const sig: Signal = signalFor(ipo);
                  const g = num(ipo.listing_gap_pct);
                  const sub = num(ipo.total_subscription);
                  const pe = num(ipo.ipo_pe), peer = num(ipo.peer_median_pe);
                  const peVsPeer = pe != null && peer != null && peer !== 0 ? (pe / peer - 1) * 100 : null;
                  const roe = num(ipo.roe);
                  return (
                    <tr key={ipo.id} className="hover:bg-blue-50/30 cursor-pointer transition-colors"
                      onClick={() => setSelected(ipo === selected ? null : ipo)}>
                      <td className="px-4 py-3 font-medium text-gray-900 max-w-[180px] truncate">
                        {ipo.company_name}
                        {ipo.is_sme && <span className="ml-1 text-[9px] bg-purple-100 text-purple-700 px-1 rounded">SME</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{ipo.ipo_status?.replace(/_/g, " ") ?? "—"}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${TONE_CSS[sig.tone]}`}>{sig.tier}</span>
                      </td>
                      <td className={`px-4 py-3 tabular-nums ${(g ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                        {g != null ? `${g > 0 ? "+" : ""}${g.toFixed(1)}%` : "—"}
                      </td>
                      <td className="px-4 py-3 tabular-nums">{sub != null ? `${sub.toFixed(1)}x` : "—"}</td>
                      <td className={`px-4 py-3 tabular-nums ${peVsPeer != null ? (peVsPeer <= 0 ? "text-emerald-600" : "text-red-600") : ""}`}>
                        {peVsPeer != null ? `${peVsPeer > 0 ? "+" : ""}${peVsPeer.toFixed(0)}%` : "—"}
                      </td>
                      <td className={`px-4 py-3 tabular-nums ${roe != null ? (roe >= 0 ? "" : "text-red-600") : ""}`}>
                        {roe != null ? `${roe.toFixed(1)}%` : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 max-w-[120px] truncate">{ipo.level_verdict ?? "—"}</td>
                      <td className="px-4 py-3 text-xs text-gray-400">{ipo.listing_date?.substring(0, 10) ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {selected && (
            <div className="border-t border-blue-100 bg-blue-50/30 p-4">
              <IpoSignalCard ipo={selected} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
