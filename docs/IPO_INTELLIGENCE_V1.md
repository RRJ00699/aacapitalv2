# IPO intelligence v1 operational contract

**Status: Integration candidate — production activation unverified**

## Current state

The shared profile contract, deterministic transformation classifier, pro-forma calculator, canonical-fact Python producer, Complete Details rendering, and compact Command Center summary are implemented. Local fixture publication exercises the existing immutable KV path. Real Neon schema smoke, real publication, production health, and authenticated browser acceptance are **[Unverified]** until an owner runs the commands below with production-scoped credentials.

## Architecture and canonical owners

`RHP/SBI/Anchor extraction → canonical V2 tables/facts → profile builder → transformation engine → valuation → versioned KV snapshots → Command Center / Complete Details`.

There is no PDF-to-profile fact shortcut. Canonical ownership is:

* RHP sectioning and qualitative/structured extraction: `rhp_sections → rhp_sonnet v2-full → rhp_writer`.
* Reported financials: `financial_statements`.
* Reported ratios, ROCE, peer P/E, and persisted valuation: `valuation`.
* Issue economics: `ipo_issue`; other provenance-bearing scalar facts: `source_facts`.
* RHP evidence and verdict inputs: `insights` and `rhp_findings`.
* SBI facts/verdict: the established SBI AI extraction writer and its canonical research-note storage; the intelligence producer only consumes that output.
* Anchor allocations: official NSE/BSE circular stored as `documents.doc_type = anchor`; only facts linked to a verified anchor document are admitted.

Fields without a currently proven canonical owner are offer expenses, detailed selling-shareholder rows, post-offer shareholding tables, and transaction-term-normalised merger/acquisition consideration. They remain UNKNOWN; another extractor must not be added until ownership is approved.

## One schema owner

`lib/intelligence/ipo-profile.schema.json` is the sole cross-runtime schema owner. TypeScript builds the web-domain object; the Python producer loads that same schema and validates its closed required/property set, schema version, identity, and section container types before output. Python does not maintain a second list of schema fields.

## Attach and evidence rules

Details attaches a profile only when there is a verified ISIN and the canonical inputs needed by the deterministic calculator: reported debt, reported PAT, post-issue shares, and issue price. Cash is optional: without it net debt and EV/EBITDA remain explicitly unavailable. Interest expense becomes required only when a verified debt-repayment amount would otherwise change PAT. Otherwise Details emits `intelligence_profile: null`, avoiding an all-UNKNOWN KV payload. Missing evidence is `UNVERIFIED_UNKNOWN`, never `VERIFIED_FACT`. Quantified verified uses may become `DETERMINISTIC_PRO_FORMA`; transaction intent without sufficient terms remains `SCENARIO_OPTIONALITY` and never changes earnings.

The approved RHP structured extraction owns page-cited `cash_cr`, `interest_expense_cr`, `operating_cash_flow_cr`, `debt_repayment_cr`, and `capex_cr`; `rhp_writer` performs unit normalization and appends changes to `source_facts`. Readers select the newest correction with `DISTINCT ON (ipo_id, field) ... ORDER BY fetched_at DESC`. Post-issue shares are derived only when `valuation.inputs_used.rhp_eps_field = eps_post`; the provenance records PAT period/basis and warns that PAT and RHP EPS periods may not align perfectly.

The shared input builder owns the read model: reported PAT/debt/EBITDA/equity and period/basis come from the latest `financial_statements` row (preferring any basis matching `ILIKE '%consolidat%'`); cash, interest expense, debt repayment, OCF, and capex come from the latest `source_facts` correction; issue price comes from `ipo_issue`; canonical ROCE/peer P/E and EPS provenance come from `valuation`. Cash, OCF, capex, EBITDA, equity, ROCE, and peer P/E are optional and only suppress the dependent output. Debt repayment is optional, but a positive repayment makes interest expense necessary for deterministic PAT.

ROCE is not recomputed by the intelligence engine. It is consumed from canonical `valuation.roce`. Pro-forma formulas cover debt after verified repayment, interest saving, PAT, EPS, P/E, EV/EBITDA, FCF, peer-P/E fair value, and margin of safety.

## Coverage and activation

No representative-corpus extraction coverage measurement has been completed. Any structural or field coverage percentage is therefore **[Unverified]** and intentionally omitted. The engine makes no paid model call; deterministic model cost is ₹0/IPO, while storage/compute/KV cost is plan- and corpus-dependent **[Unverified]**.

Bounded offline generation uses:

```bash
python -m pipeline.intelligence --input canonical-facts.json --ipo-id 123 --limit 1 --dry-run
```

`--limit` is restricted to 1–100. Activation is manual after schema smoke, bounded dry run, real publication, consumer checks, and browser observation. Roll back via the immutable snapshot previous pointer or revert the PR head.
