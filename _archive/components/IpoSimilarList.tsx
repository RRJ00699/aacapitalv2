export type SimilarIpo = { ipoId: number; companyName: string; symbol?: string | null; similarityScore: number; listingGainPct: number; reasons?: any };

export default function IpoSimilarList({ items = [] }: { items?: SimilarIpo[] }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3">
        <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Similar IPOs</div>
        <div className="text-sm text-slate-300">Historical peer pattern</div>
      </div>
      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 p-4 text-sm text-slate-400">Similar IPOs are not available yet.</div>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 7).map((item, idx) => (
            <div key={`${item.ipoId}-${idx}`} className="flex items-center justify-between gap-3 rounded-xl bg-black/20 px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-100">{item.companyName}</div>
                <div className="text-xs text-slate-500">{item.symbol || "—"} · Similarity {Math.round(item.similarityScore)}</div>
              </div>
              <div className={item.listingGainPct >= 0 ? "text-right text-emerald-300" : "text-right text-red-300"}>
                <div className="text-sm font-semibold">{item.listingGainPct.toFixed(1)}%</div>
                <div className="text-[11px] text-slate-500">listing</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
