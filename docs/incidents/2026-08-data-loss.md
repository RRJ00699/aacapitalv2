# 2026-08 destructive-cleanup data loss

## Record

Before this audit the project lost `intraday_30d` (approximately **323,537** fifteen-minute bars), `ipo_rhp_intel`, and `ipomatrix_raw`. The latter two row counts were not preserved; they must not be guessed.

## Failure mechanism and impact

Cleanup classified objects using names and incomplete metadata without proving row counts, repository references, active writers/readers, recovery, or replacement coverage. Historical intraday evidence, RHP intelligence, and the IPOMatrix fallback source became unavailable. `pipeline/cron.py` now explicitly reports that fallback as retired because its source was dropped (`pipeline/cron.py:15-16`, `pipeline/cron.py:353-357`).

## Permanent prevention gate

No table, dataset, route, script, or file may be deleted, archived, renamed, replaced, or lifecycle-purged until a reviewed evidence record contains: current row count/usage; all repository references; active writer; all active readers; operational purpose; backup/recovery; verified replacement; measured replacement coverage; compatibility and rollback; and explicit owner approval. Missing any item means **no action**. Cleanup remains opt-in and no cleanup was run in this phase.

Restoration, backfill, or destructive remediation is a separate owner-approved operation with one-then-three sample validation, runtime/rows/cost disclosure, dry-run, and explicit apply.
