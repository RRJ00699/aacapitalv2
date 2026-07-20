import type { CommentaryStatus, ManagementCommentaryInput } from './types';

function text(value: unknown): string {
  return String(value || '').toLowerCase();
}

function arrayLength(value: unknown): number {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === 'object') return Object.keys(value as object).length;
  return 0;
}

function clamp(value: number, min = -100, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function demandScore(input: ManagementCommentaryInput): number {
  const combined = `${text(input.management_tone)} ${text(input.guidance_direction)} ${JSON.stringify(input.key_growth_drivers || '')}`;
  let score = 0;
  if (combined.includes('strong') || combined.includes('robust') || combined.includes('healthy')) score += 18;
  if (combined.includes('improving') || combined.includes('positive') || combined.includes('growth')) score += 12;
  if (combined.includes('weak') || combined.includes('slowdown') || combined.includes('muted')) score -= 18;
  if (combined.includes('decline') || combined.includes('pressure')) score -= 12;
  score += Math.min(arrayLength(input.key_growth_drivers) * 3, 12);
  return clamp(score, -30, 35);
}

function marginScore(input: ManagementCommentaryInput): number {
  const combined = `${text(input.management_tone)} ${text(input.guidance_direction)}`;
  let score = 0;
  if (combined.includes('margin expansion') || combined.includes('improving margin')) score += 22;
  if (combined.includes('operating leverage') || combined.includes('better mix')) score += 12;
  if (combined.includes('margin pressure') || combined.includes('cost pressure')) score -= 20;
  if (combined.includes('raw material') || combined.includes('pricing pressure')) score -= 10;
  return clamp(score, -30, 30);
}

function orderBookScore(input: ManagementCommentaryInput): number {
  let score = 0;
  const orderBook = Number(input.order_book_cr || 0);
  if (orderBook >= 5000) score += 25;
  else if (orderBook >= 2000) score += 18;
  else if (orderBook >= 500) score += 10;
  const coverage = text(input.order_book_coverage);
  if (coverage.includes('2x') || coverage.includes('two year') || coverage.includes('24 month')) score += 12;
  if (coverage.includes('strong') || coverage.includes('healthy')) score += 8;
  return clamp(score, 0, 35);
}

function guidanceScore(input: ManagementCommentaryInput): number {
  const direction = text(input.guidance_direction);
  let score = 0;
  if (direction.includes('raise') || direction.includes('upgrade') || direction.includes('positive')) score += 25;
  if (direction.includes('maintain') || direction.includes('stable')) score += 8;
  if (direction.includes('cut') || direction.includes('downgrade') || direction.includes('negative')) score -= 30;
  return clamp(score, -35, 30);
}

function riskScore(input: ManagementCommentaryInput): number {
  const risks = arrayLength(input.key_risks);
  const negatives = arrayLength(input.negative_surprises);
  const positives = arrayLength(input.positive_surprises);
  return clamp(positives * 4 - risks * 5 - negatives * 8, -35, 20);
}

function confidenceScore(input: ManagementCommentaryInput): number {
  const quality = Number(input.mgmt_quality_score || 0);
  const confidence = text(input.confidence);
  let score = quality ? quality * 2 : 0;
  if (confidence.includes('high')) score += 10;
  if (confidence.includes('medium')) score += 4;
  if (confidence.includes('low')) score -= 10;
  return clamp(score, -15, 25);
}

export function getCommentaryStatus(totalScore: number): CommentaryStatus {
  if (totalScore >= 65) return 'BULLISH';
  if (totalScore >= 35) return 'IMPROVING';
  if (totalScore >= 5) return 'NEUTRAL';
  if (totalScore >= -25) return 'CAUTIOUS';
  return 'DETERIORATING';
}

export function scoreManagementCommentary(input: ManagementCommentaryInput) {
  const demand = demandScore(input);
  const margin = marginScore(input);
  const orderBook = orderBookScore(input);
  const guidance = guidanceScore(input);
  const risk = riskScore(input);
  const confidence = confidenceScore(input);
  const total = clamp(demand + margin + orderBook + guidance + risk + confidence, -100, 100);
  const status = getCommentaryStatus(total);

  return {
    symbol: input.symbol,
    company_name: input.company_name || null,
    fiscal_year: input.fiscal_year || null,
    fiscal_quarter: input.fiscal_quarter || null,
    demand_score: demand,
    margin_score: margin,
    order_book_score: orderBook,
    guidance_score: guidance,
    risk_score: risk,
    confidence_score: confidence,
    total_score: total,
    commentary_status: status,
    score_reason: `${status}: demand=${demand}, margin=${margin}, orderBook=${orderBook}, guidance=${guidance}, risk=${risk}, confidence=${confidence}`,
    score_details: {
      inputs: input,
      model: 'aacapital_management_commentary_v1',
      interpretation: status,
    },
  };
}
