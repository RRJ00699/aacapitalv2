"use client";
// components/ipo/IpoSignalCard.tsx
// HONEST IPO card — leads with the VALIDATED edge, not a disproven buy verdict.
//
// Validated edge (gap_bucket = (listing_open - issue)/issue):
//   LOW  (<10%)   steady — ~70% gave a green exit ≤10 sessions (+4% median). No pop to chase.
//   MID  (10-30%) the playable zone — ~81% green exit ≤10d (+10% median), peaks ~session 18.
//   HIGH (>30%)   pop-and-fade — ~61% green exit ≤10d but peaks ~session 10 then fades. Exit fast.
// GMP is non-predictive → shown as muted context, never as a buy call.
// LQI is a quality input, not a verdict → small chip, demoted.
// "Research signal, not a buy call."

import { useState } from "react";
import { signalFor, BASE_RATES, bucketOf, type Tone, type Signal } from "@/lib/ipoSignal";
export { signalFor };
export type { Signal };

const C = {
  green: "#15803D", greenBg: "#F0FDF4", greenBd: "#BBF7D0",
  amber: "#B45309", amberBg: "#FFFBEB", amberBd: "#FDE68A",
  red:   "#B91C1C", redBg:   "#FEF2F2", redBd:   "#FECACA",
  blue:  "#1D4ED8", blueBg:  "#EFF6FF", blueBd:  "#BFDBFE",
  gray:  "#6B7280", grayBg:  "#F9FAFB", grayBd:  "#E5E7EB",
  text:  "#111827", textSub: "#6B7280", surface: "#FFFFFF",
};

export interface IPORow {
  id: number;
  company_name: string;
  symbol: string | null;
  is_sme: boolean | null;
  issue_category: string | null;
  ipo_status: string | null;

  issue_price: number | null;
  issue_size_cr: number | null;
  issue_open_date: string | null;
  issue_close_date: string | null;
  listing_date: string | null;

  // validated signal inputs
  listing_open: number | null;
  gap_bucket: string | null;           // LOW | MID | HIGH
  listing_gap_pct: number | null;
  return_current: number | null;
  floor_price: number | null;
  ceiling_price: number | null;
  level_verdict: string | null;        // e.g. AT FLOOR / DEFENDING / BROKE FLOOR
  tp1_exit_note: string | null;

  // demand
  total_subscription: number | null;
  qib_subscription: number | null;
  retail_subscription: number | null;
  nii_subscription: number | null;

  // fundamentals
  ipo_pe: number | null;
  peer_median_pe: number | null;
  roe: number | null;
  pat_cr: number | null;
  is_profitable: boolean | null;
  valuation_premium: string | null;
  promoter_holding_post: number | null;

  // anchors / BRLM
  anchor_count: number | null;
  anchor_quality: string | null;
  anchor_total_cr: number | null;
  brlm_names: string | null;
  brlm_tier: string | null;

  // context (not a signal)
  regime_at_listing: string | null;
  gmp_pct: number | null;
  gmp_value: number | null;

  // quality score (demoted)
  lqi_score: number | null;
}

const num = (v: unknown): number | null => {
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};
// ── signal model moved to lib/ipoSignal.ts (single source of truth) ──────────────

const toneCss = (t: Tone) => ({
  green: { c: C.green, bg: C.greenBg, bd: C.greenBd },
  amber: { c: C.amber, bg: C.amberBg, bd: C.amberBd },
  red:   { c: C.red,   bg: C.redBg,   bd: C.redBd },
  blue:  { c: C.blue,  bg: C.blueBg,  bd: C.blueBd },
  gray:  { c: C.gray,  bg: C.grayBg,  bd: C.grayBd },
}[t]);

const STATUS_CSS: Record<string, string> = {
  OPEN: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  LISTING_PENDING: "bg-purple-50 text-purple-700 border border-purple-200",
  ALLOTMENT_PENDING: "bg-amber-50 text-amber-700 border border-amber-200",
  CLOSED: "bg-gray-100 text-gray-600",
  LISTED: "bg-blue-50 text-blue-700 border border-blue-200",
};

function Metric({ label, value, sub, good }: {
  label: string; value: string; sub?: string; good?: boolean | null;
}) {
  const col = good == null ? C.text : good ? C.green : C.red;
  return (
    <div className="px-2.5 py-2 rounded-lg" style={{ background: C.grayBg, border: `1px solid ${C.grayBd}` }}>
      <p className="text-[10px] uppercase tracking-wide" style={{ color: C.textSub }}>{label}</p>
      <p className="text-sm font-semibold tabular-nums" style={{ color: col }}>{value}</p>
      {sub && <p className="text-[10px]" style={{ color: C.textSub }}>{sub}</p>}
    </div>
  );
}

