/** Canonical, vendor-independent IPO intelligence contract and pure economic engine. */
import profileSchema from "./ipo-profile.schema.json";
export const IPO_PROFILE_SCHEMA_VERSION = "ipo-profile:v1" as const;
export type EvidenceClass = "VERIFIED_FACT" | "DETERMINISTIC_PRO_FORMA" | "SCENARIO_OPTIONALITY" | "UNVERIFIED_UNKNOWN";
export type TransformationType = "DEBT_REPAYMENT" | "DEBT_REFINANCING" | "CAPEX" | "CAPACITY_ADDITION" | "ACQUISITION" | "MERGER" | "RELATED_BUSINESS_COMBINATION" | "SUBSIDIARY_CONSOLIDATION" | "WORKING_CAPITAL" | "ASSET_SALE" | "NEW_FACILITY" | "GEOGRAPHIC_EXPANSION" | "SHARE_DILUTION" | "OFS";

export type Evidence<T = unknown> = { classification: EvidenceClass; value: T; source_document_id?: number; page?: number; excerpt?: string };
export type Transformation = { type: TransformationType; classification: EvidenceClass; amount_cr?: number | null; status: "KNOWN" | "OPTIONAL" | "INSUFFICIENT_DATA"; evidence: Evidence[] };
export type ValuationInputs = { reported_debt_cr?: number; cash_cr?: number; debt_repayment_cr?: number; interest_expense_cr?: number; reported_pat_cr?: number; post_issue_shares_cr?: number; issue_price?: number; ebitda_cr?: number; equity_cr?: number; canonical_roce?: number; tax_rate?: number; peer_pe?: number; capex_cr?: number; operating_cash_flow_cr?: number };

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const rounded = (v: number) => Math.round(v * 10000) / 10000;
const insufficient = (missing: string[]) => ({ status: "INSUFFICIENT_DATA" as const, missing_inputs: missing });

/** Only signed/quantified uses become deterministic transformations. Aspirations stay scenarios. */
export function classifyTransformation(type: TransformationType, evidence: Evidence[], amountCr?: number | null): Transformation {
  const verified = evidence.filter(e => e.classification === "VERIFIED_FACT");
  const deterministic = verified.length > 0 && finite(amountCr);
  const scenarioOnly = type === "ACQUISITION" || type === "MERGER" || type === "RELATED_BUSINESS_COMBINATION" || type === "CAPACITY_ADDITION" || type === "GEOGRAPHIC_EXPANSION";
  return {
    type,
    classification: deterministic ? "DETERMINISTIC_PRO_FORMA" : scenarioOnly && evidence.length > 0 ? "SCENARIO_OPTIONALITY" : verified.length > 0 ? "VERIFIED_FACT" : "UNVERIFIED_UNKNOWN",
    amount_cr: finite(amountCr) ? amountCr : null,
    status: deterministic ? "KNOWN" : scenarioOnly && evidence.length > 0 ? "OPTIONAL" : "INSUFFICIENT_DATA",
    evidence,
  };
}

