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
Six duplicate files met that bar and were deleted after their live root `_scripts` owners were verified; UNKNOWN files remain untouched.

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

**VERIFIED before/after:** tracked files 1,072 → 1,067; production-oriented files
486 → 425; `_scripts` files 319 → 264; `pipeline/_scripts` files 6 → 0.
Research and diagnostic implementations moved out of production; moves preserve history.

### Exact move manifest

| Old path | New path | Classification | Caller evidence / risk |
|---|---|---|---|
| `_scripts/build_ipo_consolidated.py` | `compatibility/consolidated/build_ipo_consolidated.py` | COMPATIBILITY | Lean pipeline/Admin/tests updated to explicit compatibility path; production behavior retained. |
| `_scripts/build_ipo_consolidated_v2.py` | `compatibility/consolidated/build_ipo_consolidated_v2.py` | COMPATIBILITY | Lean pipeline/Admin/tests updated to explicit compatibility path; production behavior retained. |
| `_scripts/consolidate_master.py` | `compatibility/consolidated/consolidate_master.py` | COMPATIBILITY | Lean pipeline/Admin/tests updated to explicit compatibility path; production behavior retained. |
| `docs/ARCHITECTURE_DECISIONS.md` | `docs/architecture/ARCHITECTURE_DECISIONS.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/ARCHITECTURE_STATE.md` | `docs/architecture/ARCHITECTURE_STATE.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/ASSET_LIGHT_ARCHITECTURE.md` | `docs/architecture/ASSET_LIGHT_ARCHITECTURE.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/CURRENT_STATE.md` | `docs/architecture/CURRENT_STATE.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/AACAPITAL_KICKSTART_AUDIT.md` | `docs/archive/AACAPITAL_KICKSTART_AUDIT.md` | SUPERSEDED | Historical evidence only; references updated. |
| `docs/CURRENT_PR_IMPLEMENTATION_AUDIT.md` | `docs/archive/CURRENT_PR_IMPLEMENTATION_AUDIT.md` | SUPERSEDED | Historical evidence only; references updated. |
| `docs/PIPELINE_RUNTIME_AUDIT.md` | `docs/archive/PIPELINE_RUNTIME_AUDIT.md` | SUPERSEDED | Historical evidence only; references updated. |
| `docs/SESSION_2026-07-24.md` | `docs/archive/SESSION_2026-07-24.md` | SUPERSEDED | Historical evidence only; references updated. |
| `docs/TEST_CONTRACT_AUDIT.md` | `docs/archive/TEST_CONTRACT_AUDIT.md` | SUPERSEDED | Historical evidence only; references updated. |
| `docs/FRUSTRATION_TRACKER.md` | `docs/runbooks/FRUSTRATION_TRACKER.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/NSE_PREOPEN_CAPTURE.md` | `docs/runbooks/NSE_PREOPEN_CAPTURE.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/UAT_FRAMEWORK.md` | `docs/runbooks/UAT_FRAMEWORK.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/UAT_TRACKER.md` | `docs/runbooks/UAT_TRACKER.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/VM_CRON_RUNBOOK.md` | `docs/runbooks/VM_CRON_RUNBOOK.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/AACAPITAL_PRODUCT_CONTRACT.md` | `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/DETAILS_AND_REVIEW.md` | `docs/specifications/DETAILS_AND_REVIEW.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/PROVENANCE_DESIGN.md` | `docs/specifications/PROVENANCE_DESIGN.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/QUALITY_SCORE_SPEC.md` | `docs/specifications/QUALITY_SCORE_SPEC.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/R2_DOCUMENT_CONTRACT.md` | `docs/specifications/R2_DOCUMENT_CONTRACT.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/UI_EVIDENCE_CONTRACT.md` | `docs/specifications/UI_EVIDENCE_CONTRACT.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/UI_REQUIREMENTS.md` | `docs/specifications/UI_REQUIREMENTS.md` | IN_USE | Current documentation hierarchy; references updated. |
| `docs/V2_SCHEMA.md` | `docs/specifications/V2_SCHEMA.md` | IN_USE | Current documentation hierarchy; references updated. |
| `_scripts/analyze_brlm_rate.py` | `research/backtests/analyze_brlm_rate.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/analyze_junk.py` | `research/backtests/analyze_junk.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/analyze_qib_pattern.py` | `research/backtests/analyze_qib_pattern.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/anchor_quality_backtest.py` | `research/backtests/anchor_quality_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/backfill_anchors_analysis.py` | `research/backtests/backfill_anchors_analysis.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/backtest_dna_drawdown.py` | `research/backtests/backtest_dna_drawdown.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/backtest_journey_exits.py` | `research/backtests/backtest_journey_exits.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/backtest_quality_score.py` | `research/backtests/backtest_quality_score.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/backtest_regime.py` | `research/backtests/backtest_regime.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/base_backtest.py` | `research/backtests/base_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/cross_backtest.py` | `research/backtests/cross_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/exit_backtest.py` | `research/backtests/exit_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/exit_backtest_v2.py` | `research/backtests/exit_backtest_v2.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/exit_backtest_v3.py` | `research/backtests/exit_backtest_v3.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/exit_rule_backtest.py` | `research/backtests/exit_rule_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/factor_backtest.py` | `research/backtests/factor_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/flags_horizon_backtest.py` | `research/backtests/flags_horizon_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/analyze_listing_day.py` | `research/backtests/ipo/analyze_listing_day.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/backtest_dip_defense.py` | `research/backtests/ipo/backtest_dip_defense.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/backtest_recovery_classes.py` | `research/backtests/ipo/backtest_recovery_classes.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/backtest_regime_split.py` | `research/backtests/ipo/backtest_regime_split.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/backtest_strategies.py` | `research/backtests/ipo/backtest_strategies.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/backtest_thesis.py` | `research/backtests/ipo/backtest_thesis.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ipo/export_ipo_backtest.py` | `research/backtests/ipo/export_ipo_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ml/__init__.py` | `research/backtests/ml/__init__.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/ofs_backtest.py` | `research/backtests/ofs_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/pattern_mining.py` | `research/backtests/pattern_mining.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/promoter_backtest.py` | `research/backtests/promoter_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/real_return_analysis.py` | `research/backtests/real_return_analysis.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/regime_mid_backtest.py` | `research/backtests/regime_mid_backtest.py` | RESEARCH | No production caller; documentation paths updated; offline import/runtime risk only. |
| `_scripts/audit_candles.py` | `tools/diagnostics/audit_candles.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_candle_storage.py` | `tools/diagnostics/check_candle_storage.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_consolidated_row.py` | `tools/diagnostics/check_consolidated_row.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_data_contract.py` | `tools/diagnostics/check_data_contract.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_date_sanity.py` | `tools/diagnostics/check_date_sanity.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_dupes.py` | `tools/diagnostics/check_dupes.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_fairvalue_data.py` | `tools/diagnostics/check_fairvalue_data.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_freshness.py` | `tools/diagnostics/check_freshness.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_fv_table.py` | `tools/diagnostics/check_fv_table.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_grades.py` | `tools/diagnostics/check_grades.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_ids.py` | `tools/diagnostics/check_ids.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_ingest_gain.py` | `tools/diagnostics/check_ingest_gain.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_laser_rhp.py` | `tools/diagnostics/check_laser_rhp.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_missing_scores.py` | `tools/diagnostics/check_missing_scores.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_neon_schema.py` | `tools/diagnostics/check_neon_schema.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_value_sanity.py` | `tools/diagnostics/check_value_sanity.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/check_write_constraints.py` | `tools/diagnostics/check_write_constraints.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/diagnose_neon_compute.py` | `tools/diagnostics/diagnose_neon_compute.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/ipo/verify_resolved_symbols.py` | `tools/diagnostics/ipo/verify_resolved_symbols.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/probe_ipomatrix.py` | `tools/diagnostics/probe_ipomatrix.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/verify_laser_live.py` | `tools/diagnostics/verify_laser_live.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |
| `_scripts/verify_live_feed.py` | `tools/diagnostics/verify_live_feed.py` | DIAGNOSTIC | Operator-only; all string/docs/test references updated; no scheduled caller. |

| `_scripts/archive/screener-pipeline.ts.txt` | `_archive/_scripts/screener-pipeline.ts.txt` | SUPERSEDED | No runtime caller; already inert `.txt` archive; moved out of production scripts. |

### Exact deletion manifest

| Deleted path | Classification | Caller evidence | Replacement | Rollback |
|---|---|---|---|---|
| `pipeline/_scripts/download_sbi_notes.py` | CONFIRMED_DEAD duplicate | Workflows, cron, Admin runner and imports resolve `_scripts/download_sbi_notes.py`; stale-path contract rejects old callers. | `_scripts/download_sbi_notes.py` | Revert cleanup commit. |
| `pipeline/_scripts/download_sebi_rhps_playwright.py` | CONFIRMED_DEAD duplicate | Workflows, cron, Admin runner and imports resolve `_scripts/download_sebi_rhps_playwright.py`; stale-path contract rejects old callers. | `_scripts/download_sebi_rhps_playwright.py` | Revert cleanup commit. |
| `pipeline/_scripts/kite_connect.py` | CONFIRMED_DEAD duplicate | Workflows, cron, Admin runner and imports resolve `_scripts/kite_connect.py`; stale-path contract rejects old callers. | `_scripts/kite_connect.py` | Revert cleanup commit. |
| `pipeline/_scripts/parse_sbi_notes.py` | CONFIRMED_DEAD duplicate | Workflows, cron, Admin runner and imports resolve `_scripts/parse_sbi_notes.py`; stale-path contract rejects old callers. | `_scripts/parse_sbi_notes.py` | Revert cleanup commit. |
| `pipeline/_scripts/refresh_kite_token.py` | CONFIRMED_DEAD duplicate | Workflows, cron, Admin runner and imports resolve `_scripts/refresh_kite_token.py`; stale-path contract rejects old callers. | `_scripts/refresh_kite_token.py` | Revert cleanup commit. |
| `pipeline/_scripts/update_kite_token.py` | CONFIRMED_DEAD duplicate | Workflows, cron, Admin runner and imports resolve `_scripts/update_kite_token.py`; stale-path contract rejects old callers. | `_scripts/update_kite_token.py` | Revert cleanup commit. |

Compatibility wrappers retained: **none for the deleted duplicate tree**. The existing
root redirects remain product compatibility routes. Quality-factor calculations now have one production owner in `_scripts/lib/quality_factors.py`; the backtest consumes it rather than owning a duplicate. Consolidated/V1 implementations
are visibly isolated under `compatibility/consolidated`; Admin and the lean pipeline
point there directly rather than through shadow copies.

Runtime/cost: zero public DB wake added. Moving offline research/diagnostics changes no
scheduled runtime. Duplicate removal changes no live entrypoint. Cloudflare bindings,
KV keys, R2 objects, workflows, secrets, schedules, and deployments are unchanged.
Rollback is `git revert <cleanup-head>`; no data/object rollback is needed.

Known risks: operator bookmarks using old research/diagnostic paths must use the new
manifest paths. Real schema smoke, real publication, workflow dispatch, production
health, and browser acceptance remain **UNKNOWN** without owner credentials/access.
Manual activation: none.

**MERGE RECOMMENDATION: UNKNOWN pending all local gates and owner-run production-parity
checks.** The repository reduction is now material, but tests alone do not establish
production health.
