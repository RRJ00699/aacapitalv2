'use client';

import React, { useEffect, useState } from 'react';

type Props = { symbol: string };

export default function TranscriptIntelligencePanel({ symbol }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    fetch(`/api/transcript-intel?symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setData({ error: e.message }))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="rounded-xl border p-4">Loading transcript intelligence...</div>;
  if (!data || data.error) return <div className="rounded-xl border p-4">Transcript intelligence unavailable.</div>;

  const l = data.latest;

  return (
    <div className="rounded-xl border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Transcript Intelligence</h3>
        <span className="text-sm opacity-70">{l?.quarter || 'N/A'}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Score" value={l?.transcript_score ?? 'N/A'} />
        <Metric label="Confidence" value={l?.management_confidence_score ?? 'N/A'} />
        <Metric label="Revenue" value={l?.revenue_tone ?? 'N/A'} />
        <Metric label="Margin" value={l?.margin_tone ?? 'N/A'} />
        <Metric label="Demand" value={l?.demand_tone ?? 'N/A'} />
        <Metric label="Order Book" value={l?.orderbook_tone ?? 'N/A'} />
        <Metric label="Capex" value={l?.capex_tone ?? 'N/A'} />
        <Metric label="Working Capital" value={l?.working_capital_tone ?? 'N/A'} />
      </div>
      {l?.summary && <p className="text-sm opacity-80">{l.summary}</p>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: any }) { return <div className="rounded-lg bg-black/5 p-3"><div className="text-xs opacity-60">{label}</div><div className="font-semibold">{value}</div></div>; }
