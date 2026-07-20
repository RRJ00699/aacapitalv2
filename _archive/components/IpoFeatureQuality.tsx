type Props = { score: number; bucket?: string; missingFeatures?: string[]; applyEligible?: boolean; qualityReasons?: any };

function tone(bucket?: string) {
  if (bucket === "HIGH") return "border-emerald-400/30 bg-emerald-500/10 text-emerald-200";
  if (bucket === "MEDIUM") return "border-amber-400/30 bg-amber-500/10 text-amber-200";
  if (bucket === "LOW") return "border-orange-400/30 bg-orange-500/10 text-orange-200";
  return "border-slate-500/30 bg-slate-500/10 text-slate-300";
}

export default function IpoFeatureQuality({ score, bucket = "UNKNOWN", missingFeatures = [], applyEligible = false, qualityReasons }: Props) {
  const components = qualityReasons?.components || {};
  const width = Math.max(0, Math.min(100, Number(score || 0)));

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Feature Quality</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-white">{Math.round(score)}</span>
            <span className="text-sm text-slate-400">/100</span>
          </div>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-medium ${tone(bucket)}`}>{bucket}</span>
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-white" style={{ width: `${width}%` }} />
      </div>

      {Object.keys(components).length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-slate-300">
          {Object.entries(components).map(([key, value]) => (
            <div key={key} className="flex justify-between rounded-lg bg-black/20 px-2 py-1">
              <span className="capitalize text-slate-400">{key.replaceAll("_", " ")}</span>
              <span className="font-medium text-slate-100">{String(value)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-slate-400">Apply eligible</span>
        <span className={applyEligible ? "text-xs text-emerald-300" : "text-xs text-amber-300"}>{applyEligible ? "YES" : "NO"}</span>
      </div>

      {missingFeatures.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {missingFeatures.map((feature) => (
            <span key={feature} className="rounded-full border border-slate-600/60 px-2 py-1 text-[11px] text-slate-300">
              {feature.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
