// lib/intelligence/historical-similarity.ts
// Shared scoring helpers for AACapital Historical Similarity Engine.

export type ShapeVector = number[];

export function normalizeShape(values: number[], buckets = 24): ShapeVector {
  const clean = values.filter((v) => Number.isFinite(v) && v > 0);
  if (clean.length === 0) return [];

  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const denom = max - min || 1;
  const normalized = clean.map((v) => (v - min) / denom);

  const out: number[] = [];
  for (let b = 0; b < buckets; b++) {
    const start = Math.floor((b * normalized.length) / buckets);
    const end = Math.max(start + 1, Math.floor(((b + 1) * normalized.length) / buckets));
    const slice = normalized.slice(start, end);
    out.push(slice.reduce((sum, v) => sum + v, 0) / Math.max(1, slice.length));
  }
  return out;
}

export function dtwDistance(a: ShapeVector, b: ShapeVector): number {
  if (!a.length || !b.length) return Number.POSITIVE_INFINITY;
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(Number.POSITIVE_INFINITY));
  dp[0][0] = 0;

  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      const cost = Math.abs(a[i - 1] - b[j - 1]);
      dp[i][j] = cost + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }

  return dp[n][m] / (n + m);
}

export function distanceToSimilarity(distance: number): number {
  if (!Number.isFinite(distance)) return 0;
  // DTW on normalized 24-bucket shapes usually falls inside 0.02-0.25.
  // This maps close structural matches into a usable 0-100 score.
  return Math.max(0, Math.min(100, Math.round(100 * Math.exp(-5.5 * distance))));
}

export function probabilityFromSimilarity(similarityScore: number, historicalReturnPct = 0) {
  const sim = Math.max(0, Math.min(100, similarityScore));
  const outcomeBoost = historicalReturnPct >= 900 ? 8 : historicalReturnPct >= 500 ? 5 : historicalReturnPct >= 200 ? 2 : 0;

  return {
    p2x: Math.max(3, Math.min(72, Math.round(8 + sim * 0.52 + outcomeBoost))),
    p5x: Math.max(1, Math.min(38, Math.round(1 + sim * 0.25 + outcomeBoost * 0.6))),
    p10x: Math.max(0, Math.min(16, Math.round(sim * 0.08 + outcomeBoost * 0.35))),
  };
}

export function classifyTier(returnPct: number): '10x' | '5x' | '2x' | 'winner' {
  if (returnPct >= 900) return '10x';
  if (returnPct >= 400) return '5x';
  if (returnPct >= 100) return '2x';
  return 'winner';
}
