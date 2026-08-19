Status: CURRENT — evidence register, no deletions authorised
Authority: docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md
Scope: C3 of the consolidated cleanup PR

# Quarantine audit — `compatibility/` and `_archive/scripts/`

**This document deletes nothing and authorises nothing.** It is the evidence
table C3 asked for: one row per tracked quarantined file, with the last commit
that touched it, any live reference resolved by exact module name, and a
verdict. Acting on a `DELETABLE` verdict is a separate, owner-approved change.

## Scope

| Tree | Tracked files |
|---|---:|
| `compatibility/scripts/` | 90 |
| `compatibility/consolidated/` | 3 |
| `_archive/scripts/` | 36 (35 + `setup_vm_cron.sh` archived in C2, − `prod/env_utils.py` restored in C5) |
| **Total audited** | **129** |

`_archive/` outside `scripts/` (loose one-off `.py`, `.txt`, route snapshots)
is out of scope — C3 named `_archive/scripts` specifically.

## Method

1. **Last commit** — `git log -1 --date=short -- <path>`.
2. **Reference search** — every tracked file outside the two quarantine trees
   was scanned (not only `pipeline/ _scripts/ app/ lib/`; the wider sweep also
   covered `components/ workers/ tools/ uat/ tests/ research/ .github/` and root
   config, so a `DELETABLE` verdict is a repository-wide claim, not a
   four-zone one).
3. **Exact module name, never substring.** Python files matched on
   `^\s*(from|import)\s+<stem>\b` for import edges and on
   `(?<![\w./-])<filename>(?![\w])` for path/filename edges. `market_regime`
   therefore does not match `backfill_market_regimes`, and `db.ts` does not
   match `lib/db.ts` as a substring of an unrelated token.
4. **Shadow resolution.** Where a live file carries the same module name as a
   quarantined one, a bare reference resolves to the *live twin*, not the
   quarantined copy, and is recorded as no evidence. Three shadows exist:
   `fill_listing_open_from_candles.py`, `market_regime.py`, `db.ts`.
5. **Prose vs. load-bearing.** A docstring or comment naming a script is
   recorded but does not make it `KEEP-QUARANTINED`; an import, a
   `subprocess`/`sys.path` execution, a `read_text()` in a test, or a
   coverage/workflow path entry does.

## Verdict counts

| Verdict | Files | Meaning |
|---|---:|---|
| **BLOCKED** | 1 | Owner ruling pending; not eligible for any decision here |
| KEEP-QUARANTINED | 13 | A live file imports, executes, reads, or contractually owns it. Deleting it breaks the gate or production |
| DELETABLE | 115 | No live importer, executor, reader, or contract owner anywhere in the tracked tree |

## The blocked file

`compatibility/scripts/rule_validation.py` is **BLOCKED** — the owner ruling on
the `rule_validation_results` producer is pending. It is additionally
ratchet-pinned: `_scripts/tests/test_rule_validation.py` asserts this exact
path `is_file()` and that `_scripts/rule_validation.py` does not exist, and
`pipeline/cron.py` carries the matching "producer is quarantined" note. No
verdict is offered and none should be inferred from its row.

## RESOLVED — the live production import that resolved into `_archive/`

**This audit's most important finding, and it is now fixed.** The original C3
table listed `_archive/scripts/prod/env_utils.py` as KEEP-QUARANTINED because
`_scripts/prod/kite_sync_and_predict.py` — a KEEP production file, and the
entrypoint behind `npm run prod:market`, `prod:ipo`, and `prod:all` — imports it
at module scope:

```python
from env_utils import load_dotenv_files, require_neon_url
```

On a clean checkout that raised `ModuleNotFoundError: No module named 'env_utils'`
and all three `prod:*` entrypoints died. It only appeared to work in long-lived
working copies because a stale `_scripts/prod/__pycache__/env_utils.cpython-312.pyc`
sat next to the caller — the one `.pyc` tracked in git.

**Root cause: a caller-graph resolver defect, not a stale quarantine decision.**
Running a script directly puts its own directory on `sys.path[0]`, so a bare
sibling import resolves within the caller's own package. `tools/scripts_caller_graph.py`
tried only the bare module name and the `_scripts.`-prefixed name — never the
caller's package — so **every bare sibling import below the top level was
invisible**, and Phase 4B read `env_utils.py` as UNREACHABLE.

Fixed in C5 of this PR:

* `_scripts/prod/env_utils.py` restored from `_archive/scripts/prod/` by `git mv`.
* The tracked `.pyc` untracked; `__pycache__/` and `*.pyc` were already in
  `.gitignore` (lines 60–61) and did not need adding — being ignored never
  untracks an already-tracked file, which is why it survived.
