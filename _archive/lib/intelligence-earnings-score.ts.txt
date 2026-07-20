import type { EarningsStatus, QuarterlyResult } from './types';

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function clamp(value: number, min = -100, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function growthScore(yoy: number | null, qoq: number | null): number {
  let score = 0;
  if (yoy !== null) {
    if (yoy >= 50) score += 35;
    else if (yoy >= 30) score += 28;
    else if (yoy >= 20) score += 20;
    else if (yoy >= 10) score += 12;
    else if (yoy >= 0) score += 5;
    else if (yoy <= -20) score -= 25;
    else score -= 10;
  }
  if (qoq !== null) {
    if (qoq >= 20) score += 20;
    else if (qoq >= 10) score += 14;
    else if (qoq >= 3) score += 8;
    else if (qoq >= 0) score += 3;
    else if (qoq <= -15) score -= 18;
    else score -= 8;
  }
  return clamp(score, -50, 55);
}

function marginScore(ebitdaMargin: number | null, patMargin: number | null): number {
  let score = 0;
  if (ebitdaMargin !== null) {
    if (ebitdaMargin >= 25) score += 18;
    else if (ebitdaMargin >= 18) score += 12;
    else if (ebitdaMargin >= 12) score += 6;
    else if (ebitdaMargin < 8) score -= 8;
  }
  if (patMargin !== null) {
    if (patMargin >= 15) score += 17;
    else if (patMargin >= 10) score += 10;
    else if (patMargin >= 5) score += 5;
    else if (patMargin < 2) score -= 10;
  }
  return clamp(score, -25, 35);
}

function consistencyScore(input: QuarterlyResult): number {
  const values = [
    num(input.revenue_yoy_growth),
    num(input.revenue_qoq_growth),
    num(input.pat_yoy_growth),
    num(input.pat_qoq_growth),
  ].filter((v): v is number => v !== null);

  if (values.length === 0) return 0;
  const positive = values.filter((v) => v > 0).length;
  const strong = values.filter((v) => v >= 15).length;
  const negative = values.filter((v) => v < 0).length;
  return clamp(positive * 5 + strong * 4 - negative * 6, -25, 30);
}

export function getEarningsStatus(totalScore: number, input: QuarterlyResult): EarningsStatus {
  const revenueYoY = num(input.revenue_yoy_growth);
  const patYoY = num(input.pat_yoy_growth);

  if ((revenueYoY !== null && revenueYoY < -10) && (patYoY !== null && patYoY < -10)) return 'WARNING';
  if (totalScore >= 75) return 'ACCELERATING';
  if (totalScore >= 50) return 'ACCELERATING';
  if (totalScore >= 25) return 'STABLE';
  if (totalScore >= 5) return 'TURNAROUND';
  if (totalScore >= -15) return 'DECELERATING';
  return 'WARNING';
}

export function scoreEarnings(input: QuarterlyResult) {
  const revenueAccelerationScore = growthScore(num(input.revenue_yoy_growth), num(input.revenue_qoq_growth));
  const patAccelerationScore = growthScore(num(input.pat_yoy_growth), num(input.pat_qoq_growth));
  const marginExpansionScore = marginScore(num(input.ebitda_margin), num(input.pat_margin));
  const consistency = consistencyScore(input);
  const totalScore = clamp(revenueAccelerationScore + patAccelerationScore + marginExpansionScore + consistency, -100, 100);
  const accelerationStatus = getEarningsStatus(totalScore, input);

  return {
    symbol: input.symbol,
    company_name: input.company_name || null,
    fiscal_year: input.fiscal_year,
    fiscal_quarter: input.fiscal_quarter,
    revenue_acceleration_score: revenueAccelerationScore,
    pat_acceleration_score: patAccelerationScore,
    margin_expansion_score: marginExpansionScore,
    consistency_score: consistency,
    total_score: totalScore,
    acceleration_status: accelerationStatus,
    score_details: {
      inputs: input,
      model: 'aacapital_earnings_acceleration_v1',
      interpretation: accelerationStatus,
    },
  };
}
