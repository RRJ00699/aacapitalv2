'use client';

import React, { useEffect, useState } from 'react';

type Props = { symbol: string };

export default function ManagementCredibilityPanel({ symbol }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    fetch(`/api/management-v2?symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setData({ error: e.message }))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="rounded-xl border p-4">Loading management credibility...</div>;
  if (!data || data.error) return <div className="rounded-xl border p-4">Management credibility unavailable.</div>;

  const l = data.latest;
  const history = data.history || [];

  return (
    <div className="rounded-xl border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Management Credibility</h3>
        <span className="text-sm opacity-70">{l?.quarter || 'N/A'}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Score" value={l?.score ?? 'N/A'} />
        <Metric label="Credibility" value={l?.credibility_score ?? 'N/A'} />
        <Metric label="Guidance Accuracy" value={l?.guidance_accuracy ?? 'N/A'} />
        <Metric label="Execution" value={l?.execution_rating ?? 'N/A'} />
        <Metric label="Tone" value={l?.management_tone ?? 'N/A'} />
        <Metric label="Guidance" value={l?.guidance_direction ?? 'N/A'} />
        <Metric label="Optimism" value={l?.optimism_score ?? 'N/A'} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left opacity-70"><th>Quarter</th><th>Score</th><th>Credibility</th><th>Execution</th><th>Tone</th></tr></thead>
          <tbody>
            {history.map((h: any) => (
              <tr key={`${h.nse_symbol}-${h.quarter}`} className="border-t">
                <td>{h.quarter}</td><td>{h.score}</td><td>{h.credibility_score}</td><td>{h.execution_rating}</td><td>{h.management_tone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: any }) { return <div className="rounded-lg bg-black/5 p-3"><div className="text-xs opacity-60">{label}</div><div className="font-semibold">{value}</div></div>; }
