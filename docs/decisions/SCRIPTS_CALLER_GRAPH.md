# Authoritative `_scripts` Caller Graph

**Status: CURRENT**

**Command:**

```text
python tools/scripts_caller_graph.py --production
```

The totals below are the exact output of that command. The analyzer reads source without importing or executing production modules.

## Root caller set

- `_scripts/compute_quality_score.py` — _scripts/job_runner.py JOBS[quality]
- `_scripts/compute_verdicts.py` — _scripts/job_runner.py JOBS[verdicts]
- `_scripts/derive_peer_pe_from_notes.py` — _scripts/job_runner.py JOBS[peer_pe_notes]
- `_scripts/download_sbi_notes.py` — _scripts/job_runner.py JOBS[sbi_download]; enabled workflow: .github/workflows/sbi-notes.yml; pipeline path/import: pipeline/cron.py
- `_scripts/download_sebi_rhps_playwright.py` — pipeline path/import: pipeline/cron.py
- `_scripts/fetch_ipo_news.py` — _scripts/job_runner.py JOBS[news]
- `_scripts/fetch_peer_pe.py` — _scripts/job_runner.py JOBS[peer_pe]
- `_scripts/git_sync.py` — _scripts/job_runner.py JOBS[sync]
- `_scripts/ipo_score.py` — _scripts/job_runner.py JOBS[score]
- `_scripts/ipomatrix_ingest.py` — _scripts/job_runner.py JOBS[ipomatrix]
- `_scripts/job_runner.py` — documented VM cron entrypoint
- `_scripts/kite_connect.py` — pipeline import: pipeline/capture_preopen.py; pipeline import: pipeline/kite_fetch.py; pipeline path/import: pipeline/kite_fetch.py
- `_scripts/market_breadth.py` — _scripts/job_runner.py JOBS[breadth]
- `_scripts/parse_sbi_notes.py` — _scripts/job_runner.py JOBS[sbi_parse]; enabled workflow: .github/workflows/sbi-notes.yml
- `_scripts/prod/kite_sync_and_predict.py` — package.json script: package.json
- `_scripts/refresh_kite_token.py` — _scripts/job_runner.py JOBS[token]; pipeline import: pipeline/kite_fetch.py; pipeline path/import: pipeline/cron.py; pipeline path/import: pipeline/kite_fetch.py
- `_scripts/run_ipo_pipeline_lean.py` — _scripts/job_runner.py JOBS[pipeline]; _scripts/job_runner.py JOBS[pipeline_weekly]
- `_scripts/sbi_haiku_extract.py` — _scripts/job_runner.py JOBS[sbi_haiku]
- `_scripts/schema_sync.py` — _scripts/job_runner.py JOBS[schema]
- `_scripts/scrape_investorgain_gmp.py` — _scripts/job_runner.py JOBS[gmp]
- `_scripts/set-password.mjs` — package.json script: package.json
- `_scripts/smoke_probe.py` — _scripts/job_runner.py JOBS[smoke]
- `_scripts/vm_verify.py` — _scripts/job_runner.py JOBS[vm_verify]

## Recognized edge types

- `python import`
- `relative script argument`
- `script path`
- `shell/script path`

Python AST handling covers `import`, `from ... import ...`, constants passed to wrapper functions such as `step()`, subprocess/Popen/check-call/check-output argument lists, Python-executable command arrays, `os.system` command strings, explicit `_scripts/...` paths, bare script names resolved relative to `_scripts`, and shell/batch/PowerShell references. Reachability is recursively closed over every discovered edge. Docstrings and comments are excluded from executable path evidence.

## Production totals

| Measure | Count |
|---|---:|
| TOTAL | 54 |
| KEEP | 54 |
| UNREACHABLE | 0 |
| UNKNOWN | 0 |
| V1_TOTAL | 36 |
| KEPT_WITH_V1 | 36 |
| UNREACHABLE_WITH_V1 | 0 |

Before the Phase 4B quarantine, the same production graph reported TOTAL=174, KEEP=54, UNREACHABLE=120, V1_TOTAL=122, KEPT_WITH_V1=36, and UNREACHABLE_WITH_V1=86. The 120 mechanically unreachable files were moved without source rewrites.

