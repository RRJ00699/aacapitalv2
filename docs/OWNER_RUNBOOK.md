# AACapital owner runbook

All Indian market times are **IST**; owner schedules must say **CST/CDT**. Production actions require owner approval.

## Pipeline

* Status: open `/dashboard/settings` and inspect Pipeline Steps/Failures. The new cron summary prints `run_id`, IPO count, runtime, cost, and failed steps. Until the proposed ledger migration is reviewed/applied, ledger inserts safely degrade with a warning.
* Dry run (no writers or ledger events): `cd pipeline && python cron.py --dry-run --limit 1 --skip-download --skip-kite`.
* Small apply (database/paid write — approve first): disclose scope/runtime/cost/rows, then `cd pipeline && python cron.py --run --limit 1 --skip-download`. The DB `daily_spend_cap_usd` remains authoritative.
* Never use `--backfill`, paid extraction, cleanup flags, or a full-universe limit without a separately reviewed plan.

## KV freshness and rollback

The initial bases are `ipo-command:v6` and `ipo:index:v3`. Inspect only metadata/pointers (`:active`, `:previous`) and the referenced immutable envelope; do not log payload secrets. Verify `generated_at`, checksum, schema version, source freshness, and engine versions.

Publication is an authenticated admin/pipeline operation: build, validate metadata, immutable write, read back, checksum verify, copy old active to previous, then switch active. To roll back, copy the exact `:previous` pointer value to `:active`; do not delete the bad immutable version until the destructive-cleanup gate is satisfied. Validate the user route before any later cleanup.

## Deploy

After an approved PR is merged, run the existing GitHub **Deploy Cloudflare Worker** workflow manually. Confirm tests/build, diff, bindings, rollback commit, and current Worker version first. This phase must not trigger it. Never purge all KV, alter bindings/routes, create resources, or deploy from a workstation without approval.

## Proposed schedule (not active)

Retain manual dispatch. After approval, one weekday run at `13:30 UTC` (**19:00 IST**, **08:30 CST / 09:30 CDT**) with active IPOs only, default limit 3, no history sweep, concurrency locking, existing spend cap, downloads skipped until runner capture is proven, and artifacts only on failure.

## Database migration proposal — not applied

Live `pipeline_step_runs` columns could not be inspected through an enabled Neon tool. First run a read-only information-schema query and row count on confirmed branch `aacapitalpvtltd`. If fields are absent, propose only nullable additions for `run_id`, `step_name`, `started_at`, `finished_at`, `status`, `ipo_count`, `rows_read`, `rows_written`, `estimated_cost`, `actual_cost`, `error_summary`, `retry_number`, and `source_freshness JSONB`, plus a non-blocking index on `(run_id, step_name)`. Current count supplied by owner: 0. Compatibility risk is low for nullable columns; lock/runtime should be brief at zero rows; cost $0. Rollback is dropping only newly added columns/index **after** reader/writer reference proof and approval. Do not apply automatically.
