import test from "node:test";
import assert from "node:assert/strict";
import { enrichCards } from "./ipo-command";

test("enrichCards: mega + positive + 30 anchors => 'stack' setup", () => {
  const { investable } = enrichCards([{
    issue_size_cr: 2500, listing_gap_pct: 12, anchor_count: 40, ofs_cr: 100, fresh_issue_cr: 900,
    band_high: 250, rhp_gate: "accept", issue_price: 250, ipo_pe: 30, peer_median_pe: 28, verdict: "GOOD", ipo_score: 71,
  }]);
  assert.equal(investable.length, 1);
  assert.equal((investable[0] as Record<string, unknown>).playbook_setup, "stack");
  assert.equal((investable[0] as Record<string, unknown>).house_stack, true);
});

test("enrichCards: RHP reject => 'avoid' setup", () => {
  const { investable } = enrichCards([{ issue_size_cr: 2500, listing_gap_pct: 20, anchor_count: 40, ofs_cr: 0, fresh_issue_cr: 1000, band_high: 200, rhp_gate: "reject" }]);
  assert.equal((investable[0] as Record<string, unknown>).playbook_setup, "avoid");
});

test("enrichCards: fair value + research block attached; SBI not present", () => {
  const { investable } = enrichCards([{ issue_size_cr: 1000, issue_price: 100, ipo_pe: 20, peer_median_pe: 25, roe: 20, revenue_cagr_3y: 25, debt_equity: 0.2, ofs_pct: 10, verdict: "GOOD", ipo_score: 68 }]);
  const c = investable[0] as Record<string, unknown>;
  assert.ok("fair_value" in c);           // fairValue spread in
  const research = c.research as Record<string, unknown>;
  assert.equal(research.rhp_status, "CONFIRMED");
  assert.equal("sbi_status" in research, false);   // SBI dropped in V2
  assert.equal(research.fair_value_status, "READY");
});

test("enrichCards: pe_source/pb_source pass through untouched (disclosure)", () => {
  const { investable } = enrichCards([{ issue_size_cr: 500, pe_source: "rhp_computed:price/eps_post", pb_source: "rhp_computed:price/nav_per_share" }]);
  const c = investable[0] as Record<string, unknown>;
  assert.equal(c.pe_source, "rhp_computed:price/eps_post");
  assert.equal(c.pb_source, "rhp_computed:price/nav_per_share");
});

test("Command Center intelligence summary uses canonical financial inputs",()=>{
  const {investable}=enrichCards([{issue_size_cr:500,issue_price:100,reported_debt_cr:100,cash_cr:20,debt_repayment_cr:50,interest_expense_cr:10,reported_pat_cr:25,eps_post:5,ebitda_cr:50,roce:18,peer_median_pe:12,verdict:"GOOD",junk_signals:[]}]);
  const summary=(investable[0] as any).intelligence_summary;
  assert.equal(summary.status,"AVAILABLE"); assert.equal(summary.pro_forma.net_debt_cr,30); assert.deepEqual(summary.known_transformations,["DEBT_REPAYMENT"]);
});

test("Command Center intelligence summary is honestly unavailable without canonical inputs",()=>{
  const {investable}=enrichCards([{issue_size_cr:500,issue_price:100}]);
  assert.equal((investable[0] as any).intelligence_summary.status,"UNAVAILABLE");
});
