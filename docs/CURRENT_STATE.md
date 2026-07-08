# AACapital — CURRENT STATE (2026-07-08)

**This document supersedes ALL prior handovers and the 43-file "Tech Docs and Data Brain"
archive.** Where an older doc disagrees with this one, this one wins. Update this file at the
end of every working session; treat everything else as history.

Personal Indian-equity IPO **post-listing** research tool. Trade the IPO as a market event
after listing, not the allotment lottery. Motto: _research signal, not a buy call._
Repo `RRJ00699/aacapitalv2` · Neon Postgres · Next.js on Vercel (`aacapitalprivatelimited.com`)
· Hetzner VM runs the crons (IST) · owner Rakesh (CST — never map his clock to IST).

## 0. Operating model (how sessions work)

- Assistant patches code via the GitHub API, **gates in-container** (py_compile + selftest +
  local Postgres 16 fixture run), opens PRs to `claude/*` branches. Rakesh merges from phone.
- **A fix is NOT done until its PR is MERGED and Admin→Sync runs on the VM.** Manual laptop
  runs fill data once but leave main/nightly broken. Corollary learned 2026-07-08: **merging a
  PR early strands later commits on the branch** — they need a fresh PR (see #54).
- Laptop runs: `C:\aacapital-v2`, PowerShell, `$env:DATABASE_URL` from .env, scripts fetched
  via **raw-commit-pinned URLs**. VM runs: Admin console job queue.
- Discipline: **backtest-before-build** · **n≥30 = SIGNAL bar** (below = indicative only) ·
  draw only from backtest-ready columns · **Rule 1**: raw scraped facts fill-EMPTY-only,
  derived may DO UPDATE, value-sanity before commit · probe an API before building on it.
- Windows gotcha: Defender locks `.git/objects` (the `Unlink ... (y/n)` prompt). Permanent
  fix, PowerShell as Admin: `Add-MpPreference -ExclusionPath "C:\aacapital-v2"`.
- Messages to Rakesh: short, mobile-friendly.

## 1. The validated strategy (and how its numbers evolved)

**Current, executable, honest:** gap = listing open vs issue price.
**MID gap (+4 to +15%) → buy listing open, sell D1 close: 65% win / +3.3% median.**
LOW (<4) and HIGH (>15) do not trade. HIGH is a structural trap (pop & fade).

Why older docs show different numbers — three generations, each less leaky:

| Era | Claim | Why superseded |
|---|---|---|
| June playbook docs | BUY_AT_OPEN 98% / +46% etc. | Repudiated by owner's own schema-v2 doc as "fake precision"; never trust |
| Handover v3 | MID 81% / +10, "exit on strength ≤10 sessions" | Outcome was `d10_best_pct` = best close in 10 sessions — a ceiling, not an executable exit (same leakage class as CIR, below) |
| **Current** | **MID 4–15 → sell D1 close, 65% / +3.3** | Executable prices only; this is the trading rule |

First live trade (2026-07-06, Knack): MID, sold at close, −2.9% — normal loss, correctly
executed. Journal autopilot records fills from Kite.

Other validated layer (separate spine): **MF NEW-initiation conviction signal** (💎) — a
high-conviction fund *initiating* a brand-new position; strongest when ≥2 funds initiate.
Monthly manual Excel drop feeds it; 5 of 11 funds currently stale >50d.

Score v0 (`ipo_score.py`): 7 evidence-backed weights, bands monotonic 51/76/76/90 ✅.

## 2. Rejected / closed register (do NOT revive without new evidence)

- **CIR (close-in-range) as MID confirmation — CLOSED 2026-07-08 as circular artifact.**
  The 100%/+14.6 finding measured CIR and outcome on the same day-1 bar (`d10_best_pct`
  includes day 1's own close). Leakage-free re-test (`cir_forward_test.py`, entry d1 close,
  exits d2/d3/d5): residual +4.6 med @d2, n=14, non-monotone terciles, zero pooled effect →
  below bar. **Parked with re-run condition: MID+STRONG n≥30 (14 as of today; `listing_cir`
  accrues nightly free).**
- **Market regime / red-Nifty listing days — CLOSED 2026-07-08, no effect.**
  (`regime_mid_backtest.py`) Prev-day red Nifty, 200EMA side, VIX bands: all flat, direction
  even mildly opposite. Same-day Nifty ≈ zero beta → **the MID edge is idiosyncratic; a red
  index morning is not a reason to skip a valid MID setup.**
- Fresh/OFS split · quality-flags@d10 · base-breakouts · anchor-quality (incl. tier-1 share
  regressions and d1–d5 horizons) — all tested, no edge.
- Buy-the-dip at every depth · soft-listing dip-defense (12% recovery vs 67% baseline —
  capital-protection SELL flag, not a buy) · recovery rules W2/S3 (edge was 2022-23 only).
- GMP: non-predictive context. Store, never trade. Anchor score alone: not predictive
  (Hyundai). Quality composites do NOT separate survivors — only entry timing (gap) does.
- Chart patterns / momentum / multibagger similarity: 2023-regime mirages. p_2x/5x/10x
  labels are formulaic fakes (feature kept by owner's choice; ignore analytically).

## 3. Data layer (Neon)

- **`ipo_intelligence`** — master, ~750 rows, **208 columns post-prune** (2026-07-07/08).
  `prune_dead_columns.py` DROP list is the authority on what's gone.
- **`ipo_consolidated`** — the one read model the UI trusts. Rebuilt nightly by
  `build_ipo_consolidated_v2.py` (206 MAP entries + jsonb + signal columns). Since
  2026-07-08 (#50) it has a **self-heal guard**: any `i./d./s.` ref missing from
  information_schema is NULLed with a loud `⚠️` log line instead of killing the nightly.
  **If that ⚠️ line ever appears in a nightly log, paste it to the session — schema drifted.**
- **`price_candles`** — single candle store. Purge policy keeps only listing → lock-in
  (~T+30) + buffer per IPO (`purge_candles_after_lockin.py`); `trade_journal` symbols exempt.
  Forward returns d2–d5 stay computable for re-tests.
- **`market_regimes`** — nifty_close/ema200/breadth/india_vix/active_regime per day, ~2,105
  days back to ~2018.
- Others: `ipo_gmp`, `ipo_subscription_history`, `ipo_issue_details`, `ipo_research_notes`
  (SBI PDFs), `ipo_daily_levels` (floor/ceiling; **--replace exception to Rule 1**),
  `ipo_tick_feed` (listing days only), `ipo_level_analysis`, `institutional_large_deals`,
  `delivery_data`, `anchor_deal_signals`, `trade_journal`, `platform_config` (Kite token),
  `job_runs`, `system_health`, `instrument_master` (Kite token map — **refresh with
  `load_instrument_tokens.py` before any backfill; a stale dump = spurious "No token"**).
- **Symbol hygiene** (recurring disease, root cause = unreliable scraped `~nse_symbol` +
  NSE ticker reuse): 4 landmines nulled in June (Dixon/KFINTECH etc.); **8 more fixed
  2026-07-08** via `fix_symbol_mismaps.py` — Glenmark Life GLENMARK→GLS (REMAP), Paras dupe
  PDSL→PARAS (REMAP), pre-listing candles purged for INDIGOPNTS/LATENTVIEW/EMIL/MEDANTA/
  HOMEFIRST/RAINBOW (reused tickers). **The reconciler's 400-day guard
  (`reconcile_listing_dates.py`) is the standing detector for this class.**
  Known leftover: Paras Defence + Home First have duplicate master rows → re-run
  `dedupe_master.py`.
- **Gap-band mismatch (OPEN DECISION):** app's `gap_bucket` = LOW<10/MID 10–30/HIGH>30
  (old era); the traded band = 4–15. A +5% open shows LOW (hides a valid trade); +25% shows
  MID (invites an invalid one). Fix = one line in the consolidated builder, or add a
  separate `trade_band` column. Rakesh to choose.

## 4. Pipeline & ops

- **VM crons (IST):** 08:45 Kite token · 08:50 calendar sync · 09:10 M–F live launcher
  (mainboard ≥₹200cr, listing→+30d) · 09:25+13:00 `verify_live_feed.py` · every min
  `job_runner.py` (Admin console queue) · **16:00 nightly `run_ipo_pipeline.py`** (self-updates
  via `git reset --hard origin/main` — VM-only files die nightly; merged-only rule follows) ·
  17:00 watchdog → system_health · Sun 19:00 weekly purge.
- Nightly order: scrape (Chittorgarh, GMP, delivery, bulk/block, anchor-match) → regime →
  candles (in-window) → listing fields → SBI notes → score v0 → d10 → reconcile dates →
  close-in-range → computables → sectors → peer PE → quality flags → convergence →
  **rebuild consolidated** → daily levels → journal sync/outcomes → backup → health gate →
  value sanity.
- Kite token dies daily ~6 AM IST; everything live depends on the 08:45 refresh.
- Backups: nightly csv.gz of the critical 4 tables, 14-day retention.
- **Do not run the full pipeline on the laptop** — its self-update reset is the VM's pattern.

## 5. Session log 2026-07-08 (PRs #49–#54)

- **#49** `cir_forward_test.py` — leakage-free CIR re-test → artifact (see §2). MERGED.
- **#50** consolidated rebuild fix — 44 remaining pruned refs NULL::cast with original
  types, 5 over-deleted live cols restored (`peer_median_pe` was the crash), self-heal
  guard added. MERGED. Nightly's `rebuild consolidated` green again.
- **#51** `regime_mid_backtest.py` — regime thread closed (see §2). MERGED.
- **#52** handover addendum. MERGED (superseded by this file).
- **#53** `fix_symbol_mismaps.py` — 8 wrong-symbol IPOs repaired (DB fix APPLIED live).
  MERGED early; follow-ups stranded → **#54**.
- **#54** (OPEN at write time): dupe-row handling, backfill psycopg2 scoping fix,
  `--symbols` targeted mode, and the big one — `ipo_candle_backfill.py` **now actually
  writes `price_candles`** (it never did), window capped listing+70d (Kite 2000-day limit),
  master UPDATE built from live columns only.

**Pending to close the mismap thread:** merge #54 → Admin→Sync →
`load_instrument_tokens.py` → `ipo_candle_backfill.py --symbols=GLS,INDIGOPNTS,LATENTVIEW,
EMIL,MEDANTA,PARAS,HOMEFIRST,RAINBOW` → full pipeline (VM) → reconciler dry-run (8 should
pass) → **re-run `real_return_analysis` to re-verify 65/+3.3 on clean data** (Glenmark Life
was the one wrong-company return inside the MID stats). Also: KNACK listing_date Jul 8→Jul 7
corrects itself once its candles are in and the reconciler runs.

## 6. Risk & timer board

| Item | When | Status |
|---|---|---|
| Kite app key `br9m41pn8nvvywnl` expires | **Jul 10** | Owner handling |
| IPOMatrix JWT in anchor enrich expires | ~Jul 20 | Step will warn-skip; fix per script docstring |
| Secrets rotation (Neon pw, Kite secret, etc. leaked in old docs) | go-live | Owner rotated batch 2026-07-08; remainder per plan |
| `placeOrder` production guard | unconfirmed since June | Verify it cannot fire accidentally |
| healthchecks.io dead-man URLs in .env | pending | Watchdog pings configured but URLs unset |
| MF conviction: 5/11 funds stale >50d | monthly | Needs manual Excel drops |
| Screener cookie → peer-P/E coverage (~25% → most) | whenever | Biggest single data unlock |
| Gap-band mismatch (§3) | decision | Rakesh to choose alignment vs trade_band |

## 7. Doc policy

`docs/CURRENT_STATE.md` (this file) is the single source of truth. `AACapital_Handover_v3.md`
and the zip archive are history — mine them for API quirks and incident lore, never for
current numbers. The three-generation strategy table in §1 is the canonical example of why.
