# AACapital — IPO-Focus Cleanup  ·  ONE MR (A–E, 100/100)

Single branch `claude/ipo-cleanup` — five phase commits (A→E), one merge request.
Each phase is its own commit, so you can still `git revert` any one independently,
or "Squash and merge" the whole thing. Cleanup lane only; correctness fixes are a
separate lane (bottom).

| Phase (commit) | Task | What |
|---|---|---|
| A | Remove 4 dead `/api` fetches | today-screen + cron-monitor called routes that don't exist |
| B | Archive 4 orphan equity routes + hook | search, market/live, broker/holdings, broker/positions → `_archive` |
| C | Archive 53 equity/MF scripts | MF pipeline, screener/fundamentals, dead-concept backtests → `_archive` (candle pipeline KEPT) |
| D | Remove 2 dead pipeline steps | close-in-range (CIR leakage) + anchor-deal (nonexistent table) |
| E | Root hygiene | 14 one-off `.py` + 5 stray artifacts → `_archive` |

**Gates (whole branch, local): `tsc --noEmit` 0 errors · full pytest 319 passed / 2 skipped.**
6 new fail-first guard tests (dead-api-refs, dead-pipeline-steps, root-hygiene) —
each fails on the pre-change tree, passes here. Nothing deleted; everything in `_archive/`.

## Repo-first corrections made vs the handover (both file:line-cited)
- **B:** `api/market/live` was NOT 0-ref — `lib/hooks/useMarketData.ts:51` fetched it;
  that hook is itself orphaned, so both were archived.
- **D:** delivery pct is NOT dead — `app/api/post-listing/route.ts:85` reads
  `delivery_data` for a live screen (`PostListingDashboard.tsx:56`). Removed 2 steps, not 3.

## KEPT on purpose (do not "finish the job" by removing these)
- `api/market-regime` (spec §2C.10 data input), `market/global`, `market/snapshot`,
  `broker/quote`, `broker/status`, both `post-listing` routes.
- Candle pipeline: `kite-sync-candles`, `reconcile_missing_candles`, `compute_candle_returns`,
  `sync_candles_to_neon` (+ backfill/purge). `price_candles` feeds Journey + backtests.
- Root scripts still referenced: `link_brlm_scores.py`, `load_instrument_tokens.py`,
  `real_return_analysis.py`; artifacts scripts read (`sector_map.csv`, `ipo_master.xlsx`, …).

## Separate lanes (not in this MR)
- Correctness (other chat): MID-gap ✅#230 · Haiku id ✅#229 · ₹200cr ⚪ · fuzzy-joins ⚪
- Owner: market_regimes staleness + PCR · post-listing consolidation · 8→3 tabs
- CI: `security` job `npm audit --audit-level=high` red on `adm-zip` (no upstream fix) →
  `--audit-level=critical` (agent tokens lack `workflow` scope).
