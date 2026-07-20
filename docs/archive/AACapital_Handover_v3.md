> ARCHIVED DOCUMENT
>
> This file is retained for historical reference only.
> It is not an implementation specification.
> Current product rules are defined in:
> `docs/AACAPITAL_PRODUCT_CONTRACT.md`


## ADDENDUM (2026-07-05 late)
- Institutional layer LIVE in nightly: delivery pct, bulk/block, anchor-deal conviction matcher (anchor_deal_signals; first signal: RAMBHAJO anchor ADDING 370k). Insider PIT feed PARKED: NSE blocks the API from datacenter IPs (HTTP 200, empty payload); step is a free no-op nightly; revisit via Playwright if wanted.
- verify_live_feed.py cron 09:25+13:00 auto-verifies listing days, /fail alert on failure.
- Journal autopilot v2 live (sync + FIFO outcomes + thesis snapshot). Delivery rule: git-only, gates are interlocks, Downloads retired.

## ADDENDUM (2026-07-08)
**Two open threads resolved — both by leakage-free backtest, neither traded on.**
- **CIR = circular artifact (PR #49, `cir_forward_test.py`).** The 100%/+14.6 MID+STRONG finding
  was leakage: `d10_best_pct` = max(closes d1–d10) vs open, and day 1's OWN close sits inside that
  max — the same bar CIR is measured on. Forward re-test (entry d1 close, exits fixed d2/d3/d5):
  STRONG 71.4%/+4.6 @d2 vs not-STRONG 45.7%/−0.7, t≈2.1 but n=14, terciles non-monotone, zero
  pooled effect, red-day guard cell empty. **Below the n≥30 bar → no cockpit card.** PARKED with
  re-run condition: MID+STRONG n≥30 (14 today; `listing_cir` accrues nightly for free). Journal
  CIR on every live MID trade meanwhile.
- **Market regime = no effect (PR #51, `regime_mid_backtest.py`).** Prev-day red Nifty does NOT
  worsen the MID trade (mildly opposite direction, t≈0.2–0.5, ns everywhere; VIX bands + 200EMA
  flat too). Same-day Nifty diagnostic ≈ zero beta: **the MID edge is idiosyncratic — a red index
  morning is not a reason to skip a valid MID setup.** Thread CLOSED, no filter added.
- **Strategy unchanged:** MID gap (+4–15%) → buy open, sell D1 close (65%/+3.3). Two candidate
  overlays tested and rejected instead of traded — the bar held.

**Pipeline fix (PR #50) — consolidated rebuild was crashing (`exited 1`):**
- Root cause was twofold: e68b489 fixed 18 pruned-column refs but 44 remained (Postgres reports
  only the FIRST missing column per query), and it over-deleted 5 LIVE columns — `peer_median_pe`
  (written nightly by compute_peer_pe.py, read by the valuation_premium UPDATE = the actual crash),
  `peer_pb`, `s.qib_alloc_pct`, `s.retail_alloc_pct`, `listing_volume` (importer-fed _val fallback).
- Fix: all 44 dead refs NULL::cast with original types (app still selects them — playbook route,
  listing dashboard, command center), 5 live entries restored, and a **build-time self-heal guard**:
  any i./d./s. ref missing from information_schema is NULLed with a loud `⚠️` log line instead of
  killing the nightly. This failure class is closed. **If the ⚠️ line ever appears in the nightly
  log, paste it to the next session — it means live schema drifted from the repo's assumptions.**
- Gate pattern used (new, keep it): in-container Postgres 16, source tables built with the
  post-prune live schema, builder run end-to-end with asserts. Cheaper than a broken nightly.

**Ops notes:** PAT was pasted in the 2026-07-08 chat (twice) — Rakesh rotating it. All PRs #49–#51
merged + VM synced same day. Candle purge unchanged (pre-lock window kept — forward returns d2–d5
remain computable for future re-tests).