* `tools/scripts_caller_graph.py` now resolves bare sibling imports against the
  caller's own package. Production totals move `KEEP=53 → KEEP=54` — one file,
  one edge, no other change.
* `_scripts/tests/test_prod_entrypoints_import.py` runs each `prod:*` entrypoint
  in a subprocess with `-B` and a scrubbed environment, so no bytecode cache can
  hide a missing module again, and fails if any `.pyc` is re-committed.
* `tests/contracts/test_scripts_caller_graph.py` gains a fixture case — a bare
  sibling import inside `_scripts/sub/` — that is unreachable under the old
  resolver and reachable under the current one.

The row for `env_utils.py` is gone from the table below because the file is no
longer quarantined. This is the only verdict in the original audit that changed.

## Other rows worth reading before acting

* **`compatibility/scripts/ipo/import_chittorgarh.py`** has no executable
  caller, but `_scripts/ipo_data_contract.csv` names it as the
  `populator_script` for 8 fields whose status is `LIVE`. It is marked
  KEEP-QUARANTINED: deleting the only implementation of a producer the data
  contract still calls live is a product decision, not cleanup.
* **11 of the 13 KEEP-QUARANTINED files are pinned by tests**, most of them by
  `_scripts/tests/test_ux_premium.py` and `test_root_hygiene.py`, which
  `read_text()` quarantined sources to assert historical behaviour. Any future
  deletion must retire the assertion in the same commit.
* **`compatibility/consolidated/build_ipo_consolidated.py`** (the v1) is the
  only file in `compatibility/consolidated/` with no live reference at all; its
  v2 sibling and `consolidate_master.py` are both test-executed.

## The table

