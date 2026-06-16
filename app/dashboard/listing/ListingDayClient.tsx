"use client";
// app/dashboard/listing/ListingDayClient.tsx

import { useState } from "react";
import type { ListingSignal } from "./page";

interface Props {
  todayListings: ListingSignal[];
  recentListings: ListingSignal[];
  stats: Record<string, unknown>;
}

function GainBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-gray-300 text-xs">—</span>;
  const pos = pct >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 font-bold tabular-nums text-sm ${
      pct >= 20 ? "text-emerald-700"
      : pct >= 10 ? "text-emerald-600"
      : pct >= 0  ? "text-blue-600"
      : pct >= -10? "text-orange-600"
      : "text-red-600"
    }`}>
      {pos ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

function VWAPSignal({ price, vwap, aboveVwap }: {
  price: number | null; vwap: number | null; aboveVwap: boolean | null;
}) {
  if (!price || !vwap) return <span className="text-gray-300 text-xs">No live data</span>;
  return (
    <div>
      <div className={`text-xs font-semibold px-2 py-0.5 rounded-full inline-block ${
        aboveVwap ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
      }`}>
        {aboveVwap ? "Above VWAP" : "Below VWAP"}
      </div>
      <div className="text-[10px] text-gray-400 mt-0.5">
        LTP ₹{Number(price).toFixed(1)} · VWAP ₹{Number(vwap).toFixed(1)}
      </div>
    </div>
  );
}

function OrderImbalance({ buyQty, sellQty }: { buyQty: number | null; sellQty: number | null }) {
  if (!buyQty && !sellQty) return <span className="text-gray-300 text-xs">—</span>;
  const total = (buyQty ?? 0) + (sellQty ?? 0);
  const buyPct = total > 0 ? ((buyQty ?? 0) / total) * 100 : 50;

  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden">
        <div
          className="bg-emerald-500 transition-all"
          style={{ width: `${buyPct}%` }}
        />
        <div className="bg-red-400 flex-1" />
      </div>
      <div className="flex justify-between text-[10px] mt-0.5">
        <span className="text-emerald-600">B {Number(buyPct).toFixed(0)}%</span>
        <span className="text-red-600">S {Number(100 - buyPct).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function ListingCard({ ipo }: { ipo: ListingSignal }) {
  const currentGain = ipo.last_price && ipo.issue_price
    ? ((ipo.last_price - ipo.issue_price) / ipo.issue_price) * 100
    : ipo.listing_gap_pct;

  const subscriptions = [
    { label: "QIB",   value: ipo.qib_subscription },
    { label: "Total", value: ipo.total_subscription },
  ];

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Top bar — gain */}
      <div className={`px-4 py-2 flex items-center justify-between ${
        (currentGain ?? 0) >= 20 ? "bg-emerald-600"
        : (currentGain ?? 0) >= 5  ? "bg-emerald-50"
        : (currentGain ?? 0) >= 0  ? "bg-blue-50"
        : "bg-red-50"
      }`}>
        <span className={`text-xs font-medium ${
          (currentGain ?? 0) >= 5 ? "text-white" : "text-gray-600"
        }`}>
          {ipo.company_name}
          {ipo.nse_symbol && (
            <span className="ml-1.5 opacity-70">· {ipo.nse_symbol}</span>
          )}
        </span>
        <GainBadge pct={currentGain ?? null} />
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Price row */}
        <div className="flex items-baseline gap-4">
          <div>
            <p className="text-[10px] text-gray-400">Issue Price</p>
            <p className="text-base font-semibold text-gray-800">
              {ipo.issue_price ? `₹${ipo.issue_price}` : "—"}
            </p>
          </div>
          {ipo.listing_price && (
            <div>
              <p className="text-[10px] text-gray-400">Listed At</p>
              <p className="text-base font-semibold text-gray-800">₹{ipo.listing_price}</p>
            </div>
          )}
          {ipo.last_price && (
            <div>
              <p className="text-[10px] text-gray-400">LTP</p>
              <p className="text-base font-semibold text-blue-700">₹{Number(ipo.last_price).toFixed(1)}</p>
            </div>
          )}
          <div className="ml-auto text-right">
            <p className="text-[10px] text-gray-400">LQI</p>
            <p className="text-base font-bold text-blue-600">
              {ipo.lqi_score !== null ? Math.round(ipo.lqi_score) : "—"}
            </p>
          </div>
        </div>

        {/* VWAP signal */}
        <VWAPSignal
          price={ipo.last_price}
          vwap={ipo.vwap}
          aboveVwap={ipo.above_vwap}
        />

        {/* Order imbalance */}
        <div>
          <p className="text-[10px] text-gray-400 mb-1">Order Imbalance</p>
          <OrderImbalance buyQty={ipo.buy_qty} sellQty={ipo.sell_qty} />
        </div>

        {/* Sub + GMP */}
        <div className="flex gap-3 text-xs border-t border-gray-50 pt-2">
          {subscriptions.map((s) => s.value !== null && (
            <div key={s.label}>
              <span className="text-gray-400">{s.label} </span>
              <span className="font-medium text-gray-700">{Number(s.value).toFixed(1)}x</span>
            </div>
          ))}
          {ipo.gmp_percentage !== null && (
            <div>
              <span className="text-gray-400">GMP </span>
              <span className="font-medium text-emerald-700">+{Number(ipo.gmp_percentage).toFixed(1)}%</span>
            </div>
          )}
          <div className="ml-auto">
            {ipo.conviction && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                ipo.conviction === "STRONG_BUY" ? "bg-emerald-600 text-white" :
                ipo.conviction === "BUY"        ? "bg-blue-600 text-white" :
                "bg-gray-100 text-gray-600"
              }`}>
                {ipo.conviction.replace(/_/g, " ")}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function RecentListingRow({ ipo }: { ipo: ListingSignal }) {
  return (
    <tr className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 font-medium text-gray-900 text-sm">{ipo.company_name}</td>
      <td className="px-4 py-3 text-xs text-gray-400">{ipo.listing_date?.substring(0,10)}</td>
      <td className="px-4 py-3 text-sm">
        {ipo.issue_price ? `₹${ipo.issue_price}` : "—"}
      </td>
      <td className="px-4 py-3 text-sm">
        {ipo.listing_price ? `₹${ipo.listing_price}` : "—"}
      </td>
      <td className="px-4 py-3">
        <GainBadge pct={ipo.listing_gap_pct} />
      </td>
      <td className="px-4 py-3 text-xs text-gray-500 tabular-nums">
        {ipo.total_subscription !== null ? `${Number(ipo.total_subscription).toFixed(1)}x` : "—"}
      </td>
      <td className="px-4 py-3 text-xs tabular-nums text-emerald-700">
        {ipo.gmp_percentage !== null ? `+${Number(ipo.gmp_percentage).toFixed(1)}%` : "—"}
      </td>
      <td className="px-4 py-3 text-xs font-bold text-blue-600 tabular-nums">
        {ipo.lqi_score !== null ? Math.round(ipo.lqi_score) : "—"}
      </td>
    </tr>
  );
}

