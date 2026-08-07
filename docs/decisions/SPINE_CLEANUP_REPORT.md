# Spine cleanup evidence report

Status: CURRENT — PR #307 cleanup evidence retained as the phase-2 baseline.

## Baseline and tree

Base was owner-verified `46c1e42f60a9a1f2d5956afc0486049b2175d41d` on local branch
`work`, with a clean tree and no configured remote. Before cleanup: 1,055 tracked files,
41 route/page entrypoints, 285 Python files under `_scripts`, 46 under `pipeline`, and 34
docs. The cleanup removes one API and one page from the live Next.js surface while
preserving all three implementation files in `_archive` for rollback.

## Route classification

The five product surfaces and supporting auth/health/publication/operational APIs are
**IN_USE**. Admin access and settings are **IN_USE / ADMIN**. `/ipo` and `/` are
**COMPATIBILITY** redirects. The tracker page/API was **CONFIRMED_DEAD** as a product:
its only callers were its own client and one Admin link, it depended on deliberately
dropped `distraction_log`, and the approved product list excludes it. Existing archived
routes remain **SUPERSEDED**. No UNKNOWN or PROBABLY_DEAD route was deleted.

## Move and deletion manifest

| Current path | Destination | Classification | Callers checked | Risk / replacement |
|---|---|---|---|---|
| `app/api/tracker/route.ts` | `_archive/routes/api-tracker-route.ts.txt` | CONFIRMED_DEAD | app, components, lib, scripts, workflows, tests, docs | low; no product replacement |
| `app/dashboard/tracker/page.tsx` | `_archive/pages/dashboard-tracker-page.tsx.txt` | CONFIRMED_DEAD | navigation and route links | low; Admin remains |
| `app/dashboard/tracker/TrackerClient.tsx` | `_archive/pages/TrackerClient.tsx.txt` | CONFIRMED_DEAD | imports and fetch string | low; route removed |

There are no hard deletions and no renames beyond these archival moves. The archived
files are rollback copies, not live compatibility wrappers.

## DB boundary and legacy architecture

Public product pages are snapshot-backed. Direct web DB callers are limited to Admin,
auth/access, settings, broker credentials, and rate limiting; these are operational,
not public product reads. Production env lookup is deterministic `DATABASE_URL` in
touched web/runner boundaries. The dropped `audit_log` is not recreated: broker audit
uses structured Worker logs. All request-path and runner `CREATE/ALTER TABLE` statements
were removed; explicit `_scripts/migrations` and `schema_sync.py` retain migration
ownership. `ipo_consolidated` builders remain **COMPATIBILITY / IN_USE** because Admin's
`consolidate` job and lean pipeline still call consolidation. They were not moved.

The canonical document contract remains unchanged. `document_ledger` owns writes,
`documents.object_key` owns contract-v1 reads, and legacy rows without an object key are
isolated compatibility cases.

## D1 readiness

| Postgres dependency | Classification | Later work |
|---|---|---|
| ordinary SELECT/INSERT/UPDATE and simple `ON CONFLICT` | D1_COMPATIBLE | adapter parameter syntax |
| `ILIKE`, `NOW()`, intervals, timezone/date truncation, casts | MINOR_REWRITE | SQLite functions/collations |
| JSONB operators/types and ARRAY columns | MAJOR_REWRITE | JSON1/text normalization and join tables |
| SERIAL/BIGSERIAL, UUID defaults/behavior | MINOR_REWRITE | integer keys / application UUIDs |
| partial/concurrent indexes | MINOR_REWRITE | supported SQLite indexes; remove CONCURRENTLY |
| `FOR UPDATE SKIP LOCKED`, multi-statement transactions, psycopg connection semantics | MAJOR_REWRITE | D1-safe queue/transaction design |
| Postgres catalog introspection and dynamic schema repair | MAJOR_REWRITE | versioned D1 migrations |

Remaining debt is concentrated in legacy `_scripts`: direct psycopg connections,
Postgres SQL, V1/consolidated compatibility, and mixed research/diagnostics. Those files
are classified in `docs/repository-inventory.tsv`; uncertain scripts were intentionally
not moved or deleted. A later staged move should follow the recorded conceptual target,
with wrappers where cron/string callers require stable paths.

## Cost, runtime, rollback, and risks

Removing tracker and DB audit eliminates Neon wakes/writes from those requests. Removing
self-migration DDL reduces request latency/catalog work but means required operational
tables must be provisioned before use (as they already should be). No KV keys, bindings,
R2 objects, database rows, secrets, schedules, or deployment state changed. Rollback is
`git revert <cleanup-commit>`; the archived tracker copies also permit surgical restore.
No manual activation is required. Real production schema/publication/health checks were
not run because the task prohibits production mutation and no remote/secrets are present;
those remain owner gates after merge.
