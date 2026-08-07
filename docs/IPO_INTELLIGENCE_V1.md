# IPO intelligence v1 operational contract

**Status: Active**

## Architecture

`official PDF/NSE → immutable R2 object → documents ledger → SHA-256 verified read → deterministic extraction → ipo-profile:v1 → economic transformation → pro-forma valuation → versioned KV snapshot → zero-Neon consumers`.

The document ledger remains the only upload boundary. Extraction accepts only a hash-verified object body. The same pure profile builder is used for current and historical IPOs. The bounded offline command is:

```bash
python -m pipeline.intelligence --input verified-extracts.json --ipo-id 123 --limit 1 --dry-run
```

`--limit` is restricted to 1–100. Dry run neither publishes nor writes its output file. Public consumers continue to read versioned KV and do not import a database or R2 client.

## Canonical schema

Required top-level fields are `schema_version`, `ipo_id`, `isin`, `identity`, `company`, `promoters`, `business`, `issue`, `timetable`, `objects`, `expenses`, `selling_shareholders`, `shareholding`, `reservation`, `anchor`, `subscriptions`, `financials`, `kpis`, `peers`, `documents`, `rhp_analysis`, `sbi_analysis`, `economic_transformations`, `valuation`, `listing`, `market`, `provenance`, and `generated_at`. Unknown values remain explicit `UNKNOWN`/`INSUFFICIENT_DATA`; vendor HTML, identifiers, and rankings are excluded.

## Extraction coverage

Deterministic extraction covers labelled company identity, fresh issue/OFS, objects, EPS, NAV, RoNW, debt, cash, interest expense, peer-section evidence, litigation, contingent liabilities, related-party evidence, anchor investor/shares/amount/allocation, and SBI rating/fair value/valuation observation. These are 22 deterministic field groups out of the 27 requested extract groups (**81.5% structural deterministic coverage**); dense financial tables, promoter/shareholding tables, margins, capex/acquisition tables, selling-shareholder tables, and free-form business descriptions deliberately remain UNKNOWN until table-specific parsers have sufficient fixtures. AI owns exactly five qualitative outputs—qualitative risk, governance, RHP verdict, SBI verdict, and business quality—and therefore has **0% verified-fact coverage** and **100% of the five qualitative fields**. No paid model call is in the builder or CI.

## Transformation rules

Supported types are debt repayment/refinancing, capex, capacity addition, acquisition, merger, related-business combination, subsidiary consolidation, working capital, asset sale, new facility, geographic expansion, share dilution, and OFS. A quantified verified use may become `DETERMINISTIC_PRO_FORMA`; acquisition, merger, capacity, related-business, or expansion intent without sufficient terms remains `SCENARIO_OPTIONALITY`. Aspirational capacity or acquisition language never changes revenue, EBITDA, or PAT.

## Valuation formulas

* Post-IPO debt = reported debt − min(verified debt repayment, reported debt).
* Interest saving = reported interest expense × repaid debt / reported debt.
* Pro-forma PAT = reported PAT + interest saving × (1 − verified tax rate). With no tax rate, the engine uses zero only as an explicit arithmetic default; the output does not claim a verified tax assumption.
* EPS = PAT / post-issue shares; P/E = issue price / EPS.
* EV/EBITDA = (market capitalisation + post-IPO debt − cash) / EBITDA.
* ROE = pro-forma PAT / equity; ROCE = EBITDA / capital employed; FCF = operating cash flow − capex.
* Fair value = verified peer P/E × pro-forma EPS; margin of safety = (fair value − issue price) / fair value.

Missing core inputs return `INSUFFICIENT_DATA`. A target is not consolidated for a merger/acquisition without signed transaction terms and standalone target evidence.

## Cost, runtime, activation, and rollback

Deterministic processing makes no paid API calls. Estimated variable model cost is **₹0 / IPO by default**; an optional qualitative call is provider/model dependent and must be explicitly budgeted outside this engine. Storage is one copy of each official PDF plus KV payload; Cloudflare/Neon charges depend on the deployed plans. Historical deterministic backfill therefore has **₹0 model cost**; infrastructure cost is document bytes, bounded compute, and snapshot writes. Typical local parsing is expected to take seconds per IPO, while PDF download time dominates; measure the production corpus before setting an SLA.

Activation is manual: prepare verified extracts, run a dry batch, inspect classifications, then publish through the existing snapshot publication job. Rollback uses the existing immutable snapshot `previous` pointer or a revert of this commit. The principal known risks are layout-specific PDF misses and incomplete financial-table extraction; both fail closed as UNKNOWN rather than inventing values.
