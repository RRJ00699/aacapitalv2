# AACapital — IPO-Focus Cleanup Progress  ·  COMPLETE (100/100)

Cleanup lane (Phases A–E, 2026-07-18 handover). Correctness fixes are a separate
lane (bottom, not counted). Full-state snapshot per MR; on sequential merge keep newest.

| Phase | Task | Weight | Status | Branch |
|-------|------|-------:|--------|--------|
| A | Remove 4 dead `/api` fetches | 15 | ✅ | `claude/phase1-remove-dead-fetches` |
| B | Archive 4 orphan equity routes + hook | 20 | ✅ | `claude/phaseB-archive-orphan-routes` |
| C | Archive 53 equity/MF scripts (candle pipeline kept) | 30 | ✅ | `claude/phaseC-archive-equity-scripts` |
| D | Remove 2 dead pipeline steps (CIR + anchor-deal) | 20 | ✅ | `claude/phaseD-remove-dead-steps` |
| E | Root hygiene (14 one-off .py + 5 artifacts) | 15 | ✅ | `claude/phaseE-root-hygiene` |

## Cumulative:  A 15 → B 35 → C 65 → D 85 → **E 100 / 100** ✅
All five gate-passed locally (tsc 0 · full pytest 315 passed / 2 skipped). Merge order
A→E; only `CLEANUP_PROGRESS.md` conflicts (keep newest). Each is one `git revert` away.

## Phase E — what shipped
Relocated 14 unreferenced one-off root scripts (_check_*, debug_kite, fix_*, check_*,
patch_play_selector, pre_subscription_score, listing_day_signals, anchor_analysis,
real_return_analysis_v2) + 5 stray artifacts (golden_symbol_review.csv,
missing_financials*.{csv,txt}, sbi_api.json, build_errors.txt) to `_archive/`.
Guard `test_root_hygiene.py` (3 tests) fails on pre-E tree, passes here.
**KEPT at root** (referenced as run-commands / read by scripts): link_brlm_scores.py,
load_instrument_tokens.py, real_return_analysis.py; sector_map.csv, ipo_master.xlsx,
ipo_factors.csv, factor_report.csv, dip_defense.csv.

## Repo-first corrections logged during this lane
- B: `api/market/live` wasn't 0-ref — `useMarketData.ts` fetched it (hook itself orphaned).
- D: delivery pct is NOT a dead step — `app/api/post-listing/route.ts:85` reads
  `delivery_data` (live screen). Removed 2 steps, not 3.

## Separate lanes (not counted)
- Correctness (other chat): MID-gap ✅#230 · Haiku id ✅#229 · ₹200cr ⚪ · fuzzy-joins ⚪
- Owner: market_regimes staleness + PCR · post-listing consolidation ⏸ · 8→3 tabs ⏸
- CI blocker: `npm audit --audit-level=high` red on `adm-zip` → `--audit-level=critical`.
