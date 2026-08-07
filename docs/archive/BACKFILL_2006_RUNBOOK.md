> ARCHIVED DOCUMENT
>
> This file is retained for historical reference only.
> It is not an implementation specification.
> Current product rules are defined in:
> `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md`

# 2006 Backfill Runbook — clean revalidation, zero code change

## The design guarantee
Every recompute is UPDATE-in-place (idempotent) and every backfill is COALESCE
fill-empty (never clobbers). So the 2006 IPOMatrix backfill is SAFE to run
repeatedly, and the full test suite revalidates against the larger dataset with
NO code change — that's the point Rakesh set: "backfill, rerun tests, clean result."

## Order of operations (after buying IPOMatrix 2006 access)
1. **Backfill fundamentals** (fill-empty, safe to rerun):
   ```
   IPOMATRIX_TOKEN=<paid> python research/backtests/backfill_anchors_analysis.py --apply
   IPOMATRIX_TOKEN=<paid> python _scripts/backfill_eps_post.py --apply
   # + roe/cagr/de backfill once the paid endpoint is confirmed to serve them
   ```
2. **Backfill price history** to 2006 (backtest outcomes need it):
   ```
   python _scripts/backfill_price_candles.py           # widen its date floor to 2006
   python _scripts/ipo/backfill_ipo_ohlc.py            # listing-day OHLC
   ```
3. **Recompute derived layers** (idempotent overwrites):
   ```
   python _scripts/ipo_score.py --apply                # era buckets now split 2006-15
   python _scripts/compute_quality_score.py --apply    # coverage-floor alarm active
   python _scripts/compute_verdicts.py --apply
   ```
4. **Revalidate — the clean result Rakesh wants:**
   ```
   python _scripts/ipo_score.py --backtest             # bands must stay monotonic on the BIGGER n
   python research/backtests/backtest_quality_score.py           # quality factor table on 20yr
   python research/backtests/backtest_journey_exits.py           # START=2006 exit discipline over full history
   python -m pytest _scripts/tests/ -q                 # all green on larger data
   ```

## Acceptance for the backfill (don't trust it until):
- ipo_score bands STILL monotonic after adding 2006-20 (if they break, the old
  data behaves differently — a FINDING, widen/reweight, don't hide it)
- quality_score coverage RISES (the floor alarm confirms; more data = more scored)
- Journey exit backtest holds across 2006-2020 too (bear markets included)
- Every backfilled score carries eps_source / provenance so partial (IPOMatrix-
  only, no RHP) vs full (RHP+fundamentals) is always distinguishable

## What the guards guarantee going forward
- **compute_quality_score**: coverage <60% -> pipeline_failures -> phone. A
  backfill that raises coverage passes; a regression that drops it screams.
- **smoke_probe**: quality_score <100 rows -> pipeline fails loudly (dead dial
  can't hide).
- **era buckets**: 2006 data gets its own <=2010/2011-15/2016-20 rows in every
  backtest, so deep history is revealed, never lumped.
- All idempotent: rerun any step any number of times, same clean result.
