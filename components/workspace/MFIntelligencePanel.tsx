'use client';

import React, { useEffect, useState } from 'react';

type Props = { symbol: string };

export default function MFIntelligencePanel({ symbol }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    fetch(`/api/mf-intelligence?symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setData({ error: e.message }))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="rounded-xl border p-4">Loading MF intelligence...</div>;
  if (!data || data.error) return <div className="rounded-xl border p-4">MF intelligence unavailable.</div>;

  const latest = data.latest;
  const funds = data.topFunds || [];

  return (
    <div className="rounded-xl border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Mutual Fund Intelligence</h3>
        <span className="text-sm opacity-70">{latest?.month ? String(latest.month).slice(0, 10) : 'N/A'}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Funds Holding" value={latest?.fund_count ?? 'N/A'} highlight={Number(latest?.fund_count) >= 10} />
        <Metric label="AMC Count"     value={latest?.amc_count ?? 'N/A'} />
        <Metric label="Signal"        value={latest?.signal ?? 'N/A'} />
        <Metric label="Avg Weight"    value={funds.length > 0 ? pct(funds.reduce((s: number, f: any) => s + Number(f.portfolio_weight_pct || 0), 0) / funds.length) : 'N/A'} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left opacity-70"><th>AMC</th><th>Scheme</th><th>Value</th><th>Weight</th></tr></thead>
          <tbody>
            {funds.map((f: any, i: number) => (
              <tr key={`${f.scheme_name}-${i}`} className="border-t">
                <td>{f.amc_name}</td><td>{f.scheme_name}</td><td>{cr(f.market_value_cr)}</td><td>{pct(f.portfolio_weight_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) { return <div className={`rounded-lg p-3 ${highlight ? "bg-emerald-50 border border-emerald-200" : "bg-black/5"}`}><div className="text-xs opacity-60">{label}</div><div className={`font-semibold ${highlight ? "text-emerald-700" : ""}`}>{value}</div></div>; }
function pct(v: any) { const n = Number(v); return Number.isFinite(n) ? `${n.toFixed(2)}%` : 'N/A'; }
function cr(v: any) { const n = Number(v); return Number.isFinite(n) ? `₹${n.toFixed(1)} Cr` : 'N/A'; }
