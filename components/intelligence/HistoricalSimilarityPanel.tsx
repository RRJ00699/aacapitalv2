'use client';

import { useEffect, useMemo, useState } from 'react';

type SimilarityRow = {
  symbol: string;
  similar_to: string;
  similar_to_name?: string;
  similar_to_industry?: string;
  historical_start_date?: string;
  historical_end_date?: string;
  historical_return_pct?: number;
  historical_tier?: string;
  similarity_score: number;
  p_2x: number;
  p_5x: number;
  p_10x: number;
};

function pct(v: unknown, decimals = 0) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return '—';
  return `${n.toFixed(decimals)}%`;
}

function xReturn(returnPct?: number) {
  if (!Number.isFinite(Number(returnPct))) return '—';
  return `${(1 + Number(returnPct) / 100).toFixed(1)}x`;
}

function year(value?: string) {
  if (!value) return '—';
  return String(value).slice(0, 4);
}

export function HistoricalSimilarityPanel({ symbol }: { symbol: string }) {
  const [rows, setRows] = useState<SimilarityRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/multibagger-similarity?symbol=${encodeURIComponent(symbol)}&limit=3`)
      .then((r) => r.json())
      .then((json) => {
        if (cancelled) return;
        if (json.ok) setRows(json.data || []);
        else setError(json.error || 'Similarity engine not ready');
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));

    return () => { cancelled = true; };
  }, [symbol]);

  const aggregate = useMemo(() => {
    if (!rows.length) return null;
    return {
      p2x: Math.round(rows.reduce((s, r) => s + Number(r.p_2x || 0), 0) / rows.length),
      p5x: Math.round(rows.reduce((s, r) => s + Number(r.p_5x || 0), 0) / rows.length),
      p10x: Math.round(rows.reduce((s, r) => s + Number(r.p_10x || 0), 0) / rows.length),
    };
  }, [rows]);

  if (loading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-lg bg-gray-100" />)}
      </div>
    );
  }

  if (error) {
    return <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">{error}</div>;
  }

  if (!rows.length) {
    return <div className="rounded-lg border border-gray-200 bg-white p-3 text-xs text-gray-500">No historical analogs yet. Run the similarity engine after the multibagger miner.</div>;
  }

  return (
    <div className="space-y-3">
      {aggregate && (
        <div className="grid grid-cols-3 gap-2">
          {[
            ['2x probability', aggregate.p2x, 'text-emerald-700 bg-emerald-50 border-emerald-100'],
            ['5x probability', aggregate.p5x, 'text-violet-700 bg-violet-50 border-violet-100'],
            ['10x probability', aggregate.p10x, 'text-slate-800 bg-slate-50 border-slate-200'],
          ].map(([label, value, cls]) => (
            <div key={String(label)} className={`rounded-lg border p-2 text-center ${cls}`}>
              <div className="text-lg font-black tabular-nums">{value}%</div>
              <div className="text-[9px] font-semibold uppercase tracking-wide opacity-70">{label}</div>
            </div>
          ))}
        </div>
      )}

      {rows.map((r) => (
        <div key={`${r.similar_to}-${r.historical_start_date}`} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <div className="font-mono text-sm font-black text-gray-900">{r.similar_to}</div>
                <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-bold text-violet-700">{pct(r.similarity_score)}</span>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold text-gray-600">{r.historical_tier}</span>
              </div>
              <div className="mt-0.5 truncate text-[11px] text-gray-500">{r.similar_to_name || r.similar_to} · {r.similar_to_industry || 'Historical winner'} · {year(r.historical_start_date)} setup</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-black text-emerald-700">{xReturn(r.historical_return_pct)}</div>
              <div className="text-[10px] text-gray-400">outcome</div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md bg-gray-50 p-1.5"><div className="text-xs font-bold text-gray-900">{pct(r.p_2x)}</div><div className="text-[9px] text-gray-400">P(2x)</div></div>
            <div className="rounded-md bg-gray-50 p-1.5"><div className="text-xs font-bold text-gray-900">{pct(r.p_5x)}</div><div className="text-[9px] text-gray-400">P(5x)</div></div>
            <div className="rounded-md bg-gray-50 p-1.5"><div className="text-xs font-bold text-gray-900">{pct(r.p_10x)}</div><div className="text-[9px] text-gray-400">P(10x)</div></div>
          </div>
        </div>
      ))}
    </div>
  );
}
