# D1 local migration and acceptance runbook

Status: PROPOSED — PR #343 owner review

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

The survey emits only JSON path, occurrence count, primitive type frequencies, null frequency, and bounded representative values. It never infers units. Review the output, then create an owner-approved path file, for example:

```json
{
  "reviewed": true,
  "matrix_id": "$.reviewed.path.to.id",
  "name": "$.reviewed.path.to.company_name",
  "isin": "$.reviewed.path.to.isin",
  "ipo_issue": {
    "band_lo_rs": {"path": "$.reviewed.path.to.band_low", "unit": "rs"}
  }
}
```

These example strings describe the map format, not the archive's real paths. Every mapped decimal field must declare its evidence-approved source unit and, only when conversion is approved, its normalized unit. The migration refuses an identity-only map: at least one reviewed normalized bootstrap section is required. It supports issue/profile, ownership, objects, period financials, reservation/subscription rows, anchor summary/rows, peers, sourced KPI facts, and documents. Core inventories every file by path, SHA256, and byte size in its report but defers payload-body storage; malformed, unmapped, unit-unapproved, and ambiguous records are quarantined or reported raw-only.

## 2. Migrate into Wrangler local D1

```bash
NEON_READONLY_DATABASE_URL='…read-only role…' python tools/d1_migration.py \
  --scope core \
  --ipomatrix /owner/archive \
  --ipomatrix-map artifacts/ipomatrix-reviewed-map.json \
  --apply-local \
  --report artifacts/d1-migration.json
```

The Neon connection is `READ ONLY`, `REPEATABLE READ`, and rolled back at close. Named server-side cursors stream deterministic ordered queries without `OFFSET`. Decimal values become canonical decimal strings without passing through binary floating point. Unit anomalies go to `migration_quarantine`; they do not enter canonical fact tables.

Neon `ipo` is not assumed to contain `security_kind`. Migration derives it from the existing `source_facts(field='security_kind')` evidence. A single recognized value is retained, absent evidence defaults structurally to `EQUITY` with migration provenance, and conflicting/unknown evidence is quarantined.

## 3. Reconcile the Wrangler local database

```bash
python tools/d1_reconcile.py --wrangler-local \
  --scope core \
  --source-report artifacts/d1-migration.json \
  --output artifacts/d1-reconciliation.json
```

Core acceptance requires `zero_silent_loss=true`, core FK integrity, explicit core null
counts, and owner disposition of every quarantine row. Raw payload bodies, market, listing,
GMP, valuation, and decision tables are `DEFERRED`, not core failures. Run the core migration
a second time and reconcile again to prove idempotency without deleting existing state.

Idempotency never uses global SQLite `OR IGNORE` and the bulk path emits no per-row `SELECT` guard. Expected reruns use only declared deterministic conflict keys: the conflict handler no-ops when every supplied value is identical and deliberately aborts the batch if contents differ. Rows without an approved rerun key use plain `INSERT`, so unexpected CHECK/NOT NULL/UNIQUE violations also fail the bounded Wrangler batch.

## Owner staging execution (Windows-safe)

The Python runner selects `npx.cmd` on Windows and `npx` elsewhere. The owner-controlled
Wrangler config must bind only the already-created staging database. Remote mode requires
an explicit confirmation variable and never accepts the production app config implicitly.

```powershell
$env:AACAPITAL_D1_STAGING_CONFIRM = "YES"
python tools/d1_migration.py `
  --scope core `
  --ipomatrix C:\aacapital-input\ipomatrix `
  --ipomatrix-map C:\aacapital-input\ipomatrix-reviewed-map.json `
  --apply-staging `
  --wrangler-config C:\aacapital-input\wrangler.d1-staging.jsonc `
  --binding DB `
  --bulk-rows 500 `
  --max-statements 10000 `
  --max-sql-bytes 750000 `
  --max-file-bytes 8000000 `
  --report artifacts\d1-migration-staging.json

python tools/d1_reconcile.py `
  --scope core `
  --wrangler-staging `
  --wrangler-config C:\aacapital-input\wrangler.d1-staging.jsonc `
  --binding DB `
  --source-report artifacts\d1-migration-staging.json `
  --output artifacts\d1-reconciliation-staging.json
```

Repeat the identical two commands to prove deterministic rerun behavior. The runner keeps
the current D1 state: deterministic conflicts no-op only for identical contents, so no
database reset is needed. High-volume compatible rows are grouped into 500-row `VALUES`
statements. SQL files are UTF-8/LF, bounded by statement count and byte ceilings, emitted
in the approved FK order, and deleted after each Wrangler batch. Progress is reported by
table and source row count rather than by individual SQL statement.

`--scope core` queries and writes only the canonical IPO/fundamentals datasets plus
migration metadata. `raw_objects` payload bodies, `market_bars`, listing/pre-open observations, GMP,
valuation runs, and decision history are reported as `DEFERRED`; they cannot make core
reconciliation fail. A later `--scope market` run queries only Neon daily, 15-minute,
and listing-observation datasets and relies on the already-loaded `ipo` parent rows.
The owner-held 968-file archive remains Tier-A recovery evidence; the migration report
retains each archive path/SHA/size and normalized `source_facts` retain the source SHA.

## 4. Measure storage

Export or checkpoint the local Wrangler D1 and record its exact byte size. Project only from the real migrated unique-IPO count; do not divide by zero or treat an absent archive as a zero-byte archive. No R2 decision is authorized until this measurement exists.
