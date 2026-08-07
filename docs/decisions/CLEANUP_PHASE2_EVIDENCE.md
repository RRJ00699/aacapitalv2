# Cleanup phase 2 evidence and D1 handoff

Status: CURRENT — read-only repository reset evidence as of 2026-08-07.

Every statement in this document is labelled **VERIFIED**, **INFERENCE**, or
**UNKNOWN**. No database, R2, KV, Cloudflare, deployment, or paid-model mutation was
performed while preparing it.

## 1. Revision, size, and structure

**VERIFIED:** The owner merge commit for PR #308 is
`ee76422d1810541b338f81afd867e5b9f817ffaf`. The checkout had 1,071 tracked files.
There was no configured remote and therefore no `origin/main` ref to fetch or compare.
The working branch is `refactor/aacapital-cleanup-phase2`.

**VERIFIED:** The production-oriented top-level spine is `app`, `components`, `lib`,
`pipeline`, `_scripts`, `workers`, `tests`, `uat`, and `docs`. Historical code is
isolated in `_archive`; disabled automation is in `.github/workflows_disabled`.
`_scripts` remains intentionally mixed because most files are UNKNOWN or
PROBABLY_DEAD and cannot safely be moved without runtime-caller evidence.

The machine-readable per-file classification is `docs/repository-inventory.tsv`.
CONFIRMED_DEAD means all import, subprocess, string path, package script, cron, Admin,
workflow, test, snapshot, route-link, documentation, and runtime callers were checked.
No phase-2 file met that bar, so this change deletes nothing.

## 2. Complete route map

| Route | Surface / role | Classification | Data behavior |
|---|---|---|---|
| `/`, `/ipo` | Command redirects | COMPATIBILITY | redirect only |
| `/dashboard/ipo2` | Command Center | IN_USE | KV snapshot |
| `/dashboard/ipo2/details/[isin]` | Complete Details | IN_USE | KV snapshot |
| Command live state + `/api/ipo/live-preopen`, `tick-feed`, `cum-volume` | Listing Day Live | IN_USE | KV/broker operational data |
| `/dashboard/journey`, `/api/ipo/journey` | Journey | IN_USE | versioned KV snapshot |
| `/dashboard/admin`, `/api/admin/*` | Admin | IN_USE | authenticated operations |
| `/login`, `/api/auth/*`, `/api/access-note` | auth/access | IN_USE | auth and access operations |
| `/api/health` | health | IN_USE | health only |
| `/api/admin/snapshots` | publication | IN_USE | validates payload and writes KV; no DB import |
| `/api/broker/*` | Kite operations | IN_USE | broker proxy |
| `/api/ipo-command`, `/api/ipo/index`, `/api/ipo/details/[isin]` | snapshot consumers | IN_USE | KV only |
| `/api/ipo/monitor` | live operational monitor | IN_USE | bounded operational state |
| `/api/pipeline/trigger` | approved pipeline operation | IN_USE | authenticated dispatch |
| `/dashboard/access`, `/dashboard/settings`, `/api/settings` | Admin sub-surfaces | IN_USE | authenticated operational configuration |
| `/api/market/global`, `/api/market/snapshot` | Command supporting context | IN_USE | snapshot/cache |

**VERIFIED:** The previously removed tracker page/API remains archived and unreferenced.
Static contracts reject DB imports in public pages, schema DDL in web code, and DB use
in the publication endpoint.

## 3. Pipeline and job map

| Name | Entrypoint / caller | DB | Network | R2/KV | Paid API | Output / consumer |
|---|---|---|---|---|---|---|
| canonical lifecycle | `pipeline/cron.py --run`; manual workflow | writer | SEBI/NSE/SBI/Kite | R2 + publication | bounded extraction | canonical facts and all public snapshots |
| NSE planner | `pipeline/nse_lifecycle.py`; Admin | writer | NSE | none | none | lifecycle work plan |
| pre-open | `pipeline/capture_preopen.py`; cron workflow | writer | NSE | downstream KV | none | Live |
| snapshot build/publish | `pipeline/publish_snapshot_with_ledger.py`; pipeline | read | publication HTTP | versioned CACHE | none | Command/Details/Live/Journey |
| SBI note lane | `sbi-notes.yml`; pipeline scripts | writer | SBI | document contract | configured extraction only | SBI facts |
| VM repair queue | `_scripts/job_runner.py`; minute cron + `admin:jobs-pending` gate | writer | job-specific | JOB_FLAG | job-specific | Admin operations |
| Kite explicit modes | npm `prod:*` | writer | Kite | none | none | candles/operational records |