export default function ListingDayClient({ todayListings, recentListings, stats }: Props) {
  const [tab, setTab] = useState<"today" | "recent">("today");

  return (
    <div className="px-6 py-4 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Listing Day Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Live OI · VWAP signals · Order imbalance · 90-day listing track record
          </p>
        </div>
        {todayListings.length > 0 && (
          <span className="flex items-center gap-1.5 text-xs bg-emerald-100 text-emerald-800 px-3 py-1.5 rounded-full font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {todayListings.length} listing{todayListings.length !== 1 ? "s" : ""} today
          </span>
        )}
      </div>

      {/* 90-day stats */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: "Total Listed (90d)", value: stats.total_listed },
          { label: "Positive",           value: stats.positive_listings, color: "emerald" },
          { label: "Gain ≥ 10%",         value: stats.gain_10plus,       color: "blue" },
          { label: "Negative",           value: stats.negative_listings,  color: "red" },
          { label: "Avg Gain",           value: `${stats.avg_gain}%`,     color: Number(stats.avg_gain) >= 0 ? "emerald" : "red" },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
            <p className="text-xs text-gray-400 mb-0.5">{s.label}</p>
            <p className={`text-xl font-semibold text-${s.color ?? "gray"}-600`}>
              {String(s.value ?? "—")}
            </p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-100">
        {(["today", "recent"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-400 hover:text-gray-600"
            }`}
          >
            {t === "today" ? "Today's Listings" : "Recent 14 Days"}
            {t === "today" && todayListings.length > 0 && (
              <span className="ml-1.5 text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full">
                {todayListings.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "today" ? (
        todayListings.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {todayListings.map((ipo) => (
              <ListingCard key={ipo.id} ipo={ipo} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 text-gray-400">
            <p className="text-4xl mb-3">📅</p>
            <p className="text-base font-medium text-gray-500">No IPOs listing today</p>
            <p className="text-sm text-gray-400 mt-1">
              Signals will appear here automatically when IPOs list.
            </p>
          </div>
        )
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {["Company", "Listing Date", "Issue Price", "Listed At", "Listing Gain", "Subscription", "GMP", "LQI"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentListings.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-12 text-gray-400 text-sm">
                      No listings in the last 14 days
                    </td>
                  </tr>
                ) : (
                  recentListings.map((ipo) => (
                    <RecentListingRow key={ipo.id} ipo={ipo} />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Live refresh note */}
      <p className="text-xs text-gray-400 text-center">
        Live OI + VWAP refreshes every 60s on listing day via{" "}
        <code className="bg-gray-100 px-1 rounded">kite-sync-ipos.py --listing</code>
      </p>
    </div>
  );
}
