'use client';

import React, { useEffect, useState } from 'react';

type Props = { symbol: string };

export default function OwnershipTrendPanel({ symbol }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    fetch(`/api/ownership?symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setData({ error: e.message }))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="rounded-xl border p-4">Loading ownership...</div>;
  if (!data || data.error) return <div className="rounded-xl border p-4">Ownership data unavailable.</div>;

  const s = data.signal;
  const history = data.history || [];

  return (
    <div className="rounded-xl border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Ownership Trend</h3>
        <span className="text-sm opacity-70">{s?.latest_quarter || 'N/A'}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Score" value={s?.ownership_score ?? 'N/A'} />
        <Metric label="Signal" value={s?.signal ?? 'N/A'} />
        <Metric label="FII 4Q" value={pct(s?.fii_change_4q)} />
        <Metric label="DII 4Q" value={pct(s?.dii_change_4q)} />
        <Metric label="MF 4Q" value={pct(s?.mf_change_4q)} />
        <Metric label="Public 4Q" value={pct(s?.public_change_4q)} />
        <Metric label="Pledge 4Q" value={pct(s?.pledge_change_4q)} />
        <Metric label="Promoter 4Q" value={pct(s?.promoter_change_4q)} />
      </div>

      {s?.summary && <p className="text-sm opacity-80">{s.summary}</p>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left opacity-70">
              <th>Quarter</th><th>Promoter</th><th>FII</th><th>DII</th><th>MF</th><th>Public</th><th>Pledge</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h: any) => (
              <tr key={`${h.nse_symbol}-${h.quarter}`} className="border-t">
                <td>{h.quarter}</td>
                <td>{pct(h.promoter_pct)}</td>
                <td>{pct(h.fii_pct)}</td>
                <td>{pct(h.dii_pct)}</td>
                <td>{pct(h.mutual_fund_pct)}</td>
                <td>{pct(h.public_pct)}</td>
                <td>{pct(h.pledged_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: any }) {
  return <div className="rounded-lg bg-black/5 p-3"><div className="text-xs opacity-60">{label}</div><div className="font-semibold">{value}</div></div>;
}
function pct(v: any) { const n = Number(v); return Number.isFinite(n) ? `${n.toFixed(2)}%` : 'N/A'; }
