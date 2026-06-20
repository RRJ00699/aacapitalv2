"use client";

import { useEffect, useState } from "react";
import IpoDecisionCard, { type IpoPredictionItem } from "./IpoDecisionCard";

type ApiResponse = { ok: boolean; summary: { total: number; byDecision: Record<string, number>; byQuality: Record<string, number> }; items: IpoPredictionItem[]; error?: string };
const tabs = ["ALL", "APPLY", "WATCH", "AVOID"] as const;

export default function IpoPredictionsPanel() {
  const [decision, setDecision] = useState<(typeof tabs)[number]>("ALL");
  const [query, setQuery] = useState("");
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limit: "75", similar: "true" });
        if (decision !== "ALL") params.set("decision", decision);
        if (query.trim()) params.set("q", query.trim());
        const res = await fetch(`/api/ipo/predictions?${params}`, { signal: controller.signal, cache: "no-store" });
        setData(await res.json());
      } catch (err: any) {
        if (err?.name !== "AbortError") setData({ ok: false, error: err?.message || "Failed to load IPO predictions", summary: { total: 0, byDecision: {}, byQuality: {} }, items: [] });
      } finally {
        setLoading(false);
      }
    }
    const timer = setTimeout(load, 250);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [decision, query]);

  return (
    <section className="space-y-5">
      <div className="rounded-3xl border border-white/10 bg-slate-950/70 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div><div className="text-xs uppercase tracking-[0.22em] text-slate-500">IPO DNA Engine</div><h2 className="mt-1 text-2xl font-semibold text-white">Listing Probability Command Center</h2><p className="mt-1 text-sm text-slate-400">Additive backend layer. Current IPO UI remains untouched.</p></div>
          <div className="grid grid-cols-3 gap-2 text-center"><Pill label="Apply" value={data?.summary?.byDecision?.APPLY || 0} /><Pill label="Watch" value={data?.summary?.byDecision?.WATCH || 0} /><Pill label="Avoid" value={data?.summary?.byDecision?.AVOID || 0} /></div>
        </div>
        <div className="mt-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-2">{tabs.map((tab) => <button key={tab} onClick={() => setDecision(tab)} className={decision === tab ? "rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-950" : "rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5"}>{tab}</button>)}</div>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search IPO or symbol..." className="w-full rounded-full border border-white/10 bg-black/30 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-white/20 md:w-80" />
        </div>
      </div>
      {loading && <div className="rounded-3xl border border-white/10 bg-slate-950/70 p-8 text-center text-slate-400">Loading IPO predictions...</div>}
      {!loading && data && !data.ok && <div className="rounded-3xl border border-red-400/20 bg-red-500/10 p-5 text-red-200">{data.error || "Failed to load IPO predictions"}</div>}
      {!loading && data?.ok && data.items.length === 0 && <div className="rounded-3xl border border-white/10 bg-slate-950/70 p-8 text-center text-slate-400">No IPOs found.</div>}
      <div className="space-y-5">{data?.items?.map((item) => <IpoDecisionCard key={item.ipoId} item={item} />)}</div>
    </section>
  );
}

function Pill({ label, value }: { label: string; value: number }) {
  return <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3"><div className="text-xs text-slate-500">{label}</div><div className="text-xl font-semibold text-white">{value}</div></div>;
}
