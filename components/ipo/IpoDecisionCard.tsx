import IpoFeatureQuality from "./IpoFeatureQuality";
import IpoSimilarList, { type SimilarIpo } from "./IpoSimilarList";

export type IpoPredictionItem = {
  ipoId: number; companyName: string; symbol?: string | null; sector?: string | null; status?: string | null;
  live?: { gmp?: number; gmpPct?: number; qibSub?: number; niiSub?: number; retailSub?: number; totalSub?: number };
  scores: { lqiScore: number; pGain10: number; pGain20: number; pLoss: number; expectedReturnPct: number; expectedDrawdownPct: number; confidence: number };
  quality: { featureQualityScore: number; featureQualityBucket: string; applyEligible: boolean; missingFeatures: string[]; qualityReasons?: any };
  decision: { finalDecision: "APPLY" | "WATCH" | "AVOID" | "UNKNOWN"; decisionStrength: string; reasons?: any };
  similarIpos?: SimilarIpo[];
};

function badge(decision: string) {
  if (decision === "APPLY") return "border-emerald-400/30 bg-emerald-500/10 text-emerald-200";
  if (decision === "WATCH") return "border-amber-400/30 bg-amber-500/10 text-amber-200";
  if (decision === "AVOID") return "border-red-400/30 bg-red-500/10 text-red-200";
  return "border-slate-500/30 bg-slate-500/10 text-slate-300";
}

const pct = (v?: number) => `${Number(v || 0).toFixed(1)}%`;
const mult = (v?: number) => `${Number(v || 0).toFixed(1)}x`;

function Metric({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return <div className="rounded-2xl border border-white/10 bg-black/20 p-3"><div className="text-xs text-slate-500">{label}</div><div className={danger ? "mt-1 text-lg font-semibold text-red-300" : "mt-1 text-lg font-semibold text-white"}>{value}</div></div>;
}

export default function IpoDecisionCard({ item, compact = false }: { item: IpoPredictionItem; compact?: boolean }) {
  const decision = item.decision?.finalDecision || "UNKNOWN";
  const hardBlocks = item.decision?.reasons?.hard_blocks || [];
  const cautionFlags = item.decision?.reasons?.caution_flags || [];

  return (
    <article className="overflow-hidden rounded-3xl border border-white/10 bg-slate-950/70 shadow-2xl shadow-black/30">
      <div className="border-b border-white/10 bg-white/[0.03] p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-xl font-semibold text-white">{item.companyName}</h3>
              {item.symbol && <span className="rounded-full border border-slate-600 px-2 py-0.5 text-xs text-slate-300">{item.symbol}</span>}
              {item.sector && <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-400">{item.sector}</span>}
            </div>
            <div className="mt-2 text-sm text-slate-400">LQI {item.scores.lqiScore.toFixed(1)} · Confidence {item.scores.confidence.toFixed(0)}%</div>
          </div>
          <div className="flex flex-col items-start gap-2 md:items-end">
            <span className={`rounded-full border px-4 py-1.5 text-sm font-semibold ${badge(decision)}`}>{item.decision.decisionStrength?.replaceAll("_", " ") || decision}</span>
            <span className="text-xs text-slate-500">Final: {decision}</span>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Metric label="P(>10%)" value={pct(item.scores.pGain10)} />
          <Metric label="P(loss)" value={pct(item.scores.pLoss)} danger={item.scores.pLoss > 35} />
          <Metric label="Expected" value={pct(item.scores.expectedReturnPct)} />
          <Metric label="GMP" value={pct(item.live?.gmpPct)} />
          <Metric label="Total Sub" value={mult(item.live?.totalSub || 1)} />
        </div>
      </div>

      {!compact && (
        <div className="grid gap-4 p-5 lg:grid-cols-[1fr_1fr]">
          <IpoFeatureQuality score={item.quality.featureQualityScore} bucket={item.quality.featureQualityBucket} missingFeatures={item.quality.missingFeatures} applyEligible={item.quality.applyEligible} qualityReasons={item.quality.qualityReasons} />
          <IpoSimilarList items={item.similarIpos || []} />
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 lg:col-span-2">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Decision Explanation</div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div><div className="text-sm font-medium text-slate-300">Hard blocks</div><div className="mt-2 text-sm text-slate-500">{hardBlocks.length ? hardBlocks.join(", ").replaceAll("_", " ") : "No hard blocks"}</div></div>
              <div><div className="text-sm font-medium text-slate-300">Caution flags</div><div className="mt-2 text-sm text-slate-500">{cautionFlags.length ? cautionFlags.join(", ").replaceAll("_", " ") : "No caution flags"}</div></div>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
