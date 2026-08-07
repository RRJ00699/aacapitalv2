import assert from "node:assert/strict";
import test from "node:test";
import { buildCanonicalProFormaInputs,fetchCanonicalInputRows } from "./canonical-inputs";

test("eps_pre never derives post-issue shares",()=>assert.equal(buildCanonicalProFormaInputs({reported_pat_cr:20,rhp_eps:5,rhp_eps_field:"eps_pre"}).inputs.post_issue_shares_cr,undefined));
test("eps_post derives post-issue shares with explicit provenance",()=>{
  const built=buildCanonicalProFormaInputs({reported_pat_cr:20,rhp_eps:5,rhp_eps_field:"eps_post",financial_period:"31-Mar-26",financial_basis:"Restated Consolidated"});
  assert.equal(built.inputs.post_issue_shares_cr,4);assert.deepEqual((built.provenance.post_issue_shares_cr as any).derived_from,["financial_statements.pat","valuation.inputs_used.rhp_eps","valuation.inputs_used.rhp_eps_field"]);
});
test("canonical SQL uses latest change-log fact and recognizes Restated Consolidated",async()=>{
  let query="";const sql=(async(strings:TemplateStringsArray)=>{query=strings.join("?");return[]}) as any;
  await fetchCanonicalInputRows(sql,[1]);assert.match(query,/WITH requested AS/);assert.match(query,/FROM requested r/);assert.match(query,/DISTINCT ON \(ipo_id,field\)/);assert.match(query,/ORDER BY ipo_id,field,fetched_at DESC/);assert.match(query,/basis ILIKE '%consolidat%'/);
});