**VERIFIED:** Admin API, Admin UI, and runner job keys are contract-tested for exact
equality. Subprocess/workflow paths are also required to exist. The detailed 22-key
catalog remains in `docs/runbooks/PRODUCTION_JOBS.md`; no job was removed without
caller evidence.

## 4. DB caller and environment map

| Boundary | Allowed credential | Classification |
|---|---|---|
| production pipeline, Admin operations, offline writers | `DATABASE_URL` | writer |
| explicit schema smoke / owner read-only inspection | `NEON_READONLY_DATABASE_URL` | read-only |
| public Command/Details/Live/Journey consumers | none | zero-wake |
| `NEON_DATABASE_URL` | none in production | legacy tests/archive only |

**VERIFIED:** The production `app`, `lib`, and `pipeline` trees contain no
`NEON_DATABASE_URL` fallback. Snapshot schema smoke has an explicit read-only URL;
normal publication building requires `DATABASE_URL`. Direct connections still exist in
legacy `_scripts`; classifying and adapting them is remaining debt, not grounds for an
unsafe mass edit.

## 5. Documents, extraction, and fact ownership

**VERIFIED document map:** official PDF → `pipeline.document_ledger` → immutable
`pipeline.r2.put_document_if_absent` → `documents.object_key` ledger row. Exact-key
reads use the approved contract. No alternate production `put_document` caller exists.

**VERIFIED extraction map:** RHP uses `rhp_sections → rhp_sonnet → rhp_writer`; SBI uses
the approved SBI extraction lane; Anchor is a `documents` ledger type. Old regex and
vendor scripts are SUPERSEDED or COMPATIBILITY and are not declared canonical.

| Fact domain | Canonical owner | Consumers |
|---|---|---|
| identity / issue | `ipo`, `ipo_issue` | profile/snapshots |
| statements and atomic evidence | `financial_statements`, `source_facts` | canonical-inputs |
| subscriptions | `subscription_snapshots` | Command/Details |
| valuation and score | `valuation`, `pipeline/score_engine.py` | canonical-inputs/profile |
| extracted findings | `rhp_findings`, `insights` | profile/intelligence |
| listing state | `listing_observations`, `listing_outcomes` | Live/Journey |
| source documents | `documents` | extractors/audit |
| economic EPS/P/E/net-debt/fair-value/MOS | `lib/intelligence/ipo-profile.ts` fed by `canonical-inputs.ts` | Command + Details |

**VERIFIED:** Command and Details both import the same canonical input builder. V1
`ipo_consolidated`, both consolidated builders, IPOMatrix/Chittorgarh ingestion, and old
snapshot layouts are not a second canonical architecture: remaining callers make them
COMPATIBILITY or SUPERSEDED. **UNKNOWN:** their final removal date; removing them now
would break the Admin `consolidate` compatibility job and historical tooling.

## 6. Cloudflare and snapshot contract

**VERIFIED:** `CACHE` and `JOB_FLAG` share namespace
`71fc0e8060ce4cad919b58d35b9681e2`. Snapshot keys use `snapshot:<product>:<version>`
plus `:active` / `:previous` pointers. The runner flag is `admin:jobs-pending`.
Collision risk is low because prefixes do not overlap. Quota, permissions, and blast
radius are coupled. **INFERENCE:** split JOB_FLAG into its own namespace during a later
operational migration; do not mix that binding mutation into repository cleanup.
The document bucket is pipeline-secret configured and has no public app binding.

## 7. Table ownership inventory (read-only, code-derived)

