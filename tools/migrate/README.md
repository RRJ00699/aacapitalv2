# tools/migrate/ — Stage B / Stage C tooling (5-table D1 target)

Status: **AUTHORED, NOT EXECUTED.** These scripts are ready to run against
the existing `NEON_READONLY_DATABASE_URL` Actions secret and a staging D1,
but nothing here has been executed against your Cloudflare account or
Neon. Owner-run only.

## Files

| File | Purpose |
|---|---|
| `neon_to_d1.py` | Read-only Neon → staging D1 copy targeting the 5-table schema (ipo, fundamentals, market_observations, research_findings, source_facts). Deterministic, resumable, idempotent, observable, bounded, non-destructive. |
| `reconcile.py`  | Row-count + critical-field sample-diff report per D1 target (`_migrate/reconciliation_report.{md,json}`). |
| `requirements.txt` | Minimal Python deps. |

## Guarantees (locked)

1. **Neon is READ-ONLY.** Every session executes `SET default_transaction_read_only = on` before touching data.
2. **No writeable-DSN fallback.** The scripts REJECT startup if `NEON_READONLY_DATABASE_URL` is unset. `DATABASE_URL` is NEVER read.
3. **Staging D1 only.** Writes go through `wrangler d1 execute --env staging`; `--sink wrangler-local` is the default (Miniflare sqlite). `env.production` does not exist in `wrangler.jsonc`.
4. **Snapshot-stable pagination.** All Neon scans use **keyset pagination** on the source PK (or a composite tuple where PKs are compound). `LIMIT ... OFFSET N` is not used anywhere; concurrent Neon writes cannot shift page windows.
5. **True idempotency for `source_facts`.** Every row is rehashed into `observation_hash = sha256(field|value|source|document_sha|pipeline_version)` and inserted with `ON CONFLICT (ipo_id, field, observation_hash) DO NOTHING`. Retries with identical values converge to one row regardless of `fetched_at`.
6. **Secrets never migrate.** `kite_session`, `platform_config`, `access_requests`, `pipeline_steps`, `pipeline_failures`, `rule_validation_results` are explicitly excluded (§EXCLUDED_NEON_TABLES). Kite access tokens live in `wrangler secret`, not D1.
7. **Canonical identity normalisation.** `neon_to_d1.py:_norm_name` is a character-for-character port of `pipeline/fill_ipo.py:_norm`. `workers/ingest/src/identity.ts:normaliseName` matches. Any drift is a bug.
8. **Non-destructive.** Neon is never mutated. Staging D1 is drop-and-recreate ONLY when the operator passes `--fresh`.

## Runbook (owner only)

### 1. Dry run — report per-target Neon row counts, no writes

```bash
export NEON_READONLY_DATABASE_URL="postgresql://..."
python tools/migrate/neon_to_d1.py --dry-run
cat _migrate/copy_report.md
```

### 2. Copy to local staging D1 (Miniflare sqlite; no CF traffic)

```bash
python tools/migrate/neon_to_d1.py --sink wrangler-local
```

### 3. Copy to remote staging D1 (owner-approved deploy time only)

```bash
wrangler login
python tools/migrate/neon_to_d1.py --sink wrangler-remote-staging
```

### 4. Reconcile

```bash
python tools/migrate/reconcile.py --sink wrangler-local
# exit 0 = all 5 D1 targets passed row-count + critical-field sample-diff
```

### 5. Resume after a crash

Re-run the same command. `_migrate/state.json` picks up per-target keyset
cursors from the last committed batch. Add `--targets ipo fundamentals` to
limit scope.

## Excluded Neon tables (never migrate to D1 by design)

| Neon table | Reason | Where it lives instead |
|---|---|---|
| `kite_session` | Contains `access_token`, a live secret | `wrangler secret put ...` |
| `platform_config` | Runtime knobs | Cloudflare Worker `vars` / secret store |
| `access_requests` | Auth control-plane | KV under `access:<email>` |
| `pipeline_steps` | Pipeline observability | KV `pipeline-health:v1` snapshot |
| `pipeline_failures` | Pipeline observability | KV `pipeline-health:v1` snapshot |
| `rule_validation_results` | Feature-flagged research artifact | KV `rule-validation:v1` snapshot |

## Source-data anomalies

Per the owner's Point 12 ("no cleanup during migration"), if Neon data
looks suspicious (band_lo > band_hi, non-decimal in a NUMERIC field,
unresolvable `company_name` → `ipo.id`, ...), the copy script:

* NEVER silently rewrites the source value;
* writes the offending row to `_migrate/anomalies.jsonl` with `{target, key, reason, extra}`;
* skips only that row so reconciliation surfaces the gap.

Those anomalies are reviewed and fixed **in Neon** by a separate,
owner-approved data repair PR — never by the migration.

## Rollback

* `_migrate/state.json` and the local `.wrangler` sqlite are safe to delete; `--fresh` re-triggers a full copy.
* Neon is never touched.
* No production Cloudflare resource is affected.
