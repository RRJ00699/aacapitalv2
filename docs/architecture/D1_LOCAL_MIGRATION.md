# D1 local migration and acceptance runbook

## Status and PR ownership

PR **#343** is the replacement candidate for the D1 migration design. If #343 is accepted, PR **#342 must not be merged**. This branch performs no remote Cloudflare operation and has no remote mode.

## Cost and risk gate

The commands below read Neon through `NEON_READONLY_DATABASE_URL`, write only Wrangler's local Miniflare D1 state, and make no model/API calls. They do not publish KV, deploy Workers, create D1 databases, or modify Neon. Start from an empty local state for acceptance so destination equality cannot be confused with an earlier run.

## 1. Survey the immutable IPO Matrix archive

```bash
python tools/d1_migration.py \
  --ipomatrix /owner/archive \
  --survey artifacts/ipomatrix-field-survey.json
```

The survey emits only JSON path, occurrence count, inferred JSON type(s), and bounded sample values. It never infers units. Review the output, then create an owner-approved path file, for example:

```json
{
  "matrix_id": "$.reviewed.path.to.id",
  "name": "$.reviewed.path.to.company_name",
  "isin": "$.reviewed.path.to.isin"
}
```

These example strings describe the map format, not the archive's real paths. The migration refuses normalized IPO Matrix identity loading when archive files are supplied without this reviewed map. Every valid or malformed raw object is nevertheless represented by SHA256 and immutable payload bytes; malformed or unmapped identities are quarantined.

## 2. Migrate into Wrangler local D1

```bash
rm -rf d1/.wrangler/state
NEON_READONLY_DATABASE_URL='…read-only role…' python tools/d1_migration.py \
  --ipomatrix /owner/archive \
  --ipomatrix-map artifacts/ipomatrix-reviewed-map.json \
  --apply-local \
  --report artifacts/d1-migration.json
```

The Neon connection is `READ ONLY`, `REPEATABLE READ`, and rolled back at close. Named server-side cursors stream deterministic ordered queries without `OFFSET`. Decimal values become canonical decimal strings without passing through binary floating point. Unit anomalies go to `migration_quarantine`; they do not enter canonical fact tables.

## 3. Reconcile the Wrangler local database

```bash
python tools/d1_reconcile.py --wrangler-local \
  --source-report artifacts/d1-migration.json \
  --output artifacts/d1-reconciliation.json
```

Acceptance requires `zero_silent_loss=true`, exact daily/15-minute/pre-open source comparisons, raw-object equality, zero identity/fingerprint duplicates, explicit null counts/ranges, and owner disposition of every quarantine row. Run the migration a second time and reconcile again to prove idempotency.

## 4. Measure storage

Export or checkpoint the local Wrangler D1 and record its exact byte size. Project only from the real migrated unique-IPO count; do not divide by zero or treat an absent archive as a zero-byte archive. No R2 decision is authorized until this measurement exists.