/** Deterministic valuation; absent evidence is explicit and never replaced by assumptions. */
export function calculateProForma(i: ValuationInputs) {
  const required: (keyof ValuationInputs)[] = ["reported_debt_cr", "reported_pat_cr", "post_issue_shares_cr", "issue_price"];
  if (finite(i.debt_repayment_cr) && i.debt_repayment_cr > 0 && !finite(i.interest_expense_cr)) required.push("interest_expense_cr");
  const missing = required.filter(k => !finite(i[k]));
  if (missing.length) return insufficient(missing);
  const debtRepaid = Math.min(i.reported_debt_cr!, finite(i.debt_repayment_cr) ? i.debt_repayment_cr : 0);
  const postDebt = i.reported_debt_cr! - debtRepaid;
  const savings = debtRepaid > 0 && finite(i.interest_expense_cr) && i.reported_debt_cr! > 0
    ? i.interest_expense_cr * debtRepaid / i.reported_debt_cr! : 0;
  const tax = finite(i.tax_rate) ? i.tax_rate : 0;
  const proFormaPat = i.reported_pat_cr! + savings * (1 - tax);
  const reportedEps = i.reported_pat_cr! / i.post_issue_shares_cr!;
  const proFormaEps = proFormaPat / i.post_issue_shares_cr!;
  const reportedPe = reportedEps > 0 ? i.issue_price! / reportedEps : null;
  const proFormaPe = proFormaEps > 0 ? i.issue_price! / proFormaEps : null;
  const marketCap = i.issue_price! * i.post_issue_shares_cr!;
  const enterpriseValue = finite(i.cash_cr) ? marketCap + postDebt - i.cash_cr : null;
  const fairValue = finite(i.peer_pe) && proFormaEps > 0 ? i.peer_pe * proFormaEps : null;
  return { status: "AVAILABLE" as const, classification: "DETERMINISTIC_PRO_FORMA" as const,
    reported_debt_cr: rounded(i.reported_debt_cr!), post_ipo_debt_cr: rounded(postDebt), cash_cr: finite(i.cash_cr)?rounded(i.cash_cr):null, net_debt_cr: finite(i.cash_cr)?rounded(postDebt-i.cash_cr):null,
    interest_savings_cr: rounded(savings), reported_pat_cr: rounded(i.reported_pat_cr!), pro_forma_pat_cr: rounded(proFormaPat), post_issue_shares_cr: rounded(i.post_issue_shares_cr!),
    reported_eps: rounded(reportedEps), pro_forma_eps: rounded(proFormaEps), reported_pe: reportedPe == null ? null : rounded(reportedPe), pro_forma_pe: proFormaPe == null ? null : rounded(proFormaPe),
    ev_ebitda: enterpriseValue != null && finite(i.ebitda_cr) && i.ebitda_cr > 0 ? rounded(enterpriseValue / i.ebitda_cr) : null,
    roe: finite(i.equity_cr) && i.equity_cr > 0 ? rounded(proFormaPat / i.equity_cr * 100) : null,
    roce: finite(i.canonical_roce) ? rounded(i.canonical_roce) : null,
    fcf_cr: finite(i.operating_cash_flow_cr) && finite(i.capex_cr) ? rounded(i.operating_cash_flow_cr - i.capex_cr) : null,
    fair_value: fairValue == null ? null : rounded(fairValue), margin_of_safety_pct: fairValue == null ? null : rounded((fairValue - i.issue_price!) / fairValue * 100),
    missing_inputs:[...(!finite(i.cash_cr)?["cash_cr_for_net_debt_and_ev"]:[]),...(!finite(i.operating_cash_flow_cr)||!finite(i.capex_cr)?["operating_cash_flow_cr_and_capex_cr_for_fcf"]:[])],
    formulas: { interest_savings: "interest_expense * debt_repaid / reported_debt", pro_forma_pat: "reported_PAT + interest_savings * (1-tax_rate)", eps: "PAT / post_issue_shares", pe: "issue_price / EPS", ev_ebitda: "(market_cap + post_debt - cash) / EBITDA", fcf: "operating_cash_flow - capex", roce: "canonical valuation.roce (not recomputed)" } };
}

export function buildIpoProfile(input: Record<string, unknown>, generatedAt = new Date().toISOString()) {
  if (!Number.isInteger(input.ipo_id) || Number(input.ipo_id) <= 0) throw new Error("ipo_id must be a positive integer");
  if (!/^IN[A-Z0-9]{9}[0-9]$/.test(String(input.isin || ""))) throw new Error("a verified ISIN is required");
  const section = (name: string, fallback: unknown = {}) => input[name] ?? fallback;
  const profile = { schema_version: IPO_PROFILE_SCHEMA_VERSION, ipo_id: input.ipo_id, isin: input.isin,
    identity: section("identity"), company: section("company"), promoters: section("promoters", []), business: section("business"), issue: section("issue"), timetable: section("timetable"), objects: section("objects", []), expenses: section("expenses"), selling_shareholders: section("selling_shareholders", []), shareholding: section("shareholding"), reservation: section("reservation"), anchor: section("anchor", []), subscriptions: section("subscriptions", []), financials: section("financials"), kpis: section("kpis"), peers: section("peers", []), documents: section("documents", []), rhp_analysis: section("rhp_analysis"), sbi_analysis: section("sbi_analysis"), economic_transformations: section("economic_transformations", []), valuation: section("valuation"), listing: section("listing"), market: section("market"), provenance: section("provenance", {}), generated_at: generatedAt };
  const missing = profileSchema.required.filter(key => !(key in profile));
  const extra = Object.keys(profile).filter(key => !(key in profileSchema.properties));
  if (missing.length || extra.length) throw new Error(`ipo-profile schema mismatch: missing=${missing.join(",")} extra=${extra.join(",")}`);
  return profile;
}
