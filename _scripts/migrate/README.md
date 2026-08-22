# _scripts/migrate/ — Stage B / Stage C tooling

Status: **AUTHORED, NOT EXECUTED.** These scripts are ready to run against
the existing `NEON_READONLY_DATABASE_URL` Actions secret and a staging D1,
but nothing here has been executed against your Cloudflare account or
Neon. Owner-run only.

## Files

| File | Purpose |
|---|---|
| `neon_to_d1.py` | Read-only Neon → staging D1 copy. Deterministic, resumable, idempotent, observable, bounded, non-destructive. |
| `reconcile.py` | Row-count / PK-coverage / critical-field sample-diff reports (`_migrate/reconciliation_report.{md,json}`). |
| `requirements.txt` | Minimal Python deps. |

## Guarantees

1. **Neon is READ-ONLY.** Every session executes `SET default_transaction_read_only = on` before touching data. Any script that violates this fails Postgres side, no DDL/UPDATE/DELETE possible.
2. **Staging D1 only.** The scripts write via `wrangler d1 execute --env staging`. `--sink wrangler-local` is the default (Miniflare sqlite in `workers/ingest/.wrangler/`). `--sink wrangler-remote-staging` requires the owner to `wrangler login` and does **not** target production because no `env.production` exists in `wrangler.jsonc`.
3. **No paid API calls.** Neon and Cloudflare only. No Anthropic / Kite / SEBI etc. traffic.
4. **Bounded.** `NEON_TO_D1_BATCH` (default 500) controls page size; wrangler d1 execute size limit falls back to half-batches on error.
5. **Resumable.** `_migrate/state.json` tracks the byte-level `copied` counter per table. Crash → rerun → continue from `offset`.
6. **Idempotent.** All writes use `INSERT ... ON CONFLICT DO NOTHING` keyed by the *real* PK; re-runs are safe.
7. **Observable.** Every run writes `_migrate/copy_report.{md,json}` and `_migrate/reconciliation_report.{md,json}`. CI can gate on these.
8. **Non-destructive.** Neon is never mutated. Staging D1 is drop-and-recreate ONLY when the operator passes `--fresh`.

## Runbook (owner only)

### 1. Dry run — print Neon row counts, write nothing

```bash
export NEON_READONLY_DATABASE_URL="postgresql://..."
python _scripts/migrate/neon_to_d1.py --dry-run
cat _migrate/copy_report.md
```

### 2. Copy to local staging D1 (Miniflare sqlite; no CF traffic)

```bash
python _scripts/migrate/neon_to_d1.py --sink wrangler-local
```

### 3. Copy to remote staging D1 (owner-approved deploy time only)

```bash
wrangler login                      # once
python _scripts/migrate/neon_to_d1.py --sink wrangler-remote-staging
```

### 4. Reconcile

```bash
python _scripts/migrate/reconcile.py --sink wrangler-local
# exit 0 = every table passed row-count + PK-coverage + sample-diff
```

### 5. Resume after a crash

Re-run the same `neon_to_d1.py` command. `state.json` picks up from the
last committed batch. Add `--tables ipo ipo_issue` to limit scope.

## Source-data anomalies

Per the owner's Point 12 ("no cleanup during migration"), if Neon data
looks suspicious (e.g. `band_lo > band_hi`, non-decimal in a NUMERIC field,
NULL ISIN + NULL name_norm), the copy script:

* NEVER silently rewrites the source value;
* writes the offending row to `_migrate/anomalies.jsonl` with `{table, pk, field, value, reason}`;
* skips only that row (not the whole table) so reconciliation surfaces the gap.

Those anomalies are reviewed and fixed **in Neon** by a separate, owner-
approved data repair PR — never by the migration.

## Rollback

* `_migrate/state.json` and the local `.wrangler` sqlite are safe to delete;
  `--fresh` re-triggers a full copy.
* Neon is never touched.
* No production Cloudflare resource is affected.
