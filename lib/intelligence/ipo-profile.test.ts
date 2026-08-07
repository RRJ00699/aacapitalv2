import assert from "node:assert/strict";
import test from "node:test";
import { buildIpoProfile, calculateProForma, classifyTransformation } from "./ipo-profile";

const fact = (value: unknown) => ({ classification: "VERIFIED_FACT" as const, value, source_document_id: 7, page: 42 });

test("debt-heavy IPO debt repayment produces deterministic post-IPO valuation", () => {
  const result = calculateProForma({ reported_debt_cr:500,cash_cr:50,debt_repayment_cr:300,interest_expense_cr:60,reported_pat_cr:100,post_issue_shares_cr:10,issue_price:150,ebitda_cr:200,tax_rate:.25,peer_pe:18 });
  assert.equal(result.status,"AVAILABLE");
  if(result.status === "AVAILABLE") { assert.equal(result.post_ipo_debt_cr,200); assert.equal(result.interest_savings_cr,36); assert.equal(result.pro_forma_pat_cr,127); assert.equal(result.pro_forma_eps,12.7); }
});

test("merger and related-business facts remain optional without sufficient transaction terms", () => {
  const merger=classifyTransformation("RELATED_BUSINESS_COMBINATION",[fact("board intent")]);
  assert.equal(merger.classification,"SCENARIO_OPTIONALITY"); assert.equal(merger.status,"OPTIONAL");
});

test("capex without earnings guidance never becomes earnings", () => {
  const capex=classifyTransformation("CAPEX",[fact("₹100cr facility")],100);
  assert.equal(capex.status,"KNOWN");
  const valuation=calculateProForma({reported_debt_cr:0,cash_cr:10,reported_pat_cr:20,post_issue_shares_cr:10,issue_price:50,capex_cr:100});
  assert.equal(valuation.status,"AVAILABLE"); if(valuation.status==="AVAILABLE") assert.equal(valuation.pro_forma_pat_cr,20);
});

test("acquisition intent with insufficient terms is optionality",()=>assert.equal(classifyTransformation("ACQUISITION",[fact("intends to acquire")]).status,"OPTIONAL"));

test("multiple and historical profiles use the identical canonical builder",()=>{
  const rows=([[1,"INE000000001"],[2,"INE000000002"],[99,"INE000000099"]] as Array<[number,string]>).map(([ipo_id,isin])=>buildIpoProfile({ipo_id,isin,identity:{historical:ipo_id===99}}));
  assert.equal(rows.length,3); assert.ok(rows.every(x=>x.schema_version==="ipo-profile:v1")); assert.equal((rows[2].identity as any).historical,true);
});

test("missing valuation inputs return INSUFFICIENT_DATA",()=>assert.deepEqual(calculateProForma({issue_price:100}),{status:"INSUFFICIENT_DATA",missing_inputs:["reported_debt_cr","cash_cr","reported_pat_cr","post_issue_shares_cr"]}));
