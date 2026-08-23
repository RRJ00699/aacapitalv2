# D1 migration evidence report

Status: PROPOSED — PR #343 owner review

PR #342 is superseded by PR #343. Only its useful rehearsal/evidence idea was reproduced here; no #342 schema was imported.

## Verified repository evidence

| Gate | Evidence |
|---|---|
| Decimal persistence | DDL contains no `REAL`; canonical decimals are `TEXT`, counts/shares `INTEGER`. |
| Molbio-class rejection | Python pre-insert validator and D1 CHECK constraints enforce ordered band, issue-price containment, and book-built band ≥ face value. |
| Structural universe | `security_kind` is constrained and the existing canonical universe predicate excludes REIT/InvIT. |
| Lifecycle honesty | Status is constrained; `ipo_lifecycle_due` and `concept_state` keep `NOT_DUE` separate from missing, failed, and numeric zero. |
| Identity | Repository `canon` is reused; ISIN/name/Matrix-ID and NSE-symbol collisions are explicit. |
| Immutability | Raw objects reject update/delete; decision history rejects update/delete. |
| Local path | Rehearsal executes transformed Neon-shaped rows and immutable Matrix raw through Wrangler local D1 twice, exports D1, and reconciles counts. |
| IPO Matrix bootstrap | Owner-reviewed paths and explicit units populate normalized issue/profile/ownership/objects/financial/reservation/subscription/anchor/peer/KPI/document homes; every mapped field also writes provenance. Unapproved paths remain raw-only. |
| Constraint honesty | No global `INSERT OR IGNORE` or per-row `SELECT` guard exists. Known rerun keys use an explicit conflict handler that no-ops only when every supplied value is identical and aborts on differing contents; rows without an approved key use plain `INSERT`, and unexpected CHECK/NOT NULL/UNIQUE violations fail the bounded batch. |

## Owner-data evidence still required

`NEON_READONLY_DATABASE_URL` and the immutable archive are absent from this checkout. Therefore real source counts, non-null counts, quarantine reasons, storage bytes, and 964-ID coverage remain **UNKNOWN**. They must be filled from the runbook artifacts before `READY_FOR_OWNER_DB_REVIEW` can be asserted.
