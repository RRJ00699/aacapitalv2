import type { SqlClient } from "@/lib/v2/sql";
import type { ValuationInputs } from "./ipo-profile";

export const PRO_FORMA_SOURCE_FACT_FIELDS = ["cash_cr","interest_expense_cr","debt_repayment_cr","operating_cash_flow_cr","capex_cr"] as const;

/** One canonical reader for Command and Details. Facts are a change-log, so the
 * newest row wins even when a correction decreases a value. */
export async function fetchCanonicalInputRows(sql: SqlClient, ipoIds: Array<string|number>) {
  if (!ipoIds.length) return [];
  return sql`
    WITH latest_financial AS (
      SELECT DISTINCT ON (ipo_id) ipo_id,period,basis,pat,total_debt,ebitda,net_worth
      FROM financial_statements WHERE ipo_id = ANY(${ipoIds})
      ORDER BY ipo_id,(basis ILIKE '%consolidat%') DESC,
        CASE WHEN period ~ '^[0-9]{1,2}-[A-Za-z]{3}-[0-9]{2}$' THEN to_date(period,'DD-Mon-YY') END DESC NULLS LAST
    ), latest_fact AS (
      SELECT DISTINCT ON (ipo_id,field) ipo_id,field,value,fetched_at
      FROM source_facts WHERE ipo_id = ANY(${ipoIds}) AND field = ANY(${[...PRO_FORMA_SOURCE_FACT_FIELDS]})
      ORDER BY ipo_id,field,fetched_at DESC
    ), facts AS (
      SELECT ipo_id,jsonb_object_agg(field,value) AS values_by_field FROM latest_fact GROUP BY ipo_id
    )
    SELECT f.ipo_id,f.period AS financial_period,f.basis AS financial_basis,
      f.pat AS reported_pat_cr,f.total_debt AS reported_debt_cr,f.ebitda AS ebitda_cr,f.net_worth AS net_worth_cr,
      x.values_by_field->>'cash_cr' AS cash_cr,x.values_by_field->>'interest_expense_cr' AS interest_expense_cr,
      x.values_by_field->>'debt_repayment_cr' AS debt_repayment_cr,x.values_by_field->>'operating_cash_flow_cr' AS operating_cash_flow_cr,
      x.values_by_field->>'capex_cr' AS capex_cr
    FROM latest_financial f LEFT JOIN facts x ON x.ipo_id=f.ipo_id`;
}

const numeric = (value: unknown): number|undefined => value == null || value === "" || !Number.isFinite(Number(value)) ? undefined : Number(value);

export function buildCanonicalProFormaInputs(row: Record<string,unknown>): { inputs: ValuationInputs; provenance: Record<string,unknown> } {
  const pat=numeric(row.reported_pat_cr), eps=numeric(row.rhp_eps);
  const epsField=row.rhp_eps_field == null ? null : String(row.rhp_eps_field);
  const postShares=epsField === "eps_post" && pat != null && eps != null && eps > 0 ? pat/eps : undefined;
  return { inputs: { reported_debt_cr:numeric(row.reported_debt_cr),cash_cr:numeric(row.cash_cr),debt_repayment_cr:numeric(row.debt_repayment_cr),
    interest_expense_cr:numeric(row.interest_expense_cr),reported_pat_cr:pat,post_issue_shares_cr:postShares,issue_price:numeric(row.issue_price),
    ebitda_cr:numeric(row.ebitda_cr),equity_cr:numeric(row.net_worth_cr),canonical_roce:numeric(row.roce),peer_pe:numeric(row.peer_median_pe),
    operating_cash_flow_cr:numeric(row.operating_cash_flow_cr),capex_cr:numeric(row.capex_cr) },
    provenance: { financial_period:row.financial_period??null,financial_basis:row.financial_basis??null,
      post_issue_shares_cr: { derived_from:["financial_statements.pat","valuation.inputs_used.rhp_eps","valuation.inputs_used.rhp_eps_field"],
        rhp_eps_field:epsField, alignment_warning:"PAT period/basis and RHP EPS period may not be perfectly aligned." } } };
}

export async function attachCanonicalInputs(sql:SqlClient, rows:Record<string,unknown>[]) {
  const canonical=await fetchCanonicalInputRows(sql,rows.map(r=>r.ipo_id as string|number).filter(Boolean));
  const byId=new Map(canonical.map(r=>[String(r.ipo_id),r]));
  return rows.map(row=>({...row,...(byId.get(String(row.ipo_id))??{})}));
}
