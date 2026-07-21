// lib/listing-review.ts — Listing Review derivations (2026-07-22). PURE:
// executed in tests via esbuild+node. Deterministic explanations from
// structured facts — never buyer/seller attribution, never LLM speculation.

export type ReviewState = "PRE-LISTING" | "LISTING DAY LIVE" | "LISTING DAY COMPLETE"
  | "LISTING WEEK IN PROGRESS" | "LISTING WEEK COMPLETE";

const DAY = 86400_000;
const utcDate = (s: string) => { const d = new Date(s); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); };

export function reviewState(listingDate: string | null, nowIstMs: number, marketOpen: boolean, tradingDaysDone: number): ReviewState {
  if (!listingDate) return "PRE-LISTING";
  const l0 = utcDate(listingDate);
  const t0 = Date.UTC(new Date(nowIstMs).getUTCFullYear(), new Date(nowIstMs).getUTCMonth(), new Date(nowIstMs).getUTCDate());
  if (t0 < l0) return "PRE-LISTING";
  if (t0 === l0) return marketOpen ? "LISTING DAY LIVE" : "LISTING DAY COMPLETE";
  return tradingDaysDone >= 5 ? "LISTING WEEK COMPLETE" : "LISTING WEEK IN PROGRESS";
}

export type Facts = {
  issue?: number | null; open?: number | null; high?: number | null; low?: number | null;
  close?: number | null; gmpImplied?: number | null; fairValue?: number | null;
  deliveryPct?: number | null; volume?: number | null; offeredShares?: number | null;
};
export type Observation = {
  observation: string; facts: string[]; impact: "High" | "Medium" | "Low";
  certainty: "Confirmed" | "Supported inference"; counter: string[];
};

const pct = (a: number, b: number) => ((a - b) / b) * 100;
const f1 = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;

// Max five ranked observations; prohibited attribution words never appear.
export function observations(fx: Facts): Observation[] {
  const out: Observation[] = [];
  const { issue, open, close, high, gmpImplied, fairValue, deliveryPct, volume, offeredShares } = fx;
  if (issue && open) {
    const prem = pct(open, issue);
    const vsGmp = gmpImplied ? pct(open, gmpImplied) : null;
    out.push({
      observation: prem >= 0
        ? (vsGmp != null && vsGmp < -1
          ? "Positive debut, but the open underperformed grey-market expectations."
          : "The debut priced above issue — demand absorbed supply at the open.")
        : "The stock listed below issue price — supply exceeded demand at the open.",
      facts: [`Issue ₹${issue}`, `Listing open ₹${open} (${f1(prem)})`,
        ...(gmpImplied ? [`Final GMP implied ₹${gmpImplied}`] : []),
        ...(close ? [`Close ₹${close} (${f1(pct(close, issue))} vs issue)`] : [])],
      impact: "High", certainty: "Confirmed", counter: [],
    });
  }
  if (open && high && close && high > open && pct(close, high) < -3) {
    out.push({
      observation: "The intraday high was rejected — the premium compressed into the close.",
      facts: [`High ₹${high}`, `Close ₹${close} (${f1(pct(close, high))} from high)`],
      impact: "Medium",
      certainty: "Supported inference",
      counter: close > (open ?? 0) ? ["Price still closed above the listing open."] :
        (issue && close > issue ? ["Price held above issue into the close."] : []),
    });
  }
  if (deliveryPct != null && volume && offeredShares) {
    const volPctOffer = (volume / offeredShares) * 100;
    out.push({
      observation: deliveryPct >= 30
        ? "Substantial delivery — a meaningful share of listing-day buying was taken home, not intraday churn."
        : "Low delivery — listing-day activity was dominated by intraday turnover.",
      facts: [`Delivery ${deliveryPct.toFixed(1)}%`, `Volume ${(volPctOffer).toFixed(0)}% of offered shares`],
      impact: "Medium",
      certainty: "Supported inference",
      counter: deliveryPct >= 30 ? [] : ["Delivery data settles T+1 and can revise."],
    });
  }
  if (fairValue && close) {
    const vsFv = pct(close, fairValue);
    out.push({
      observation: vsFv <= 0
        ? "The close sits below AACapital fair value — the discount persists."
        : "The close sits above AACapital fair value — the premium narrowed the margin of safety.",
      facts: [`Fair value ₹${fairValue}`, `Close ₹${close} (${f1(vsFv)} vs FV)`],
      impact: "Low", certainty: "Confirmed", counter: [],
    });
  }
  return out.slice(0, 5);
}

// Prohibited attribution phrases — test-pinned so they can never render.
export const PROHIBITED = [/mutual funds? sold/i, /fiis? (sold|dumped)/i, /anchors? (exited|sold)/i,
  /operators? manipulated/i, /retail panic/i];