| # | Path | Last commit touching it | Live importer under `pipeline/` `_scripts/` `app/` `lib/` (exact module name) | Verdict |
|---:|---|---|---|---|
| 1 | `compatibility/scripts/rule_validation.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_rule_validation.py` asserts this exact path `is_file()` and that `_scripts/rule_validation.py` does NOT exist | **BLOCKED** |
| 2 | `_archive/scripts/load_instrument_tokens.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_root_hygiene.py::test_referenced_root_scripts_relocated_with_updated_callers` asserts this exact path exists | KEEP-QUARANTINED |
| 3 | `_archive/scripts/loadtest_k6.js` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_phase8_uat_contracts.py` reads its source | KEEP-QUARANTINED |
| 4 | `_archive/scripts/setup_vm_cron.sh` | `b2759fe` 2026-08-17 — chore(archive): retire setup_vm_cron.sh to _archive/scripts (VM decommissioned) | cited as evidence by `docs/decisions/LEAN_RETIREMENT_DECISIONS.md` B1 (archived in C2 of this PR) | KEEP-QUARANTINED |
| 5 | `compatibility/consolidated/build_ipo_consolidated_v2.py` | `fda7503` 2026-08-07 — refactor: materially separate legacy repository surfaces | `_scripts/tests/test_build_consolidated.py` subprocess-executes it; `_scripts/tests/test_core_imports.py` imports it by path (MOVED_IMPORT_SAFE); `.coveragerc` scores it; `_scripts/fill_listing_open_from_candles.py` prints it as the next command | KEEP-QUARANTINED |
| 6 | `compatibility/consolidated/consolidate_master.py` | `fda7503` 2026-08-07 — refactor: materially separate legacy repository surfaces | `_scripts/tests/test_consolidate_master_executes.py` puts `compatibility/consolidated` on `sys.path` and imports it; `_scripts/tests/test_ux_premium.py` reads its source | KEEP-QUARANTINED |
| 7 | `compatibility/scripts/backfill_listing_minutes.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_no_columns_on_rebuilt_tables.py` reads its source | KEEP-QUARANTINED |
| 8 | `compatibility/scripts/backfill_listing_window_candles.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_ux_premium.py` reads its source (2 assertions) | KEEP-QUARANTINED |
| 9 | `compatibility/scripts/data_quality_audit.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_ux_premium.py` reads its source (2 assertions) | KEEP-QUARANTINED |
| 10 | `compatibility/scripts/ipo/import_chittorgarh.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | no executable caller, but `_scripts/ipo_data_contract.csv` names it as the `populator_script` for **8 fields whose status is LIVE** (nse_symbol, listing_date, issue_price, issue_size_cr, ipo_pe, ipo_pe_post, anchor_total_cr, anchor_lock30_date) plus 1 BROKEN_SOURCE field. Deleting it removes the only implementation of a producer the data contract still calls live | KEEP-QUARANTINED |
| 11 | `compatibility/scripts/ipo/kite_ticker_ipo.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_pipeline_hotfixes.py` and `_scripts/tests/test_ux_premium.py` read its source | KEEP-QUARANTINED |
| 12 | `compatibility/scripts/link_brlm_scores.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_root_hygiene.py::test_referenced_root_scripts_relocated_with_updated_callers` asserts this exact path exists | KEEP-QUARANTINED |
| 13 | `compatibility/scripts/nse_anchor_backfill.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_ux_premium.py` reads its source | KEEP-QUARANTINED |
| 14 | `compatibility/scripts/run_ipo_pipeline.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | `_scripts/tests/test_no_dead_pipeline_steps.py` (PIPELINES list) and `_scripts/tests/test_phase1_fixes.py` read its source | KEEP-QUARANTINED |
| 15 | `_archive/scripts/__init__.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 16 | `_archive/scripts/add_password_hash.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 17 | `_archive/scripts/backfill/download-screener-csv.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 18 | `_archive/scripts/chittorgarh_recon.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 19 | `_archive/scripts/compute_earnings_estimates.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 20 | `_archive/scripts/compute_earnings_surprise.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 21 | `_archive/scripts/dump_sector_map.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 22 | `_archive/scripts/fetch_live_ipos.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — `_scripts/ipo/fetch_nse_ipos.py:12` (docstring, explains why it was retired)) | DELETABLE |
| 23 | `_archive/scripts/find_tickers.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 24 | `_archive/scripts/ipo/ipo_live_feed.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 25 | `_archive/scripts/ipo/ipo_run_all.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 26 | `_archive/scripts/ipo/ipo_run_quality_decision.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 27 | `_archive/scripts/ipo/load_issue_details.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 28 | `_archive/scripts/ipo/load_subscription_history.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 29 | `_archive/scripts/ipo/run_ipo_pipeline.ps1` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 30 | `_archive/scripts/ipo_live_launcher.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 31 | `_archive/scripts/lib/__init__.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 32 | `_archive/scripts/lib/http_resilience.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 33 | `_archive/scripts/lib/indicators.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 34 | `_archive/scripts/loaders/load-weekly-candles.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 35 | `_archive/scripts/migrations/20260806_document_ledger.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 36 | `_archive/scripts/migrations/create_multibagger_similarity.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 37 | `_archive/scripts/migrations/management_commentary_schema.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 38 | `_archive/scripts/neon_sizes.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 39 | `_archive/scripts/neon_sleep_sentinel.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 40 | `_archive/scripts/parse_sbi_notes.py` | `37ead43` 2026-08-08 — feat: migrate SBI notes to canonical R2 Sonnet lane | none | DELETABLE |
| 41 | `_archive/scripts/price-history-route.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 42 | `_archive/scripts/prod/__init__.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 43 | `_archive/scripts/run-intelligence-scoring.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 44 | `_archive/scripts/seed_global_cache.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 45 | `_archive/scripts/tests/test_phase4_resilience.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 46 | `_archive/scripts/update_kite_token.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 47 | `_archive/scripts/update_nifty_value.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 48 | `compatibility/consolidated/build_ipo_consolidated.py` | `fda7503` 2026-08-07 — refactor: materially separate legacy repository surfaces | none (prose only — no live reference at all; `tests/contracts/test_repository_spine.py` only asserts it is ABSENT from `_scripts/`) | DELETABLE |
| 49 | `compatibility/scripts/anchor_quality_d5.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 50 | `compatibility/scripts/anchor_quality_regression.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 51 | `compatibility/scripts/anchor_threshold_test.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 52 | `compatibility/scripts/backfill_anchors_and_test.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 53 | `compatibility/scripts/backfill_anchors_api.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 54 | `compatibility/scripts/backfill_anchors_slug.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 55 | `compatibility/scripts/backfill_price_candles.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — `_scripts/sync_inwindow_candles.py:15` (docstring)) | DELETABLE |
| 56 | `compatibility/scripts/check-env.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 57 | `compatibility/scripts/check-neon-storage.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 58 | `compatibility/scripts/checkcols.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 59 | `compatibility/scripts/cir_forward_test.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 60 | `compatibility/scripts/clean_data_tests.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 61 | `compatibility/scripts/dedup_merge.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 62 | `compatibility/scripts/dedup_merge.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 63 | `compatibility/scripts/dedupe_master.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 64 | `compatibility/scripts/deepen_candles_to_10yr.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 65 | `compatibility/scripts/engines/ipo_probability_engine.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 66 | `compatibility/scripts/enrich_ipo_chittorgarh.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 67 | `compatibility/scripts/enrich_promoter_holding.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 68 | `compatibility/scripts/explain_profitlock.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 69 | `compatibility/scripts/export_phase3_data.ps1` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 70 | `compatibility/scripts/fetch_insider_trades.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 71 | `compatibility/scripts/find_sub_cols.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 72 | `compatibility/scripts/fix_dupes.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 73 | `compatibility/scripts/fix_symbol_mismaps.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 74 | `compatibility/scripts/guardrails_canon.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — `_scripts/lib/canon.py:5` (docstring names the SQL twin)) | DELETABLE |
| 75 | `compatibility/scripts/import_golden_master.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 76 | `compatibility/scripts/ipo/backfill_brlm_names.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 77 | `compatibility/scripts/ipo/compute_brlm_scores.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 78 | `compatibility/scripts/ipo/dedup_ipo_intelligence.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 79 | `compatibility/scripts/ipo/dedup_ipos.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 80 | `compatibility/scripts/ipo/enrich_from_reports.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 81 | `compatibility/scripts/ipo/enrich_ipo_chittorgarh.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 82 | `compatibility/scripts/ipo/fetch_ipo_post_listing_returns.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 83 | `compatibility/scripts/ipo/fill_listing_open_from_candles.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — every live reference to this filename resolves to the live twin `_scripts/fill_listing_open_from_candles.py` (the lean runner passes it as a relative step argument from `_scripts/`)) | DELETABLE |
| 84 | `compatibility/scripts/ipo/import_all_reports.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 85 | `compatibility/scripts/ipo/import_ipo_foundation.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 86 | `compatibility/scripts/ipo/ipo_data_hygiene.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 87 | `compatibility/scripts/ipo/ipo_decision_engine.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 88 | `compatibility/scripts/ipo/ipo_factor_dump.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 89 | `compatibility/scripts/ipo/ipo_feature_store.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 90 | `compatibility/scripts/ipo/ipo_listing_probability_engine.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 91 | `compatibility/scripts/ipo/ipo_similarity_engine.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 92 | `compatibility/scripts/ipo/listing_day_monitor.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 93 | `compatibility/scripts/ipo/listing_day_reminder.ps1` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 94 | `compatibility/scripts/ipo/load_brlm_scores.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 95 | `compatibility/scripts/ipo/resolve_ipo_symbols.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 96 | `compatibility/scripts/ipo/score_ipos_live.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 97 | `compatibility/scripts/ipo/setup_ipo_scheduler.ps1` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 98 | `compatibility/scripts/ipo/sync_ipo_calendar.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 99 | `compatibility/scripts/ipo_candle_backfill.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 100 | `compatibility/scripts/ipo_daily_levels.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 101 | `compatibility/scripts/ipomatrix_api.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 102 | `compatibility/scripts/kite-sync-candles.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — `pipeline/kite_fetch.py:15` (WHY-NOT-REUSE docstring); `_scripts/tests/test_pipeline_lean.py:70` asserts the lean run does NOT call it) | DELETABLE |
| 103 | `compatibility/scripts/kite-sync-ipos.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 104 | `compatibility/scripts/kite_preopen_capture.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 105 | `compatibility/scripts/lib/db.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (name shadowed by live `lib/db.ts`; all references resolve there) | DELETABLE |
| 106 | `compatibility/scripts/listing_day_execution_engine.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 107 | `compatibility/scripts/loaders/load-daily-candles.ts` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 108 | `compatibility/scripts/map_ipo_tables.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 109 | `compatibility/scripts/market_regime.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — `_scripts/backfill_market_regimes.py:5,16` (docstring). The live `import` there is `from engines.market_regime import ...`, which resolves to `_scripts/engines/market_regime.py`) | DELETABLE |
| 110 | `compatibility/scripts/migrations/20260617_prod_ready_tables.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 111 | `compatibility/scripts/pipeline_watchdog.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 112 | `compatibility/scripts/preflight_listing_day.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 113 | `compatibility/scripts/prune_dead_columns.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 114 | `compatibility/scripts/purge_ipo_ticks.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 115 | `compatibility/scripts/purge_old_candles.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 116 | `compatibility/scripts/reconcile_missing_candles.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 117 | `compatibility/scripts/research_bundle.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 118 | `compatibility/scripts/scrape_anchors_playwright.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 119 | `compatibility/scripts/scrape_chittorgarh.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none (prose only — `_scripts/run_ipo_pipeline_lean.py:178` (a `(removed)` comment)) | DELETABLE |
| 120 | `compatibility/scripts/sync_ipo_calendar.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 121 | `compatibility/scripts/sync_ipo_master.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 122 | `compatibility/scripts/tests/test_asset_light.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 123 | `compatibility/scripts/tests/test_kite_preopen.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 124 | `compatibility/scripts/tests/test_listing_minutes.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 125 | `compatibility/scripts/tests/test_strong_key_writers.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 126 | `compatibility/scripts/triage_known_gaps.sql` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 127 | `compatibility/scripts/upgrade_trade_journal.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 128 | `compatibility/scripts/wayback_preopen_harvest.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
| 129 | `compatibility/scripts/z.py` | `8026a54` 2026-08-07 — chore: quarantine unreachable scripts | none | DELETABLE |
