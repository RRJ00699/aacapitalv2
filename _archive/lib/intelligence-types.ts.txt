export type EarningsStatus = 'ACCELERATING' | 'STABLE' | 'DECELERATING' | 'TURNAROUND' | 'WARNING';
export type CommentaryStatus = 'BULLISH' | 'IMPROVING' | 'NEUTRAL' | 'CAUTIOUS' | 'DETERIORATING';
export type AmfiLiquidityStatus = 'RISK_ON' | 'SELECTIVE_RISK_ON' | 'NEUTRAL' | 'RISK_OFF' | 'OVERHEATED';

export interface QuarterlyResult {
  symbol: string;
  company_name?: string | null;
  fiscal_year: number;
  fiscal_quarter: string;
  revenue_yoy_growth?: number | null;
  revenue_qoq_growth?: number | null;
  pat_yoy_growth?: number | null;
  pat_qoq_growth?: number | null;
  ebitda_margin?: number | null;
  pat_margin?: number | null;
}

export interface ManagementCommentaryInput {
  symbol: string;
  company_name?: string | null;
  fiscal_year?: number | null;
  fiscal_quarter?: string | null;
  management_tone?: string | null;
  guidance_direction?: string | null;
  order_book_cr?: number | null;
  order_book_coverage?: string | null;
  key_growth_drivers?: unknown;
  key_risks?: unknown;
  positive_surprises?: unknown;
  negative_surprises?: unknown;
  mgmt_quality_score?: number | null;
  confidence?: string | null;
}

export interface AmfiFlowInput {
  report_month: number;
  report_year: number;
  category: string;
  sub_category?: string | null;
  net_inflow?: number | null;
  aum?: number | null;
  mom_change?: number | null;
  yoy_change?: number | null;
}
