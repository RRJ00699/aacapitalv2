# Bucket B — IPO-domain scripts with no automated caller (116)

These are NOT dead code. They are unreachable from cron/pipeline/job_runner, but
they are **IPO-domain** — almost all are backtests, one-off analyses, and manual
research tools you run from your laptop on demand. That is a legitimate workflow
(owner, 2026-07-18: "we can leverage my local machine when we need to re-run").

**Nothing here is archived without your strike-through.** Cross out the ones you
never run; those move to `_archive/_scripts/` in Phase 3b. Anything unmarked stays.

| # | Script | Purpose (from its own docstring) |
|---|---|---|
| 1 | `__init__.py` |  |
| 2 | `analyze_brlm_rate.py` | READ ONLY — BRLM junk RATE (not count). Which lead managers have a HIGH % of junk?""" |
| 3 | `analyze_junk.py` | READ ONLY — split IPOs good vs junk (by verdict), analyze junk anchors + BRLMs for patte |
| 4 | `analyze_qib_pattern.py` | Does "high QIB + weak HNI + good anchor" actually list well? |
| 5 | `anchor_quality_backtest.py` | tests anchor QUALITY (not count) vs d10. |
| 6 | `anchor_quality_d5.py` | READ-ONLY. Re-tests anchor quality vs the EXECUTABLE |
| 7 | `anchor_quality_regression.py` | READ-ONLY. The most conclusive test possible on |
| 8 | `anchor_threshold_test.py` | READ ONLY — test the anchor threshold EXACTLY as asked: >30 as one bucket, |
| 9 | `audit_candles.py` | READ ONLY — what's actually in price_candles? IPO symbols vs full universe.""" |
| 10 | `audit_db_tables.py` | READ ONLY — list every table, row count, and whether it feeds the IPO engine. |
| 11 | `backfill_anchors_analysis.py` | fills anchor_names + anchor_count from IPOMatrix |
| 12 | `backfill_anchors_and_test.py` | fills anchor_count/anchor_names from Chittorgarh |
| 13 | `backfill_anchors_api.py` | fills anchor_names + anchor_count for the whole IPO |
| 14 | `backfill_anchors_slug.py` | fills anchor_names + anchor_count using the AUTHORITATIVE |
| 15 | `backfill_brlm_names.py` | fills ipo_intelligence.brlm_names from Chittorgarh "Issue Details" |
| 16 | `backtest_dna_drawdown.py` | the FAIR test of the DNA engine. Raw long-horizon returns inverted |
| 17 | `backtest_journey_exits.py` | does the Journey screen's exit discipline |
| 18 | `backtest_recovery_classes.py` | AACapital IPO Recovery Engine, Hypothesis 3. |
| 19 | `backtest_regime.py` | the 10yr verdict said the breakout setups have edge ONLY in uptrends. |
| 20 | `backtest_regime_split.py` | is the edge real, or just one bull market? |
| 21 | `backtest_strategies.py` | AACapital: does ANY decidable post-listing rule make money? |
| 22 | `backtest_thesis.py` | _scripts/ipo/backtest_thesis.py |
| 23 | `build_purge_plan.py` | READ ONLY — measures bloat + EMITS the purge SQL (you review + run it). Drops nothing it |
| 24 | `check_candle_storage.py` | READ ONLY — are we storing daily candles for the whole 1400-stock universe again?""" |
| 25 | `check_consolidated_row.py` | eyeball one ipo_consolidated row end-to-end (read-only). |
| 26 | `check_dupes.py` | READ ONLY — find duplicate IPOs (same company, multiple rows) + their verdicts.""" |
| 27 | `check_fairvalue_data.py` | READ ONLY — do we have the inputs for the fair-value model? (EPS, peer PE, ROE, CAGR, D/ |
| 28 | `check_fv_table.py` | READ ONLY — which table has the fair-value columns (consolidated vs intelligence)?""" |
| 29 | `check_grades.py` | READ ONLY — do upcoming/recent IPOs actually have grades? Why aren't they shown?""" |
| 30 | `check_ids.py` |  |
| 31 | `check_ingest_gain.py` | READ ONLY — coverage after the IPOMatrix ingest + why id-resolution is low.""" |
| 32 | `check_laser_rhp.py` | READ ONLY — actual ipo_rhp_intel schema + is Laser's RHP data there?""" |
| 33 | `check_missing_scores.py` | READ ONLY — why do Kusumgar/Laser/Alpine have no score circle but SBI/Knack do?""" |
| 34 | `check_neon_schema.py` |  |
| 35 | `checkcols.py` |  |
| 36 | `chittorgarh_recon.py` | throwaway: can Playwright clear Chittorgarh's Cloudflare, and |
| 37 | `cir_forward_test.py` | leakage-free re-test of the close-in-range (CIR) finding. |
| 38 | `clean_data_tests.py` | READ ONLY. The factor tests on the newly-clean IPOMatrix data. |
| 39 | `compute_earnings_estimates.py` | transparent, backtestable "house estimate" for each |
| 40 | `compute_earnings_surprise.py` | did the company beat OUR HOUSE ESTIMATE? |
| 41 | `cross_backtest.py` | READ-ONLY two-factor cross-tab on the EXACT founding outcome: |
| 42 | `db_audit.py` | READ-ONLY: the mess map. Per core table: row count, exact-duplicate |
| 43 | `dedup_ipo_intelligence.py` | collapse rows that are the same company under two name |
| 44 | `dedup_ipos.py` | _scripts/ipo/dedup_ipos.py |
| 45 | `dedupe_master.py` | merges the 9 audited duplicate groups in ipo_intelligence. |
| 46 | `deepen_candles_to_10yr.py` | bring every shallow symbol in price_candles up to a full |
| 47 | `diagnose_neon_compute.py` | READ ONLY — what's keeping Neon compute awake? Find the compute-hour drain.""" |
| 48 | `download_sebi_rhps_playwright.py` | download_sebi_rhps_playwright.py |
| 49 | `dump_sector_map.py` |  |
| 50 | `enrich_from_reports.py` | ---------------------------------------------------------------------------- |
| 51 | `enrich_promoter_holding.py` | fills promoter_pre_equity / promoter_holding_post |
| 52 | `env_utils.py` | Tiny dotenv loader so scripts work without python-dotenv installed.""" |
| 53 | `exit_backtest_v2.py` | READ ONLY — REFINED exit backtest. Tests SMART dynamic exits vs the v1 baselines. |
| 54 | `exit_backtest_v3.py` | READ ONLY — v3 exit backtest for the TYPICAL IPO (most don't hit +15%). |
| 55 | `exit_rule_backtest.py` | READ-ONLY: which exit rule maximizes return after |
| 56 | `explain_profitlock.py` | READ ONLY — walk the profit-lock rule day-by-day on Knack (and Turtlemint) so it's cryst |
| 57 | `export_ipo_backtest.py` | pull the data needed to backtest the post-listing floor / |
| 58 | `fetch_ipo_post_listing_returns.py` | _scripts/ipo/fetch_ipo_post_listing_returns.py |
| 59 | `fetch_peer_pe.py` | populate ipo_intelligence.peer_median_pe from screener.in. |
| 60 | `find_sub_cols.py` | READ ONLY — what ARE the subscription columns? Why is score 0.00 for Laser?""" |
| 61 | `find_tickers.py` |  |
| 62 | `fix_dupes.py` | READ ONLY (dry-run) — find TRUE duplicate IPOs (same listing_date + size + near-identica |
| 63 | `fix_symbol_mismaps.py` | audit + repair the 8 IPOs whose price_candles history |
| 64 | `flags_horizon_backtest.py` | READ-ONLY: quality flags vs LONGER horizons. |
| 65 | `import_all_reports.py` | _scripts/ipo/import_all_reports.py |
| 66 | `import_golden_master.py` | one-time harvest of the pre-DB manual project |
| 67 | `import_ipo_foundation.py` |  |
| 68 | `ipo_candle_backfill.py` | AACapital -- IPO Candle Backfill V2 |
| 69 | `ipo_data_hygiene.py` | two safe, idempotent fixes for ipo_intelligence: |
| 70 | `ipo_decision_engine.py` |  |
| 71 | `ipo_factor_dump.py` | one row per listed IPO, every factor as a column, sorted by the |
| 72 | `ipo_feature_store.py` | CREATE TABLE IF NOT EXISTS ipo_feature_store ( |
| 73 | `ipo_listing_probability_engine.py` |  |
| 74 | `ipo_live_feed.py` | CREATE TABLE IF NOT EXISTS ipo_live_feed ( |
| 75 | `ipo_probability_engine.py` | -ipo "BLS E-Services" |
| 76 | `ipo_run_all.py` |  |
| 77 | `ipo_run_quality_decision.py` |  |
| 78 | `ipo_similarity_engine.py` | CREATE TABLE IF NOT EXISTS ipo_similarity_results ( |
| 79 | `ipomatrix_api.py` | GOLD-STANDARD IPOMatrix data via its private API. |
| 80 | `kite-sync-ipos.py` | live IPO data from Zerodha |
| 81 | `kite_sync_and_predict.py` | AACapital production sync runner. |
| 82 | `listing_day_execution_engine.py` | -ipo "BLS E-Services" |
| 83 | `listing_day_monitor.py` | -symbol NSDL |
| 84 | `load_brlm_scores.py` | populates brlm_scores from the Chittorgarh "Lead Managers by |
| 85 | `load_issue_details.py` | creates and fills ipo_issue_details from Chittorgarh |
| 86 | `load_subscription_history.py` | ingest Chittorgarh/IPOMatrix "Issue Subscription" |
| 87 | `map_ipo_tables.py` | READ ONLY — map the 21 IPO tables: row counts, key columns, overlap. Find redundancy.""" |
| 88 | `migrate_neon_to_local.py` | move heavy OFFLINE-only tables from Neon to local Postgres. |
| 89 | `neon_sizes.py` | SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size |
| 90 | `neon_sleep_sentinel.py` | CERTAINTY that the DB sleeps (Rakesh 2026-07-18: |
| 91 | `null_triage.py` | READ-ONLY. Sorts every ipo_intelligence column into ONE bucket |
| 92 | `ofs_backtest.py` | READ-ONLY: does the fresh-vs-OFS split predict the d10 |
| 93 | `preflight_listing_day.py` | ONE command that proves listing-day readiness. READ-ONLY. |
| 94 | `probe_ipomatrix.py` | probe_ipomatrix.py v2 — corrected diagnostic (no writes). |
| 95 | `promoter_backtest.py` | READ-ONLY: does ownership structure predict outcomes? |
| 96 | `purge_automation.py` | -execute --table price_candles |
| 97 | `purge_ipo_ticks.py` | drop listing-day ticks once an IPO passes its anchor lock-in. |
| 98 | `purge_old_candles.py` | keeps price_candles bounded to a rolling window (default 5y) |
| 99 | `real_return_analysis.py` | re-verify the validated strategy, DECOMPOSED. |
| 100 | `reconcile_missing_candles.py` | fix the company_master <-> price_candles closed loop. |
| 101 | `regime_mid_backtest.py` | do red-Nifty listing days worsen the MID-gap trade? |
| 102 | `research_bundle.py` | READ ONLY — 3 things: (1) fair-value table check, (2) lock8/trail12 walk on Knack, |
| 103 | `resolve_ipo_symbols.py` | fill the ONE missing link for bare IPO rows. |
| 104 | `score_ipos_live.py` | _scripts/ipo/score_ipos_live.py |
| 105 | `scrape_anchors_playwright.py` | fills anchor_names+count for IPOs IPOMatrix's API |
| 106 | `seed_global_cache.py` | _scripts/seed_global_cache.py |
| 107 | `sync_candles_to_neon.py` | -top 200 --days 365 |
| 108 | `sync_ipo_calendar.py` | _scripts/ipo/sync_ipo_calendar.py |
| 109 | `sync_ipo_master.py` | AACapital -- Sync IPO Master Data |
| 110 | `test_post_listing.py` | READ ONLY — test the post-listing signals for a listed symbol, as TEXT (no UI needed). |
| 111 | `update_kite_token.py` |  |
| 112 | `update_nifty_value.py` | store the current Nifty 50 index value into platform_config. |
| 113 | `upgrade_trade_journal.py` | make the EXISTING trade_journal table serve the |
| 114 | `verify_laser_live.py` | READ ONLY — does the fuzzy join ACTUALLY match Laser? Test the exact SQL the API runs."" |
| 115 | `verify_resolved_symbols.py` | turn fuzzy-matched symbols into candle-verified facts. |
| 116 | `wayback_preopen_harvest.py` | free recent-data workaround for the pre-open book. |

## Already decided — NOT in this list
- **KEPT (shared IPO infra):** `compute_candle_returns`, `kite-sync-candles`,
  `reconcile_missing_candles`, `sync_candles_to_neon` — `price_candles` feeds
  Journey + every backtest.
- **KEPT (owner tools):** `data_coverage_report` ("the truth button"),
  `backtest_dip_defense` (IPO backtest in spec §5).
- **ARCHIVED in Phase 3a (MF/equity only, zero IPO content):** clean_target_funds,
  filter_target_mf_holdings, import_fundamentals, load_mf_excel_holdings,
  populate_company_master, reconcile_universe, validate_mf_csv, validate_target_mf_csv.