export default function IpoSignalCard({ ipo, compact = false }: { ipo: IPORow; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const sig = signalFor(ipo);
  const t = toneCss(sig.tone);

  const sub = num(ipo.total_subscription);
  const pe = num(ipo.ipo_pe);
  const peerPe = num(ipo.peer_median_pe);
  const peVsPeer = pe != null && peerPe != null && peerPe !== 0
    ? ((pe / peerPe - 1) * 100) : null;
  const roe = num(ipo.roe);
  const gap = num(ipo.listing_gap_pct);
  const floor = num(ipo.floor_price);
  const ceil = num(ipo.ceiling_price);

  return (
    <div className="rounded-2xl overflow-hidden shadow-sm" style={{ background: C.surface, border: `1px solid ${C.grayBd}` }}>
      {/* Header */}
      <div className="px-4 py-3" style={{ borderBottom: `1px solid ${C.grayBd}` }}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <h3 className="text-sm font-semibold truncate" style={{ color: C.text }}>{ipo.company_name}</h3>
              {ipo.symbol && <span className="text-[10px] font-mono px-1 rounded" style={{ background: C.grayBg, color: C.textSub }}>{ipo.symbol}</span>}
              {ipo.is_sme && <span className="text-[9px] px-1 rounded bg-purple-50 text-purple-700 border border-purple-200">SME</span>}
              {ipo.ipo_status && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${STATUS_CSS[ipo.ipo_status] ?? "bg-gray-100 text-gray-600"}`}>
                  {ipo.ipo_status.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1 text-[11px] flex-wrap" style={{ color: C.textSub }}>
              {ipo.issue_price != null && <span>₹{ipo.issue_price}</span>}
              {ipo.listing_open != null && <span>open ₹{ipo.listing_open}{gap != null && ` (${gap > 0 ? "+" : ""}${gap.toFixed(1)}%)`}</span>}
              {ipo.issue_size_cr != null && <span>₹{Number(ipo.issue_size_cr).toLocaleString("en-IN")} Cr</span>}
              {ipo.listing_date && <span>{String(ipo.listing_date).substring(0, 10)}</span>}
            </div>
          </div>
          {ipo.lqi_score != null && (
            <div className="text-right shrink-0" title="Listing-Quality Index — a quality input, not a buy verdict">
              <p className="text-lg font-bold tabular-nums" style={{ color: C.gray }}>{Math.round(Number(ipo.lqi_score))}</p>
              <p className="text-[9px]" style={{ color: C.textSub }}>LQI</p>
            </div>
          )}
        </div>
      </div>

      {/* VALIDATED SIGNAL — the lead */}
      <div className="px-4 py-2.5" style={{ background: t.bg, borderBottom: `1px solid ${t.bd}` }}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ background: t.c, color: "#fff" }}>{sig.tier}</span>
          <span className="text-xs font-semibold" style={{ color: t.c }}>{sig.headline}</span>
        </div>
        <p className="text-[11px] mt-1" style={{ color: C.text }}>{sig.detail}</p>
        {sig.bucket && (
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {([
              [`~${BASE_RATES[sig.bucket].winRate}%`, "green exit ≤10d"],
              [`+${BASE_RATES[sig.bucket].median}%`, "median"],
              [`exit ~s${BASE_RATES[sig.bucket].peakDay}`, "peak"],
              [`${BASE_RATES[sig.bucket].tail}%`, "tail risk"],
            ] as [string, string][]).map(([v, l]) => (
              <span key={l} className="text-[10px] px-1.5 py-0.5 rounded tabular-nums"
                style={{ background: "#fff", border: `1px solid ${t.bd}`, color: t.c }}>
                <b>{v}</b> <span style={{ color: C.textSub }}>{l}</span>
              </span>
            ))}
          </div>
        )}
        {ipo.level_verdict && (
          <p className="text-[11px] mt-1 font-medium" style={{ color: t.c }}>
            Level: {ipo.level_verdict}
            {floor != null && ` · floor ₹${floor}`}
            {ceil != null && ` · ceiling ₹${ceil}`}
          </p>
        )}
      </div>

      {/* Key metrics — correctly wired */}
      {!compact && (
        <div className="px-4 py-3 grid grid-cols-2 gap-2">
          <Metric label="Total Sub." value={sub != null ? `${sub.toFixed(1)}x` : "—"} good={sub != null ? sub >= 10 : null} />
          <Metric label="P/E vs Peers"
            value={peVsPeer != null ? `${peVsPeer > 0 ? "+" : ""}${peVsPeer.toFixed(0)}%` : (pe != null ? `${pe.toFixed(1)}` : "—")}
            sub={peerPe != null ? `peer ${peerPe.toFixed(1)}` : undefined}
            good={peVsPeer != null ? peVsPeer <= 0 : null} />
          <Metric label="Anchors"
            value={ipo.anchor_count != null ? `${ipo.anchor_count}` : "—"}
            sub={ipo.anchor_quality ?? (ipo.anchor_total_cr != null ? `₹${ipo.anchor_total_cr}cr` : undefined)}
            good={ipo.anchor_quality ? ipo.anchor_quality.toUpperCase().includes("STRONG") || ipo.anchor_quality.toUpperCase().includes("TIER") : null} />
          <Metric label="RoE"
            value={roe != null ? `${roe.toFixed(1)}%` : "—"}
            sub={ipo.is_profitable === false ? "loss-making" : undefined}
            good={ipo.is_profitable == null ? null : ipo.is_profitable} />
        </div>
      )}

      {/* Context strip — GMP is NOT a signal, shown muted */}
      {!compact && (ipo.gmp_pct != null || ipo.regime_at_listing || ipo.brlm_tier) && (
        <div className="px-4 py-2 flex items-center gap-3 text-[10px] flex-wrap" style={{ background: C.grayBg, color: C.textSub, borderTop: `1px solid ${C.grayBd}` }}>
          {ipo.regime_at_listing && <span>regime: {ipo.regime_at_listing}</span>}
          {ipo.brlm_tier && <span>BRLM: {ipo.brlm_tier}</span>}
          {ipo.gmp_pct != null && <span title="Grey-market premium is non-predictive in backtest — context only">GMP {Number(ipo.gmp_pct) > 0 ? "+" : ""}{Number(ipo.gmp_pct).toFixed(0)}% (context)</span>}
          {ipo.tp1_exit_note && (
            <button onClick={() => setOpen(!open)} className="ml-auto underline" style={{ color: C.blue }}>
              {open ? "hide" : "exit note"}
            </button>
          )}
        </div>
      )}
      {open && ipo.tp1_exit_note && (
        <div className="px-4 py-2 text-[11px]" style={{ color: C.text, background: C.blueBg }}>{ipo.tp1_exit_note}</div>
      )}
    </div>
  );
}
