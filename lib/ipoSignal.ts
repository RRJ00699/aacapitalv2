// lib/ipoSignal.ts — SINGLE SOURCE OF TRUTH for the validated IPO post-listing signal.
// Imported by IpoSignalCard, dashboards, tiles — so the read can never drift again.
//
// Backtest N=343, 2010–2026, scored as BUY-AT-OPEN + exit on strength (best close ≤10 sessions):
//   LOW  (<10%)   steady     — ~70% green exit ≤10d (+4% median), peaks ~session 15.
//   MID  (10-30%) playable   — ~81% green exit ≤10d (+10% median), peaks ~session 18. Let it run.
//   HIGH (>30%)   pop & fade — ~61% green exit ≤10d (+3%), peaks ~session 10 then fades. Exit fast.
// Population downside (hold-through context): median −9% drawdown, −22% tail.

export type Tone = "green" | "amber" | "red" | "blue" | "gray";
export type GapBucket = "LOW" | "MID" | "HIGH";
export interface Signal { tier: string; tone: Tone; headline: string; detail: string; bucket: GapBucket | null; }

export const BASE_RATES: Record<GapBucket, {
  winRate: number; median: number; peakDay: number; drawdown: number; tail: number; action: string; tone: Tone;
}> = {
  LOW:  { winRate: 70, median: 4,  peakDay: 15, drawdown: -9, tail: -22, action: "Buy-at-open workable · manage to floor", tone: "blue"  },
  MID:  { winRate: 81, median: 10, peakDay: 18, drawdown: -8, tail: -22, action: "Buy-at-open · let it run",               tone: "green" },
  HIGH: { winRate: 61, median: 3,  peakDay: 10, drawdown: -9, tail: -22, action: "Capture fast · don't hold",             tone: "amber" },
};

const num = (v: unknown): number | null => { const n = parseFloat(String(v)); return Number.isFinite(n) ? n : null; };

// Minimal structural input — any IPO row with these fields works.
export type SigInput = {
  listing_open?: number | null; issue_price?: number | null; gap_bucket?: string | null;
  total_subscription?: number | null; qib_subscription?: number | null;
};

export function bucketOf(r: SigInput): GapBucket | null {
  const b = (r.gap_bucket ?? "").toUpperCase();
  if (b === "LOW" || b === "MID" || b === "HIGH") return b;
  const open = num(r.listing_open), issue = num(r.issue_price);
  if (open == null || issue == null || issue === 0) return null;
  const gap = (open - issue) / issue * 100;
  return gap < 10 ? "LOW" : gap <= 30 ? "MID" : "HIGH";
}

export function signalFor(r: SigInput): Signal {
  const listed = r.listing_open != null;
  if (!listed) {
    const sub = num(r.total_subscription ?? r.qib_subscription);
    if (sub != null && sub >= 10)
      return { tier: "PRE-LISTING", tone: "blue", headline: "Heavily subscribed",
        detail: `Demand read: ${sub.toFixed(0)}x total. Demand ≠ listing edge — wait for the open.`, bucket: null };
    return { tier: "PRE-LISTING", tone: "gray", headline: "Awaiting listing",
      detail: "No listing-day data yet. Signal resolves at the open.", bucket: null };
  }
  const b = bucketOf(r);
  if (!b) return { tier: "LISTED", tone: "gray", headline: "Listed", detail: "Gap bucket unavailable.", bucket: null };
  const br = BASE_RATES[b];
  const detail = {
    MID:  `Strongest zone: ~${br.winRate}% gave a green exit within 10 sessions (+${br.median}% median), peaks ~session ${br.peakDay}. Buy-at-open; let it run, manage to the floor.`,
    HIGH: `Strong open: ~${br.winRate}% gave a green exit but it peaks ~session ${br.peakDay} then fades. Capture the move early — don't hold for more.`,
    LOW:  `No pop to chase, but ~${br.winRate}% gave a green exit within 10 sessions (+${br.median}% median). Buy-at-open workable; manage to the floor.`,
  }[b];
  const headline = { MID: "Playable · let it run", HIGH: "Pop & fade · exit fast", LOW: "Steady · manage to floor" }[b];
  return { tier: `${b}-GAP`, tone: br.tone, headline, detail, bucket: b };
}