Production mode excludes exactly `_scripts/tests/**` and tracked files whose suffix is not in the executable/source suffix allowlist `.py`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.sh`, `.ps1`, `.bat`, `.cmd`, and `.sql`. At this commit the latter exclusion is precisely `_scripts/.deploy-trigger`, `_scripts/VERIFY_V2.md`, `_scripts/ipo_autoupdate.patch`, `_scripts/ipo_data_contract.csv`, and `_scripts/prod/__pycache__/env_utils.cpython-312.pyc`. The production view now contains only the 54 caller-evidenced KEEP files; quarantined files are outside `_scripts`.

## Raw all-tracked totals

| Measure | Count |
|---|---:|
| TOTAL | 267 |
| KEEP | 56 |
| UNREACHABLE | 211 |
| UNKNOWN | 0 |
| V1_TOTAL | 154 |
| KEPT_WITH_V1 | 36 |
| UNREACHABLE_WITH_V1 | 118 |

## Limitations and backstops

- Conservative string matching may over-keep files when a script-looking string is not executed.
- F-string and other dynamically assembled paths may be under-detected.
- Path-existence contracts and caller contracts remain the backstop; these limitations are not resolved by this graph.

## Complete `run_ipo_pipeline_lean.py` dependency closure

The closure contains 47 production files, including the root:

- `_scripts/backfill_eps_post.py`
- `_scripts/backfill_market_regimes.py`
- `_scripts/backfill_master_computables.py`
- `_scripts/backup_critical_tables.py`
- `_scripts/compute_d10.py`
- `_scripts/compute_flags.py`
- `_scripts/compute_journal_outcomes.py`
- `_scripts/compute_quality_score.py`
- `_scripts/compute_verdicts.py`
- `_scripts/derive_peer_pe_from_notes.py`
- `_scripts/download_sbi_notes.py`
- `_scripts/engines/market_regime.py`
- `_scripts/fetch_delivery_bhavcopy.py`
- `_scripts/fetch_ipo_news.py`
- `_scripts/fetch_new_rhps.py`
- `_scripts/fetch_peer_pe.py`
- `_scripts/fill_listing_open_from_candles.py`
- `_scripts/insights_fanout.py`
- `_scripts/ipo/backfill_ipo_ohlc.py`
- `_scripts/ipo/fetch_nse_ipos.py`
- `_scripts/ipo/ipo_play_selector.py`
- `_scripts/ipo/refresh_gmp.py`
- `_scripts/ipo_score.py`
- `_scripts/ipomatrix_ingest.py`
- `_scripts/kite_connect.py`
- `_scripts/lib/canon.py`
- `_scripts/lib/notify.py`
- `_scripts/lib/quality_factors.py`
- `_scripts/lib/stage_state.py`
- `_scripts/lineage_registry.py`
- `_scripts/nse_preopen_capture.py`
- `_scripts/parse_sbi_notes.py`
- `_scripts/purge_candles_after_lockin.py`
- `_scripts/reconcile_listing_dates.py`
- `_scripts/refresh_kite_token.py`
- `_scripts/rhp_auto.py`
- `_scripts/rhp_sections.py`
- `_scripts/rhp_sonnet.py`
- `_scripts/rhp_sonnet_store.py`
- `_scripts/run_ipo_pipeline_lean.py`
- `_scripts/sbi_haiku_extract.py`
- `_scripts/schema_sync.py`
- `_scripts/scrape_investorgain_gmp.py`
- `_scripts/smoke_probe.py`
- `_scripts/sync_inwindow_candles.py`
- `_scripts/sync_issue_details.py`
- `_scripts/sync_trade_journal.py`

### Complete dependency edges inside the lean closure

- `_scripts/backfill_market_regimes.py` → `_scripts/engines/market_regime.py` (python import)
- `_scripts/backfill_market_regimes.py` → `_scripts/kite_connect.py` (python import)
- `_scripts/backfill_market_regimes.py` → `_scripts/kite_connect.py` (relative script argument)
- `_scripts/compute_quality_score.py` → `_scripts/lib/quality_factors.py` (python import)
- `_scripts/engines/market_regime.py` → `_scripts/refresh_kite_token.py` (relative script argument)
- `_scripts/fetch_new_rhps.py` → `_scripts/lib/canon.py` (python import)
- `_scripts/fetch_new_rhps.py` → `_scripts/lib/notify.py` (python import)
- `_scripts/fetch_new_rhps.py` → `_scripts/lib/stage_state.py` (python import)
- `_scripts/ipo/backfill_ipo_ohlc.py` → `_scripts/refresh_kite_token.py` (script path)
- `_scripts/ipo/fetch_nse_ipos.py` → `_scripts/ipo/ipo_play_selector.py` (relative script argument)
- `_scripts/ipo/fetch_nse_ipos.py` → `_scripts/lib/canon.py` (python import)
- `_scripts/ipo/refresh_gmp.py` → `_scripts/scrape_investorgain_gmp.py` (relative script argument)
- `_scripts/ipomatrix_ingest.py` → `_scripts/lib/canon.py` (python import)
- `_scripts/kite_connect.py` → `_scripts/refresh_kite_token.py` (script path)
- `_scripts/lineage_registry.py` → `_scripts/backfill_eps_post.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/compute_verdicts.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/ipo_score.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/ipomatrix_ingest.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/nse_preopen_capture.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/rhp_sonnet.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/sbi_haiku_extract.py` (relative script argument)
- `_scripts/lineage_registry.py` → `_scripts/scrape_investorgain_gmp.py` (relative script argument)
- `_scripts/parse_sbi_notes.py` → `_scripts/schema_sync.py` (python import)
- `_scripts/refresh_kite_token.py` → `_scripts/lib/notify.py` (python import)
- `_scripts/rhp_auto.py` → `_scripts/fetch_new_rhps.py` (relative script argument)
- `_scripts/rhp_auto.py` → `_scripts/fetch_new_rhps.py` (script path)
- `_scripts/rhp_auto.py` → `_scripts/lib/notify.py` (python import)
- `_scripts/rhp_auto.py` → `_scripts/rhp_sonnet.py` (relative script argument)
- `_scripts/rhp_auto.py` → `_scripts/rhp_sonnet.py` (script path)
- `_scripts/rhp_auto.py` → `_scripts/rhp_sonnet_store.py` (relative script argument)
- `_scripts/rhp_auto.py` → `_scripts/rhp_sonnet_store.py` (script path)
- `_scripts/rhp_sonnet.py` → `_scripts/rhp_sections.py` (python import)
- `_scripts/rhp_sonnet_store.py` → `_scripts/insights_fanout.py` (python import)
- `_scripts/rhp_sonnet_store.py` → `_scripts/lib/stage_state.py` (python import)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/backfill_eps_post.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/backfill_market_regimes.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/backfill_master_computables.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/backup_critical_tables.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/compute_d10.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/compute_flags.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/compute_journal_outcomes.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/compute_quality_score.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/compute_verdicts.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/derive_peer_pe_from_notes.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/download_sbi_notes.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/fetch_delivery_bhavcopy.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/fetch_ipo_news.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/fetch_peer_pe.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/fill_listing_open_from_candles.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/ipo/backfill_ipo_ohlc.py` (script path)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/ipo/fetch_nse_ipos.py` (script path)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/ipo/refresh_gmp.py` (script path)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/ipo_score.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/ipomatrix_ingest.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/kite_connect.py` (python import)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/lib/notify.py` (python import)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/lineage_registry.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/parse_sbi_notes.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/purge_candles_after_lockin.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/reconcile_listing_dates.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/rhp_auto.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/sbi_haiku_extract.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/schema_sync.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/smoke_probe.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/sync_inwindow_candles.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/sync_issue_details.py` (relative script argument)
- `_scripts/run_ipo_pipeline_lean.py` → `_scripts/sync_trade_journal.py` (relative script argument)
- `_scripts/sbi_haiku_extract.py` → `_scripts/lib/stage_state.py` (python import)
- `_scripts/scrape_investorgain_gmp.py` → `_scripts/lib/notify.py` (python import)
- `_scripts/sync_trade_journal.py` → `_scripts/kite_connect.py` (python import)

## Safe quarantine candidate count

**0 production files** remain mechanically UNREACHABLE under `_scripts`; all 120 Phase 4B candidates were quarantined while the 54 KEEP files remained in place.

## Method and regression

`tests/contracts/test_scripts_caller_graph.py` uses a repository fixture to prove the previously missed `step(["foo.py"])` edge, a `subprocess.run(["python", "bar.py"])` edge, an explicit `_scripts/final.py` path, and transitive wrapper/import closure.