| Table/family | Class | Owner/caller evidence |
|---|---|---|
| `ipo`, `ipo_issue`, `documents`, `financial_statements`, `source_facts`, `subscription_snapshots`, `valuation`, `rhp_findings`, `insights`, `listing_observations`, `listing_outcomes`, `market_candles*`, `decisions` | CANONICAL_ACTIVE | pipeline writers and snapshot builders |
| `job_runs`, `pipeline_*`, `platform_config`, access/auth tables | OPERATIONAL_ACTIVE | Admin, runner, auth, lifecycle |
| `ipo_consolidated`, `ipo_intelligence`, `ipo_golden`, `ipo_master`, `ipo_rhp_intel` | COMPATIBILITY | consolidated job / legacy scripts; never canonical profile ownership |
| `market_candles_15m` | CANONICAL_ACTIVE | listing capture/Journey; successor to removed intraday layout |
| `ipo_clean_backup` | PROBABLY_DEAD | no canonical owner; retain pending real catalog/caller audit |
| `local_cache` | UNKNOWN | name/reference evidence insufficient; retain |
| `migration_merge_log` | OPERATIONAL_ACTIVE | migration audit tooling |
| `neon_*` performance/catalog tables | NEON_INTERNAL | Neon-managed, application must not own/migrate |

**UNKNOWN:** The live database's full table list. No schema query was made because no
read-only production credential was supplied. This classification is a repository
inventory and must be reconciled against a future owner-run read-only catalog export.
No table is dropped or modified.

## 8. Finite D1 readiness matrix

| PostgreSQL behavior | Rewrite | D1 boundary |
|---|---|---|
| simple CRUD and simple `ON CONFLICT` | D1_COMPATIBLE | adapter placeholders/types |
| JSONB storage/operators | MAJOR_REWRITE | JSON text/JSON1 or normalized children |
| ARRAY | MAJOR_REWRITE | JSON or join table |
| BIGSERIAL / UUID defaults | MINOR_REWRITE | integer key/application UUID |
| ILIKE | MINOR_REWRITE | normalized/collated LIKE |
| DISTINCT ON | MAJOR_REWRITE | window function/subquery |
| partial indexes | MINOR_REWRITE | SQLite partial-index verification |
| CREATE INDEX CONCURRENTLY | MINOR_REWRITE | offline migration without keyword |
| INTERVAL / NOW() / `to_date` / timezone behavior | MINOR_REWRITE | explicit ISO UTC + SQLite functions |
| casts and PostgreSQL operators | MINOR_REWRITE | adapter query rewrite |
| transaction locking / `FOR UPDATE SKIP LOCKED` | MAJOR_REWRITE | queue design / Durable Object if needed |
| LATERAL joins | MAJOR_REWRITE | correlated subquery or preaggregation |

**INFERENCE:** Future boundaries should be (1) canonical IPO/profile facts, (2)
operational lifecycle/Admin queue, (3) market/Journey time series, and (4) publication
metadata. Documents remain in R2 with ledger metadata in the canonical-facts boundary.
Do not migrate research/compatibility tables until a consumer explicitly claims them.

## 9. Change manifest, impact, and rollback

- Files moved/renamed/archived/deleted: **none**. UNKNOWN and PROBABLY_DEAD files were
  retained. Existing PR #307 archival remains the rollback record for tracker removal.
- Compatibility wrappers retained: root redirects and all evidenced Admin/script
  entrypoints.
- Legacy architectures removed in phase 2: the remaining production
  `NEON_DATABASE_URL` fallback; no data architecture was redesigned.
- Runtime/cost: zero public DB wake added; deterministic credential selection prevents
  accidental writer use of an old Neon alias. Tests are static/offline.
- Cloudflare/GitHub: no binding, workflow, secret, schedule, deployment, or production
  state changed.
- Rollback: revert the cleanup commit. No data/object rollback is needed.
- Known risks: real schema smoke, real publication, workflow dispatch, production
  health, and browser acceptance are **UNKNOWN** until an owner runs them with approved
  read-only/non-production credentials after merge.
- Manual activation: none.

**MERGE RECOMMENDATION: UNKNOWN pending all local gates and owner-run production-parity
checks.** Passing local tests alone does not establish production health.
