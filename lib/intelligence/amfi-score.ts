import type { AmfiFlowInput, AmfiLiquidityStatus } from './types';

function clamp(value: number, min = -100, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function lc(value: unknown): string {
  return String(value || '').toLowerCase();
}

function flowFor(flows: AmfiFlowInput[], matcher: (f: AmfiFlowInput) => boolean): number {
  return flows.filter(matcher).reduce((sum, f) => sum + Number(f.net_inflow || 0), 0);
}

function scoreFlow(value: number): number {
  if (value >= 30000) return 30;
  if (value >= 20000) return 24;
  if (value >= 10000) return 16;
  if (value >= 3000) return 8;
  if (value >= 0) return 2;
  if (value <= -10000) return -25;
  return -10;
}

export function getAmfiLiquidityStatus(totalScore: number, smallcapHeatScore: number): AmfiLiquidityStatus {
  if (smallcapHeatScore >= 25 && totalScore >= 55) return 'OVERHEATED';
  if (totalScore >= 60) return 'RISK_ON';
  if (totalScore >= 30) return 'SELECTIVE_RISK_ON';
  if (totalScore >= 0) return 'NEUTRAL';
  return 'RISK_OFF';
}

export function scoreAmfiLiquidity(flows: AmfiFlowInput[]) {
  if (flows.length === 0) {
    throw new Error('No AMFI flows supplied for scoring.');
  }

  const first = flows[0];
  const equityFlow = flowFor(flows, (f) => lc(f.category).includes('equity'));
  const debtFlow = flowFor(flows, (f) => lc(f.category).includes('debt'));
  const smallcapFlow = flowFor(flows, (f) => lc(f.category).includes('small') || lc(f.sub_category).includes('small'));
  const midcapFlow = flowFor(flows, (f) => lc(f.category).includes('mid') || lc(f.sub_category).includes('mid'));
  const liquidFlow = flowFor(flows, (f) => lc(f.category).includes('liquid') || lc(f.sub_category).includes('liquid'));
  const sipLikeFlow = flowFor(flows, (f) => lc(f.category).includes('sip') || lc(f.sub_category).includes('sip'));

  const equityFlowScore = scoreFlow(equityFlow);
  const sipStrengthScore = sipLikeFlow ? scoreFlow(sipLikeFlow) : Math.max(0, Math.round(equityFlowScore * 0.5));
  const smallcapHeatScore = clamp(scoreFlow(smallcapFlow), -25, 30);
  const midcapHeatScore = clamp(scoreFlow(midcapFlow), -20, 25);
  const debtShiftScore = clamp(debtFlow > equityFlow ? -15 : 10, -20, 15);
  const liquidityScore = clamp(scoreFlow(equityFlow + midcapFlow + smallcapFlow) - Math.max(0, scoreFlow(liquidFlow) / 2), -30, 30);

  const totalScore = clamp(
    equityFlowScore + sipStrengthScore + smallcapHeatScore + midcapHeatScore + debtShiftScore + liquidityScore,
    -100,
    100,
  );
  const liquidityStatus = getAmfiLiquidityStatus(totalScore, smallcapHeatScore);

  return {
    report_month: first.report_month,
    report_year: first.report_year,
    equity_flow_score: equityFlowScore,
    sip_strength_score: sipStrengthScore,
    smallcap_heat_score: smallcapHeatScore,
    midcap_heat_score: midcapHeatScore,
    debt_shift_score: debtShiftScore,
    liquidity_score: liquidityScore,
    total_score: totalScore,
    liquidity_status: liquidityStatus,
    score_reason: `${liquidityStatus}: equity=${equityFlow}, smallcap=${smallcapFlow}, midcap=${midcapFlow}, debt=${debtFlow}, liquid=${liquidFlow}`,
    score_details: {
      inputs: flows,
      aggregate_flows: { equityFlow, debtFlow, smallcapFlow, midcapFlow, liquidFlow, sipLikeFlow },
      model: 'aacapital_amfi_liquidity_v1',
      interpretation: liquidityStatus,
    },
  };
}
