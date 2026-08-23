# Current project priority order

Status: **CURRENT** — sets what work is in-scope for this and the next PR.

Derived from Point 6 of the owner brief (2026-08-23).

## The order

1. **Priority 1 — DB migration + historical bootstrap**
   * Finish the 5-table D1 schema (`d1/migrations/*.sql`) — done in PR #342.
   * Prove Neon READ ONLY → local Wrangler D1 → reconcile end-to-end —
     done, see `_migrate/reconciliation_report.md`.
   * Load the IPO Matrix bootstrap per
     `docs/architecture/IPO_MATRIX_BOOTSTRAP.md` (not yet).

2. **Priority 2 — Finish missing forward pipeline pieces**
   * Kite tick / 15-minute candle ingest into `market_observations`.
   * SEBI RHP watcher → `research_findings` (`finding_type='rhp'` /
     `rhp_summary`).
   * Valuation engine v2 writing `fundamentals.ipo_pe`,
     `pb`, `fair_value`, `valuation_score`, `valuation_band`.
   * Decision engine writing `fundamentals.fundamental_verdict`,
     `listing_action`.

3. **Priority 3 — UI / layout polish**
   * Deferred until Priorities 1 and 2 are stable. Major visual /
     structural changes to the public app should NOT land while the D1
     data contract is still being finalised.

## What that means for open PRs

* **PR #342 stays scoped to Priority 1.** No frontend / UI edits.
* Any UAT failure that is proven pre-existing (`main` and PR #342
  both fail identically) is not gated by this PR — see
  `docs/architecture/UAT_JOURNEYS_INVESTIGATION.md`.
* IPO Matrix load is a follow-up PR gated by the unit-map sign-off in
  `docs/architecture/IPO_MATRIX_BOOTSTRAP.md`.
